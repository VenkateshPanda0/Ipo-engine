"""
Browser sessions.

The cookie holds a random token; the database holds only its SHA-256, so a copy of the database
cannot be used to sign in. Each session also has a CSRF token that the web app must send in a header
on every state-changing request, which a page on another site cannot read. A session ends at its
absolute expiry, after an idle period, when it is revoked, or when its user is suspended or leaves
the organisation. A revoked, expired, idle or orphaned session is refused like an unknown one.
"""

from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any

from sqlalchemy import select, update

from ipo_engine.screening.core.security import Principal, Role
from ipo_engine.screening.db.base import Database
from ipo_engine.screening.db.models import (
    MembershipRow,
    OrganisationRow,
    SessionRow,
    UserRow,
)
from ipo_engine.screening.db.repositories import audit
from ipo_engine.screening.models.exceptions import NotFoundError
from ipo_engine.screening.services.accounts import AccountError, _aware, hash_secret, now

TOUCH_EVERY = timedelta(minutes=1)  # slide the idle window at most once a minute (limits writes)


class SessionService:
    def __init__(self, db: Database, *, days: int, idle_hours: int) -> None:
        self._db = db
        self._lifetime = timedelta(days=days)
        self._idle = timedelta(hours=idle_hours)

    def create(
        self, user_id: str, org_id: str, *, user_agent: str | None = None
    ) -> tuple[str, str]:
        """Start a session; returns (cookie token, CSRF token). The cookie token is not stored."""
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        stamp = now()
        with self._db.session() as s:
            s.add(
                SessionRow(
                    id=hash_secret(token),
                    user_id=user_id,
                    org_id=org_id,
                    csrf_token=csrf,
                    created_at=stamp,
                    last_seen_at=stamp,
                    expires_at=stamp + self._lifetime,
                    user_agent=(user_agent or "")[:300] or None,
                )
            )
            user = s.get(UserRow, user_id)
            if user is not None:
                user.last_login_at = stamp
            audit(
                s, actor=user_id, action="session.created", entity_type="session",
                entity_id=hash_secret(token)[:16], org_id=org_id,
            )  # fmt: skip
        return token, csrf

    def authenticate(self, token: str) -> tuple[Principal, str] | None:
        """(principal, csrf token) for a live session cookie, else None."""
        digest = hash_secret(token)
        with self._db.session() as s:
            found = s.execute(
                select(
                    SessionRow,
                    UserRow.status,
                    OrganisationRow.status,
                    OrganisationRow.deleted_at,
                    MembershipRow.role,
                )
                .join(UserRow, UserRow.id == SessionRow.user_id)
                .join(OrganisationRow, OrganisationRow.id == SessionRow.org_id)
                .outerjoin(
                    MembershipRow,
                    (MembershipRow.org_id == SessionRow.org_id)
                    & (MembershipRow.user_id == SessionRow.user_id),
                )
                .where(SessionRow.id == digest)
            ).first()
            if found is None:
                return None
            row, user_status, org_status, org_deleted, role = found
            if row.revoked_at is not None:
                return None
            stamp = now()
            if _aware(row.expires_at) <= stamp:  # type: ignore[operator]
                return None
            if stamp - _aware(row.last_seen_at) > self._idle:  # type: ignore[operator]
                return None
            if user_status != "active":
                return None
            if org_deleted is not None or org_status != "active":
                return None
            if role is None:
                return None
            if stamp - _aware(row.last_seen_at) > TOUCH_EVERY:  # type: ignore[operator]
                row.last_seen_at = stamp
            principal = Principal(
                user_id=row.user_id,
                role=Role(role),
                authenticated=True,
                org_id=row.org_id,
                auth="session",
                session_id=digest,
            )
            return principal, row.csrf_token

    def list(self, user_id: str, *, current: str | None = None) -> list[dict[str, Any]]:
        with self._db.session() as s:
            rows = (
                s.execute(
                    select(SessionRow)
                    .where(SessionRow.user_id == user_id, SessionRow.revoked_at.is_(None))
                    .order_by(SessionRow.last_seen_at.desc())
                )
                .scalars()
                .all()
            )
            stamp = now()
            return [
                {
                    "id": r.id[:16],
                    "org_id": r.org_id,
                    "created_at": r.created_at,
                    "last_seen_at": r.last_seen_at,
                    "expires_at": r.expires_at,
                    "user_agent": r.user_agent,
                    "current": r.id == current,
                }
                for r in rows
                if _aware(r.expires_at) > stamp  # type: ignore[operator]
            ]

    def revoke(self, user_id: str, short_id: str, *, actor: str) -> None:
        """Revoke one of the user's own sessions, named by its public id."""
        if len(short_id) < 8:
            raise NotFoundError("session", short_id)
        with self._db.session() as s:
            rows = (
                s.execute(
                    select(SessionRow).where(
                        SessionRow.user_id == user_id, SessionRow.revoked_at.is_(None)
                    )
                )
                .scalars()
                .all()
            )
            hit = [r for r in rows if r.id.startswith(short_id)]
            if len(hit) != 1:
                raise NotFoundError("session", short_id)
            hit[0].revoked_at = now()
            audit(
                s, actor=actor, action="session.revoked", entity_type="session",
                entity_id=hit[0].id[:16], org_id=hit[0].org_id,
            )  # fmt: skip

    def revoke_by_id(self, session_id: str, *, actor: str) -> None:
        with self._db.session() as s:
            row = s.get(SessionRow, session_id)
            if row is not None and row.revoked_at is None:
                row.revoked_at = now()
                audit(
                    s, actor=actor, action="session.ended", entity_type="session",
                    entity_id=row.id[:16], org_id=row.org_id,
                )  # fmt: skip

    def revoke_all(self, user_id: str, *, except_id: str | None = None) -> int:
        with self._db.session() as s:
            stmt = (
                update(SessionRow)
                .where(SessionRow.user_id == user_id, SessionRow.revoked_at.is_(None))
                .values(revoked_at=now())
            )
            if except_id:
                stmt = stmt.where(SessionRow.id != except_id)
            result: Any = s.execute(stmt)
            return int(result.rowcount or 0)

    def switch_org(self, session_id: str, user_id: str, org_id: str) -> None:
        with self._db.session() as s:
            member = s.execute(
                select(MembershipRow.id).where(
                    MembershipRow.org_id == org_id, MembershipRow.user_id == user_id
                )
            ).first()
            org = s.get(OrganisationRow, org_id)
            if member is None or org is None or org.deleted_at is not None:
                raise AccountError("You are not a member of that organisation.")
            row = s.get(SessionRow, session_id)
            if row is None:
                raise NotFoundError("session", session_id[:16])
            row.org_id = org_id
            audit(
                s, actor=user_id, action="session.org_switched", entity_type="session",
                entity_id=session_id[:16], org_id=org_id,
            )  # fmt: skip

    def purge_expired(self) -> int:
        """Delete sessions that can no longer be used (housekeeping; run at startup)."""
        cutoff = now() - timedelta(days=1)
        with self._db.session() as s:
            rows = (
                s.execute(
                    select(SessionRow).where(
                        (SessionRow.expires_at < now()) | (SessionRow.revoked_at < cutoff)
                    )
                )
                .scalars()
                .all()
            )
            for r in rows:
                s.delete(r)
            return len(rows)


__all__ = ["SessionService"]
