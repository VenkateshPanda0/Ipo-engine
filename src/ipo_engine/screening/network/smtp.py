"""Send e-mail through an SMTP server the operator provides (optional; off unless SMTP_HOST)."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

TIMEOUT_S = 15.0


class MailError(RuntimeError):
    """The message could not be sent."""


class SmtpMailer:
    def __init__(
        self,
        *,
        host: str,
        port: int = 587,
        username: str | None = None,
        password: str | None = None,
        sender: str,
        security: str = "starttls",
    ) -> None:
        self._host, self._port = host, port
        self._user, self._password = username, password
        self._sender, self._security = sender, security

    def send(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()  # refuses a header value containing a line break
        try:
            msg["From"], msg["To"], msg["Subject"] = self._sender, to, subject
        except ValueError as exc:
            raise MailError("the message has an invalid header") from exc
        msg.set_content(body)
        ctx = ssl.create_default_context()
        try:
            if self._security == "ssl":
                server: smtplib.SMTP = smtplib.SMTP_SSL(
                    self._host, self._port, timeout=TIMEOUT_S, context=ctx
                )
            else:
                server = smtplib.SMTP(self._host, self._port, timeout=TIMEOUT_S)
            with server:
                if self._security == "starttls":
                    server.starttls(context=ctx)
                if self._user:
                    server.login(self._user, self._password or "")
                server.send_message(msg)
        except (OSError, smtplib.SMTPException) as exc:
            raise MailError(f"mail not sent: {type(exc).__name__}") from exc
