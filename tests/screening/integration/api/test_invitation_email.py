"""Invitation e-mail: a real SMTP conversation, header safety, and what the API reports."""

from __future__ import annotations

import socket
import threading
from email import message_from_bytes
from typing import Any

import pytest
from tests.screening.integration.api.accounts_world import build_world

from ipo_engine.screening.core.config import Settings
from ipo_engine.screening.network.smtp import MailError, SmtpMailer
from ipo_engine.screening.services.mailer import Mailer


class FakeSmtp:
    """Just enough SMTP (no TLS, no auth) to receive one message."""

    def __init__(self) -> None:
        self.messages: list[bytes] = []
        self.recipients: list[str] = []
        self._srv = socket.socket()
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(5)
        self.port = self._srv.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self._srv.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        f = conn.makefile("rwb")

        def say(line: str) -> None:
            f.write(line.encode() + b"\r\n")
            f.flush()

        say("220 fake ESMTP")
        data: list[bytes] = []
        in_data = False
        while True:
            line = f.readline()
            if not line:
                return
            if in_data:
                if line == b".\r\n":
                    self.messages.append(b"".join(data))
                    data, in_data = [], False
                    say("250 queued")
                else:
                    data.append(line)
                continue
            cmd = line.decode().strip().upper()
            if cmd.startswith(("EHLO", "HELO")):
                say("250 fake")
            elif cmd.startswith("MAIL"):
                say("250 ok")
            elif cmd.startswith("RCPT"):
                self.recipients.append(line.decode().split("<", 1)[1].split(">", 1)[0])
                say("250 ok")
            elif cmd == "DATA":
                in_data = True
                say("354 go")
            elif cmd == "QUIT":
                say("221 bye")
                return
            else:
                say("250 ok")

    def close(self) -> None:
        self._srv.close()


@pytest.fixture
def smtp() -> Any:
    server = FakeSmtp()
    yield server
    server.close()


def test_a_real_smtp_conversation_delivers_the_invitation(smtp: FakeSmtp) -> None:
    mailer = SmtpMailer(
        host="127.0.0.1", port=smtp.port, sender="no-reply@ipo.example", security="none"
    )
    mailer.send("new@acme.example", "Hello", "Body line\n")
    msg = message_from_bytes(smtp.messages[0])
    assert smtp.recipients == ["new@acme.example"]
    assert msg["Subject"] == "Hello" and msg["From"] == "no-reply@ipo.example"
    assert "Body line" in msg.get_payload()


def test_a_header_with_a_line_break_is_refused_not_sent(smtp: FakeSmtp) -> None:
    mailer = SmtpMailer(host="127.0.0.1", port=smtp.port, sender="a@b.example", security="none")
    with pytest.raises(MailError):
        mailer.send("x@y.example", "Hi\r\nBcc: evil@evil.example", "body")
    assert smtp.messages == []


def test_an_unreachable_server_is_a_mail_error_not_a_crash() -> None:
    mailer = SmtpMailer(host="127.0.0.1", port=1, sender="a@b.example", security="none")
    with pytest.raises(MailError, match="not sent"):
        mailer.send("x@y.example", "s", "b")


def test_the_mailer_flattens_an_organisation_name_with_line_breaks(smtp: FakeSmtp) -> None:
    s = Settings(
        SMTP_HOST="127.0.0.1",
        SMTP_PORT=str(smtp.port),
        SMTP_FROM="a@b.example",
        SMTP_SECURITY="none",
    )
    why = Mailer(s).send_invitation(
        "p@q.example", "Evil\r\nBcc: x@y.example", "ann", "http://l/i?token=t", "viewer"
    )
    assert why is None
    msg = message_from_bytes(smtp.messages[0])
    assert msg["Bcc"] is None and "Evil Bcc: x@y.example" in msg["Subject"]


def test_without_smtp_the_mailer_says_so() -> None:
    assert (
        Mailer(Settings()).send_invitation("a@b.example", "Org", "ann", "l", "viewer")
        == "e-mail is not configured"
    )


class Recorder:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []
        self.fail = False

    def send(self, to: str, subject: str, body: str) -> None:
        if self.fail:
            raise MailError("mail not sent: ConnectionRefusedError")
        self.sent.append((to, subject, body))


def _world(app_factory: Any, rec: Recorder) -> Any:
    return build_world(app_factory, seed_a=False, _app={"mail_transport": rec})


def test_creating_an_invitation_emails_it_when_mail_is_configured(app_factory: Any) -> None:
    rec = Recorder()
    w = _world(app_factory, rec)
    r = w.client.post(
        "/api/v1/org/invitations",
        json={"email": "New@Acme.example", "role": "reviewer"},
        headers=w.a.h,
    )
    assert r.status_code == 201 and r.json()["emailed"] is True and r.json()["email_error"] is None
    to, subject, body = rec.sent[0]
    assert to == "new@acme.example" and "Alpha Capital" in subject
    assert r.json()["link"] in body and "reviewer" in body


def test_a_mail_failure_does_not_lose_the_invitation(app_factory: Any) -> None:
    rec = Recorder()
    rec.fail = True
    w = _world(app_factory, rec)
    r = w.client.post(
        "/api/v1/org/invitations", json={"email": "x@acme.example", "role": "viewer"}, headers=w.a.h
    )
    assert (
        r.status_code == 201
        and r.json()["emailed"] is False
        and "not sent" in r.json()["email_error"]
    )
    assert r.json()["link"].startswith("http")  # the admin can still copy the link
    assert len(w.client.get("/api/v1/org/invitations", headers=w.a.h).json()) == 1


def test_without_mail_the_api_says_the_link_must_be_shared_by_hand(app_factory: Any) -> None:
    w = build_world(app_factory, seed_a=False)
    r = w.client.post(
        "/api/v1/org/invitations", json={"email": "x@acme.example", "role": "viewer"}, headers=w.a.h
    )
    assert r.json()["emailed"] is False and r.json()["email_error"] is None
