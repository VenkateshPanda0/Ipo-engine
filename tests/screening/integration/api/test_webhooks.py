"""Webhooks: signing, SSRF protection, the outbox, retries, and per-organisation isolation."""

from __future__ import annotations

import http.server
import json
import socket
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.screening.integration.api.accounts_world import World, build_world

from ipo_engine.screening.core.config import Settings
from ipo_engine.screening.db.models import WebhookDeliveryRow
from ipo_engine.screening.main import create_app
from ipo_engine.screening.network.http import HttpError
from ipo_engine.screening.network.webhook_http import PinnedSender, validate_target
from ipo_engine.screening.services.webhooks import sign, verify_signature

KEY = "test-signing-key-0123456789"
PUBLIC = "https://93.184.216.34/hook"  # a public address literal: no DNS needed offline


class FakeSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, bytes, dict[str, str]]] = []
        self.answer: int | Exception = 200

    def send(self, url: str, body: bytes, headers: dict[str, str]) -> int:
        self.sent.append((url, body, headers))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def _world(app_factory: Any, **env: Any) -> tuple[World, FakeSender]:
    sender = FakeSender()

    def make(**kw: Any) -> TestClient:
        import tempfile
        from pathlib import Path

        tmp = Path(tempfile.mkdtemp())
        values = {
            "DATA_DIR": str(tmp / "d"),
            "DATABASE_URL": f"sqlite:///{tmp / 'w.db'}",
            "WEBHOOK_SIGNING_KEY": KEY,
            "ACCOUNTS_ENABLED": "true",
            **{k: str(v) for k, v in {**env, **kw}.items()},
        }
        client = TestClient(
            create_app(Settings(**values), inline_processing=True, webhook_sender=sender)  # type: ignore[arg-type]
        )
        client.__enter__()
        made.append(client)
        return client

    made: list[TestClient] = []
    world = build_world(lambda **kw: make(**kw), seed_a=False)
    world._closers = made  # type: ignore[attr-defined]
    return world, sender


@pytest.fixture
def hooks(app_factory: Any) -> Any:
    world, sender = _world(app_factory)
    yield world, sender
    for c in world._closers:  # type: ignore[attr-defined]
        c.__exit__(None, None, None)


def _hook(w: World, events: list[str] | None = None, url: str = PUBLIC, who: Any = None) -> Any:
    return w.client.post(
        "/api/v1/webhooks",
        json={"url": url, "events": events or ["case.created", "screening.completed"]},
        headers=(who or w.a).h,
    )


def _drain(w: World) -> int:
    n = 0
    while k := w.accounts and w.client.app.state.container.webhooks.dispatch_due():  # type: ignore[attr-defined]
        n += k
    return n


# ------------------------------------------------------------------- signatures
def test_a_signature_verifies_and_any_change_breaks_it() -> None:
    body = b'{"a":1}'
    now = int(datetime.now(tz=UTC).timestamp())
    header = sign("whsec_x", now, body)
    assert verify_signature("whsec_x", header, body)
    assert not verify_signature("whsec_x", header, b'{"a":2}')  # body changed
    assert not verify_signature("whsec_y", header, body)  # wrong secret
    assert not verify_signature("whsec_x", sign("whsec_x", now - 3600, body), body)  # replay
    assert not verify_signature("whsec_x", "garbage", body)


# ------------------------------------------------------------------------ SSRF
@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/x",
        "https://localhost/x",
        "https://10.0.0.5/x",
        "https://192.168.1.1/x",
        "https://172.16.0.9/x",
        "https://169.254.169.254/latest/meta-data/",  # cloud metadata
        "https://100.64.0.1/x",  # carrier-grade NAT
        "https://[::1]/x",
        "https://[fe80::1]/x",
        "https://0.0.0.0/x",
        "http://93.184.216.34/x",  # not https
        "ftp://93.184.216.34/x",
        "https://user:pw@93.184.216.34/x",
        "https:///nohost",
        "not a url",
    ],
)
def test_private_internal_and_odd_targets_are_refused(url: str) -> None:
    with pytest.raises(HttpError):
        validate_target(url)


def test_a_name_that_resolves_to_a_private_address_is_refused_even_among_public_ones() -> None:
    def rebinding(host: str, port: int, **_: Any) -> list[Any]:
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", port)),
        ]

    with pytest.raises(HttpError, match="non-public"):
        validate_target("https://evil.example/x", resolver=rebinding)

    def fine(host: str, port: int, **_: Any) -> list[Any]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    assert validate_target("https://ok.example/p?q=1", resolver=fine).ips == ("93.184.216.34",)
    assert validate_target("https://ok.example/p?q=1", resolver=fine).path == "/p?q=1"


def test_the_api_refuses_dangerous_targets_and_unknown_events(hooks: Any) -> None:
    w, _ = hooks
    for bad in ("https://127.0.0.1/x", "https://169.254.169.254/", "http://93.184.216.34/x"):
        assert _hook(w, url=bad).status_code == 422, bad
    assert _hook(w, events=["not.an.event"]).status_code == 422
    assert _hook(w, events=["ping"]).status_code == 422  # ping is sent only by the test button
    assert _hook(w).status_code == 201


# ------------------------------------------------------------ the service itself
def test_webhooks_are_off_without_a_signing_key(app_factory: Any) -> None:
    w = build_world(app_factory, seed_a=False)  # no WEBHOOK_SIGNING_KEY
    assert w.client.get("/api/v1/webhooks", headers=w.a.h).json()["enabled"] is False
    assert _hook(w).status_code == 422


def test_the_secret_is_shown_on_creation_and_listing_never_repeats_it(hooks: Any) -> None:
    w, _ = hooks
    made = _hook(w).json()
    assert made["secret"].startswith("whsec_") and len(made["secret"]) > 30
    listing = w.client.get("/api/v1/webhooks", headers=w.a.h).json()
    assert "whsec_" not in json.dumps(listing["items"]) and listing["enabled"] is True


def test_an_event_is_signed_and_carries_ids_and_names_only(hooks: Any) -> None:
    w, sender = hooks
    made = _hook(w).json()
    case = w.client.post("/api/v1/cases", json={"company_name": "Hooked Ltd"}, headers=w.a.h).json()
    assert _drain(w) == 1
    url, body, headers = sender.sent[0]
    assert url == PUBLIC and headers["X-IPO-Event"] == "case.created"
    assert verify_signature(made["secret"], headers["X-IPO-Signature"], body)
    payload = json.loads(body)
    assert payload["data"] == {"case_id": case["id"], "company_name": "Hooked Ltd"}
    assert payload["organisation_id"] == w.a.org_id and payload["id"] == headers["X-IPO-Delivery"]


def test_only_subscribed_active_endpoints_of_the_same_organisation_get_events(hooks: Any) -> None:
    w, sender = hooks
    mine = _hook(w, events=["case.created"]).json()
    _hook(w, events=["screening.completed"])  # not subscribed to case.created
    theirs = _hook(w, who=w.b).json()
    off = _hook(w, events=["case.created"]).json()
    w.client.patch(f"/api/v1/webhooks/{off['id']}", json={"active": False}, headers=w.a.h)
    w.client.post("/api/v1/cases", json={"company_name": "X Ltd"}, headers=w.a.h)
    _drain(w)
    assert len(sender.sent) == 1
    assert verify_signature(mine["secret"], sender.sent[0][2]["X-IPO-Signature"], sender.sent[0][1])
    assert not verify_signature(
        theirs["secret"], sender.sent[0][2]["X-IPO-Signature"], sender.sent[0][1]
    )


def test_an_organisation_can_switch_all_its_webhooks_off(hooks: Any) -> None:
    w, sender = hooks
    _hook(w)
    w.client.patch("/api/v1/org/settings", json={"webhooks_enabled": False}, headers=w.a.h)
    w.client.post("/api/v1/cases", json={"company_name": "Quiet Ltd"}, headers=w.a.h)
    assert _drain(w) == 0 and sender.sent == []


def test_a_failing_endpoint_is_retried_with_backoff_then_given_up_and_admins_told(
    app_factory: Any,
) -> None:
    w, sender = _world(app_factory, WEBHOOK_MAX_ATTEMPTS="3")
    sender.answer = 500
    _hook(w)
    w.client.post("/api/v1/cases", json={"company_name": "Flaky Ltd"}, headers=w.a.h)
    svc = w.client.app.state.container.webhooks  # type: ignore[attr-defined]
    db = w.client.app.state.container.db  # type: ignore[attr-defined]

    def force_due() -> None:
        with db.session() as s:
            for d in s.execute(select(WebhookDeliveryRow)).scalars():
                d.next_attempt_at = datetime.now(tz=UTC) - timedelta(seconds=1)

    assert svc.dispatch_due() == 1
    with db.session() as s:
        d = s.execute(select(WebhookDeliveryRow)).scalar_one()
        assert d.status == "pending" and d.attempts == 1 and d.last_status == 500
        wait = (d.next_attempt_at.replace(tzinfo=UTC) - datetime.now(tz=UTC)).total_seconds()
        assert 30 < wait <= 60  # first backoff: a minute
    assert svc.dispatch_due() == 0  # not due yet
    force_due()
    svc.dispatch_due()
    force_due()
    svc.dispatch_due()
    with db.session() as s:
        d = s.execute(select(WebhookDeliveryRow)).scalar_one()
        assert d.status == "failed" and d.attempts == 3
    notes = w.client.get("/api/v1/notifications", headers=w.a.h).json()["items"]
    assert any(n["kind"] == "webhook_failed" for n in notes)
    sender.answer = 200
    hid = w.client.get("/api/v1/webhooks", headers=w.a.h).json()["items"][0]["id"]
    delivery = w.client.get(f"/api/v1/webhooks/{hid}/deliveries", headers=w.a.h).json()[0]
    w.client.post(f"/api/v1/webhooks/{hid}/deliveries/{delivery['id']}/redeliver", headers=w.a.h)
    assert svc.dispatch_due() == 1
    assert (
        w.client.get(f"/api/v1/webhooks/{hid}/deliveries", headers=w.a.h).json()[0]["status"]
        == "delivered"
    )
    for c in w._closers:  # type: ignore[attr-defined]
        c.__exit__(None, None, None)


def test_a_network_error_counts_as_a_failed_attempt(hooks: Any) -> None:
    w, sender = hooks
    sender.answer = HttpError("delivery failed: ConnectionRefusedError")
    _hook(w)
    w.client.post("/api/v1/cases", json={"company_name": "Down Ltd"}, headers=w.a.h)
    _drain_once = w.client.app.state.container.webhooks.dispatch_due()
    assert _drain_once == 1
    with w.client.app.state.container.db.session() as s:
        d = s.execute(select(WebhookDeliveryRow)).scalar_one()
        assert d.status == "pending" and "ConnectionRefused" in (d.last_error or "")


def test_rotating_the_secret_invalidates_the_old_one(hooks: Any) -> None:
    w, sender = hooks
    made = _hook(w).json()
    rotated = w.client.post(f"/api/v1/webhooks/{made['id']}/rotate", headers=w.a.h).json()
    assert rotated["secret"] != made["secret"] and rotated["secret_version"] == 2
    w.client.post("/api/v1/cases", json={"company_name": "R Ltd"}, headers=w.a.h)
    _drain(w)
    _, body, headers = sender.sent[0]
    assert verify_signature(rotated["secret"], headers["X-IPO-Signature"], body)
    assert not verify_signature(made["secret"], headers["X-IPO-Signature"], body)


def test_the_test_button_sends_a_ping(hooks: Any) -> None:
    w, sender = hooks
    made = _hook(w).json()
    assert w.client.post(f"/api/v1/webhooks/{made['id']}/test", headers=w.a.h).status_code == 202
    _drain(w)
    assert sender.sent[0][2]["X-IPO-Event"] == "ping"


def test_a_screening_and_a_document_produce_their_events(hooks: Any) -> None:
    from tests.screening.fixtures.pdf_factory import standard_drhp

    w, sender = hooks
    _hook(w, events=["document.processed", "screening.completed", "comment.added"])
    case = w.client.post("/api/v1/cases", json={"company_name": "Full Ltd"}, headers=w.a.h).json()
    w.client.post(
        f"/api/v1/cases/{case['id']}/documents",
        files={"file": ("d.pdf", standard_drhp(), "application/pdf")},
        headers=w.a.h,
    )
    w.client.post(f"/api/v1/cases/{case['id']}/screenings", headers=w.a.h)
    w.client.post(f"/api/v1/cases/{case['id']}/comments", json={"body": "hi"}, headers=w.a.h)
    _drain(w)
    kinds = [h["X-IPO-Event"] for _, _, h in sender.sent]
    assert sorted(kinds) == ["comment.added", "document.processed", "screening.completed"]
    doc = json.loads(next(b for _, b, h in sender.sent if h["X-IPO-Event"] == "document.processed"))
    assert doc["data"]["status"] in ("awaiting_review", "completed")
    text = b"".join(b for _, b, _ in sender.sent).decode()
    # names and ids may appear in a payload; extracted figures and text never do
    assert "net_tangible_assets" not in text and "123.4567" not in text


def test_other_organisations_cannot_see_or_change_a_webhook(hooks: Any) -> None:
    w, _ = hooks
    mine = _hook(w).json()
    for method, path in (
        ("patch", f"/api/v1/webhooks/{mine['id']}"),
        ("delete", f"/api/v1/webhooks/{mine['id']}"),
        ("post", f"/api/v1/webhooks/{mine['id']}/rotate"),
        ("post", f"/api/v1/webhooks/{mine['id']}/test"),
        ("get", f"/api/v1/webhooks/{mine['id']}/deliveries"),
    ):
        kwargs: dict[str, Any] = {"json": {"active": False}} if method == "patch" else {}
        assert getattr(w.client, method)(path, headers=w.b.h, **kwargs).status_code == 404, path
    assert w.client.get("/api/v1/webhooks", headers=w.b.h).json()["items"] == []


def test_an_organisation_has_a_limited_number_of_webhooks_and_only_admins_manage_them(
    hooks: Any,
) -> None:
    from tests.screening.integration.api.accounts_world import make_member

    from ipo_engine.screening.core.security import Role

    w, _ = hooks
    rev = make_member(w.client, w.a.org_id, "rev@alpha.example", Role.REVIEWER)
    assert _hook(w, who=rev).status_code == 403
    for _ in range(10):
        assert _hook(w).status_code == 201
    assert _hook(w).status_code == 422


# ----------------------------------------------- the real sender, end to end
class _Receiver(http.server.BaseHTTPRequestHandler):
    got: ClassVar[list[tuple[bytes, dict[str, str]]]] = []
    status = 200

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        _Receiver.got.append((self.rfile.read(length), dict(self.headers.items())))
        self.send_response(_Receiver.status)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *a: Any) -> None:
        pass


def test_the_real_sender_delivers_a_signed_post_to_a_local_receiver() -> None:
    server = http.server.HTTPServer(("127.0.0.1", 0), _Receiver)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/hook"
        with pytest.raises(HttpError):  # refused unless private targets are allowed
            PinnedSender().send(url, b"{}", {})
        body = b'{"hello":"world"}'
        header = sign("whsec_t", int(time.time()), body)
        code = PinnedSender(allow_private=True).send(
            url, body, {"X-IPO-Signature": header, "Content-Type": "application/json"}
        )
        assert code == 200
        received, headers = _Receiver.got[-1]
        assert received == body and verify_signature(
            "whsec_t", headers["X-IPO-Signature"], received
        )
        assert headers["Host"] == "127.0.0.1"
        _Receiver.status = 302
        assert (
            PinnedSender(allow_private=True).send(url, body, {}) == 302
        )  # a redirect is not followed
    finally:
        _Receiver.status = 200
        server.shutdown()


def test_the_background_dispatcher_delivers_without_being_called(app_factory: Any) -> None:
    w, sender = _world(app_factory)
    try:
        _hook(w)
        w.client.post("/api/v1/cases", json={"company_name": "Auto Ltd"}, headers=w.a.h)
        end = time.time() + 20
        while not sender.sent and time.time() < end:
            time.sleep(0.2)
        assert sender.sent, "the dispatcher thread should have sent it"
    finally:
        for c in w._closers:  # type: ignore[attr-defined]
            c.__exit__(None, None, None)
