"""Regression tests for defects found by the repository audit (see audit_reports/)."""

from __future__ import annotations

import contextlib
import socket
import threading
import time
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar

import pytest
from fastapi.testclient import TestClient

from ipo_engine.screening.core.config import Settings
from ipo_engine.screening.core.security import safe_equals
from ipo_engine.screening.main import create_app
from ipo_engine.screening.network import webhook_http
from ipo_engine.screening.network.http import _OPENER, HttpError
from ipo_engine.screening.network.webhook_http import PinnedSender, validate_target
from ipo_engine.screening.services.tabular import cell_text


def _public(host: str, port: int, **_: Any) -> list[Any]:
    return [(2, 1, 6, "", ("93.184.216.34", port))]


def _send_bounded(sender: PinnedSender, url: str, *, limit_s: float) -> None:
    """One delivery in a thread: a delivery never cut off fails the test instead of hanging it."""
    done = threading.Event()

    def run() -> None:
        with contextlib.suppress(HttpError):
            sender.send(url, b"{}", {})
        done.set()

    threading.Thread(target=run, daemon=True).start()
    assert done.wait(limit_s), f"the delivery was still running after {limit_s} s"


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
        _send_bounded(sender, f"http://127.0.0.1:{port}/x", limit_s=6)
        assert time.monotonic() - started < 7
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


def test_the_http_client_refuses_redirects_instead_of_following_them() -> None:
    """A 302 from an https IdP URL to another address must not be followed."""
    import http.server

    class Redirect(http.server.BaseHTTPRequestHandler):
        hits: ClassVar[list[str]] = []

        def do_GET(self) -> None:
            Redirect.hits.append(self.path)
            if self.path == "/start":
                self.send_response(302)
                self.send_header("Location", "/elsewhere")
                self.end_headers()
            else:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")

        def log_message(self, *a: Any) -> None:
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Redirect)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/start")
        with pytest.raises(urllib.error.HTTPError) as exc:
            _OPENER.open(req, timeout=5)  # the https check is the caller's; this is the redirects
        assert exc.value.code == 302
        assert Redirect.hits == ["/start"]  # /elsewhere was never requested
    finally:
        srv.shutdown()


def test_a_drip_from_a_server_that_closes_the_connection_is_cut_off_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP/1.0 or Connection: close makes http.client drop its socket reference early."""
    monkeypatch.setattr(webhook_http, "TOTAL_S", 1.0)
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    stop = threading.Event()

    def drip() -> None:
        conn, _ = srv.accept()
        conn.recv(65536)
        conn.sendall(b"HTTP/1.0 200 OK\r\nContent-Length: 100000\r\n\r\n")
        while not stop.is_set():
            try:
                conn.sendall(b"x")
            except OSError:
                break
            time.sleep(0.3)
        conn.close()

    threading.Thread(target=drip, daemon=True).start()
    sender = PinnedSender(allow_private=True, resolver=_resolves_to("127.0.0.1"))
    started = time.monotonic()
    try:
        _send_bounded(sender, f"http://127.0.0.1:{port}/x", limit_s=6)
        assert time.monotonic() - started < 7
    finally:
        stop.set()
        srv.close()


def test_failed_credentials_count_but_requests_with_no_credential_do_not(tmp_path: Path) -> None:
    settings = Settings(
        DATA_DIR=str(tmp_path / "d"),
        DATABASE_URL=f"sqlite:///{tmp_path / 'b.db'}",
        API_KEYS="ops|admin|good-key",
        API_RATE_LIMIT_PER_MINUTE="3",
    )
    with TestClient(create_app(settings, inline_processing=True)) as client:
        assert [client.get("/api/v1/cases").status_code for _ in range(10)] == [401] * 10
        bad = {"Authorization": "Bearer wrong"}
        assert [client.get("/api/v1/cases", headers=bad).status_code for _ in range(4)] == [
            401,
            401,
            401,
            429,
        ]


def test_safe_equals_survives_a_lone_surrogate() -> None:
    assert safe_equals("\ud800", "\ud800")
    assert not safe_equals("\ud800", "x")
