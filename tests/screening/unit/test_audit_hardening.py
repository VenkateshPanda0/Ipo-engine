"""Regression tests for defects found by the repository audit (see audit_reports/)."""

from __future__ import annotations

import contextlib
import socket
import threading
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ipo_engine.screening.core.config import Settings
from ipo_engine.screening.core.security import safe_equals
from ipo_engine.screening.main import create_app
from ipo_engine.screening.network import webhook_http
from ipo_engine.screening.network.http import HttpError
from ipo_engine.screening.network.webhook_http import PinnedSender, validate_target
from ipo_engine.screening.services.tabular import cell_text


def _public(host: str, port: int, **_: Any) -> list[Any]:
    return [(2, 1, 6, "", ("93.184.216.34", port))]


def _resolves_to(ip: str) -> Any:
    fam = socket.AF_INET6 if ":" in ip else socket.AF_INET

    def resolver(host: str, port: int, **_: Any) -> list[Any]:
        return [(fam, 1, 6, "", (ip, port))]

    return resolver


# ----------------------------------------------------------------- webhook targets
@pytest.mark.parametrize(
    "url",
    ["https://hook.example:99999/x", "https://hook.example:abc/x", "https://hook.example:0/x"],
)
def test_a_bad_port_is_a_clean_refusal_not_a_crash(url: str) -> None:
    with pytest.raises(HttpError, match="port"):
        validate_target(url, resolver=_public)


@pytest.mark.parametrize(
    "ip",
    [
        "64:ff9b::a9fe:a9fe",  # NAT64 for 169.254.169.254
        "64:ff9b::7f00:1",  # NAT64 for 127.0.0.1
        "::127.0.0.1",  # IPv4-compatible
        "::ffff:127.0.0.1",  # IPv4-mapped
        "2002:7f00:1::1",  # 6to4 for 127.0.0.1
    ],
)
def test_addresses_that_smuggle_an_ipv4_target_are_refused(ip: str) -> None:
    with pytest.raises(HttpError, match="non-public"):
        validate_target("https://hook.example/x", resolver=_resolves_to(ip))


def test_an_ordinary_public_ipv6_address_is_still_allowed() -> None:
    t = validate_target("https://hook.example/x", resolver=_resolves_to("2606:4700::1111"))
    assert t.ips == ("2606:4700::1111",)


def test_a_server_that_drips_bytes_cannot_hold_a_delivery_for_ever(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(webhook_http, "TOTAL_S", 1.0)
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    stop = threading.Event()

    def drip() -> None:
        conn, _ = srv.accept()
        conn.recv(65536)
        conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 100000\r\n\r\n")
        while not stop.is_set():
            try:
                conn.sendall(b"x")
            except OSError:
                break
            time.sleep(0.3)  # each read succeeds inside TIMEOUT_S, so only a total deadline helps
        conn.close()

    threading.Thread(target=drip, daemon=True).start()
    sender = PinnedSender(allow_private=True, resolver=_resolves_to("127.0.0.1"))
    started = time.monotonic()
    try:
        # the drip may be cut off mid-body (HttpError) or the status line read first (an int)
        with contextlib.suppress(HttpError):
            sender.send(f"http://127.0.0.1:{port}/x", b"{}", {})
        assert time.monotonic() - started < 5
    finally:
        stop.set()
        srv.close()


# ------------------------------------------------------------------ exports and ids
def test_negative_numbers_stay_numbers_but_text_that_looks_like_a_formula_is_defused() -> None:
    assert cell_text(-5) == "-5"
    assert cell_text(-2.5) == "-2.5"
    assert cell_text(Decimal("-3.10")) == "-3.10"
    assert cell_text(True) == "True"
    assert cell_text("-5") == "'-5"  # text is still treated as a possible formula
    assert cell_text("=SUM(A1)") == "'=SUM(A1)"
    assert cell_text("@cmd") == "'@cmd"


def test_a_digest_with_a_trailing_newline_is_not_a_digest() -> None:
    from ipo_engine.screening.network.s3 import _HEX64

    assert _HEX64.fullmatch("a" * 64)
    assert not _HEX64.fullmatch("a" * 64 + "\n")


# ----------------------------------------------------------- non-ASCII credentials
def test_safe_equals_accepts_any_text_and_still_compares() -> None:
    assert safe_equals("abc", "abc")
    assert not safe_equals("abc", "abd")
    assert not safe_equals("tøken", "token")
    assert safe_equals("tøken", "tøken")


def test_a_signature_header_with_odd_characters_is_just_invalid() -> None:
    from ipo_engine.screening.services.webhooks import verify_signature

    assert verify_signature("secret", f"t={int(time.time())},v1=ø", b"{}") is False


# ------------------------------------------------------------------ configuration
def test_a_wildcard_cors_origin_is_refused_because_credentials_are_sent() -> None:
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        Settings(CORS_ORIGINS="*")
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        Settings(CORS_ORIGINS="https://a.example,*")
    assert Settings(CORS_ORIGINS="https://a.example").cors_origins == ["https://a.example"]


def test_an_empty_api_keys_variable_does_not_hide_the_keys_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    keys = tmp_path / "keys"
    keys.write_text("ops|admin|secret-key\n")
    monkeypatch.setenv("API_KEYS", "")
    monkeypatch.setenv("API_KEYS_FILE", str(keys))
    assert Settings().api_keys == "ops|admin|secret-key"
    monkeypatch.setenv("API_KEYS", "dir|viewer|direct-key")
    assert Settings().api_keys == "dir|viewer|direct-key"  # a direct value wins


# ---------------------------------------------------------- guessing credentials
def test_failed_credentials_are_throttled_but_good_ones_are_not(tmp_path: Path) -> None:
    settings = Settings(
        DATA_DIR=str(tmp_path / "d"),
        DATABASE_URL=f"sqlite:///{tmp_path / 'a.db'}",
        API_KEYS="ops|admin|good-key",
        API_RATE_LIMIT_PER_MINUTE="5",
    )
    with TestClient(create_app(settings, inline_processing=True)) as client:
        bad = {"Authorization": "Bearer wrong"}
        codes = [client.get("/api/v1/cases", headers=bad).status_code for _ in range(12)]
        assert codes[:5] == [401] * 5 and 429 in codes[5:]
        # the same address still gets a refusal, never access, and a good key is a different story
        assert client.get("/api/v1/cases", headers=bad).status_code in (401, 429)
        good = client.get("/api/v1/cases", headers={"Authorization": "Bearer good-key"})
        assert good.status_code == 200
