"""
Sign-in with an identity provider: begin the redirect, complete the callback, start a session.

State is single-use and short-lived, and it is bound to the browser that started the flow by a
cookie, so a link an attacker obtained cannot be completed by someone else (login CSRF). The
address to return to is accepted only as a path on this site.
"""

from __future__ import annotations

import secrets
from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from ipo_engine.screening.core.config import Settings
from ipo_engine.screening.core.security import safe_equals
from ipo_engine.screening.db.base import Database
from ipo_engine.screening.db.models import OAuthStateRow
from ipo_engine.screening.services.accounts import AccountError, AccountService, hash_secret, now
from ipo_engine.screening.services.sessions import SessionService

if TYPE_CHECKING:
    from ipo_engine.screening.network.oidc import OidcClient

STATE_TTL = timedelta(minutes=10)
PROVIDER = "google"


def safe_next(value: str | None) -> str:
    """A path on this site, or "/". Anything that could leave the site is dropped."""
    if not value or not value.startswith("/") or value.startswith("//") or "\\" in value:
        return "/"
    if any(ord(ch) < 32 for ch in value) or len(value) > 500:
        return "/"
    return value


class SignInService:
    def __init__(
        self,
        db: Database,
        settings: Settings,
        accounts: AccountService,
        sessions: SessionService,
        oidc: OidcClient | None,
    ) -> None:
        self._db, self._settings = db, settings
        self._accounts, self._sessions, self._oidc = accounts, sessions, oidc

    @property
    def available(self) -> bool:
        return self._oidc is not None

    def begin(self, *, next_url: str | None, invitation_token: str | None) -> tuple[str, str]:
        """(URL to send the browser to, state value to put in the binding cookie)."""
        if self._oidc is None:
            raise AccountError("Google sign-in is not configured.")
        from ipo_engine.screening.network.oidc import new_pkce

        invitation_id = None
        if invitation_token:
            invitation_id = self._accounts.invitation_id_for_token(invitation_token)
            if invitation_id is None:
                raise AccountError("That invitation is no longer valid.")
        state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        verifier, challenge = new_pkce()
        with self._db.session() as s:
            s.add(
                OAuthStateRow(
                    state_hash=hash_secret(state),
                    provider=PROVIDER,
                    nonce=nonce,
                    code_verifier=verifier,
                    next_url=safe_next(next_url),
                    invitation_id=invitation_id,
                    expires_at=now() + STATE_TTL,
                )
            )
            # tidy abandoned attempts
            for old in s.execute(
                select(OAuthStateRow).where(OAuthStateRow.expires_at < now())
            ).scalars():
                s.delete(old)
        url = self._oidc.authorization_url(state=state, nonce=nonce, code_challenge=challenge)
        return url, state

    def complete(
        self, *, code: str, state: str, bound_state: str | None, user_agent: str | None
    ) -> tuple[str, str, str]:
        """Finish the callback. Returns (session cookie token, CSRF token, path to return to)."""
        from ipo_engine.screening.network.oidc import OidcError

        if self._oidc is None:
            raise AccountError("Google sign-in is not configured.")
        if not bound_state or not safe_equals(bound_state, state):
            raise AccountError("This sign-in was not started in this browser. Start again.")
        with self._db.session() as s:
            row = s.get(OAuthStateRow, hash_secret(state))
            if row is None:
                raise AccountError("This sign-in link has already been used or has expired.")
            valid = row.expires_at.replace(tzinfo=row.expires_at.tzinfo or now().tzinfo) > now()
            nonce, verifier, next_url, invitation_id = (
                row.nonce,
                row.code_verifier,
                row.next_url,
                row.invitation_id,
            )
            s.delete(row)  # single use, whatever happens next
        if not valid:
            raise AccountError("This sign-in link has already been used or has expired.")
        try:
            who = self._oidc.exchange(code=code, code_verifier=verifier, nonce=nonce)
        except OidcError as exc:
            raise AccountError(str(exc)) from exc
        allowed = {d.lower() for d in self._settings.allowed_email_domains}
        if allowed and who.email.rsplit("@", 1)[-1].lower() not in allowed:
            raise AccountError("Accounts from that email domain are not allowed here.")
        user, org_id = self._accounts.sign_in(
            provider=PROVIDER,
            subject=who.subject,
            email=who.email,
            email_verified=who.email_verified,
            name=who.name,
            invitation_id=invitation_id,
            signup_open=self._settings.signup_mode == "open",
        )
        token, csrf = self._sessions.create(user["id"], org_id, user_agent=user_agent)
        return token, csrf, next_url
