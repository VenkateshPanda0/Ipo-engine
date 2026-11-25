"""E-mail the app sends (only invitations so far), if the operator configured an SMTP server."""

from __future__ import annotations

import logging
from typing import Any

from ipo_engine.screening.core.config import Settings

logger = logging.getLogger(__name__)


def _one_line(text: str) -> str:
    return " ".join(text.split())


class Mailer:
    def __init__(self, settings: Settings, transport: Any = None) -> None:
        self._settings = settings
        self._transport = transport

    @property
    def enabled(self) -> bool:
        return self._transport is not None or bool(self._settings.smtp_host)

    def _smtp(self) -> Any:
        if self._transport is None:  # the only place the SMTP code is loaded
            from ipo_engine.screening.network.smtp import SmtpMailer

            s = self._settings
            self._transport = SmtpMailer(
                host=s.smtp_host or "",
                port=s.smtp_port,
                username=s.smtp_user,
                password=s.smtp_password,
                sender=s.smtp_from or s.smtp_user or "",
                security=s.smtp_security,
            )
        return self._transport

    def send_invitation(
        self, to: str, organisation: str, inviter: str, link: str, role: str
    ) -> str | None:
        """Send the invitation. Returns None on success, or a short reason it was not sent."""
        if not self.enabled:
            return "e-mail is not configured"
        org = _one_line(organisation)
        body = (
            f"{_one_line(inviter)} has invited you to join {org} on IPO Engine as {role}.\n\n"
            f"Open this link to accept (it works once and expires):\n{link}\n\n"
            "If you were not expecting this, you can ignore the message.\n"
        )
        try:
            self._smtp().send(to, f"You are invited to {org} on IPO Engine", body)
        except Exception as exc:
            logger.warning("invitation_email_failed", extra={"error": str(exc)[:200]})
            return str(exc)[:200] or "the message could not be sent"
        return None
