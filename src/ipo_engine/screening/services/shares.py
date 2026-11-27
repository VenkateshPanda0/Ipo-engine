"""
Share links: a read-only view of one report for someone without an account.

The link carries a random token; only its hash is stored. It expires, can be revoked, and shows the
one report it was made for (nothing else in the organisation). Views are counted. The page served is
the same standalone HTML export the signed-in app offers, with the same restrictive CSP.
"""

from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from ipo_engine.screening.db.base import Database
from ipo_engine.screening.db.models import CaseRow, OrganisationRow, ReportRow, ShareLinkRow
from ipo_engine.screening.db.repositories import audit
from ipo_engine.screening.models.exceptions import NotFoundError
from ipo_engine.screening.services.accounts import AccountError, _aware, hash_secret, now

MAX_DAYS = 90
MAX_ACTIVE_PER_REPORT = 20


class ShareService:
    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, report_id: str, org_id: str, *, actor: str, days: int = 7) -> dict[str, Any]:
        if not 1 <= days <= MAX_DAYS:
            raise AccountError(f"A share link lasts 1 to {MAX_DAYS} days.")
        token = secrets.token_urlsafe(32)
        with self._db.session() as s:
            owner = s.execute(
                select(CaseRow.org_id)
                .join(ReportRow, ReportRow.case_id == CaseRow.id)
                .where(ReportRow.report_id == report_id)
            ).scalar_one_or_none()
            if owner != org_id:
                raise NotFoundError("report", report_id)
            live = [
                r
                for r in s.execute(
                    select(ShareLinkRow).where(
                        ShareLinkRow.report_id == report_id, ShareLinkRow.revoked_at.is_(None)
                    )
                ).scalars()
                if _aware(r.expires_at) > now()  # type: ignore[operator]
            ]
            if len(live) >= MAX_ACTIVE_PER_REPORT:
                raise AccountError("This report already has the maximum number of live links.")
            row = ShareLinkRow(
                id=str(uuid4()),
                org_id=org_id,
                report_id=report_id,
                token_hash=hash_secret(token),
                created_by=actor,
                expires_at=now() + timedelta(days=days),
            )
            s.add(row)
            s.flush()
            audit(
                s, actor=actor, action="share.created", entity_type="report", entity_id=report_id,
                org_id=org_id, details={"share_id": row.id, "days": days},
            )  # fmt: skip
            return {**self._out(row), "token": token}

    def list(self, report_id: str, org_id: str) -> list[dict[str, Any]]:
        with self._db.session() as s:
            rows = s.execute(
                select(ShareLinkRow)
                .where(ShareLinkRow.report_id == report_id, ShareLinkRow.org_id == org_id)
                .order_by(ShareLinkRow.created_at.desc())
            ).scalars()
            return [self._out(r) for r in rows]

    def revoke(self, share_id: str, org_id: str, *, actor: str) -> None:
        with self._db.session() as s:
            row = s.get(ShareLinkRow, share_id)
            if row is None or row.org_id != org_id:
                raise NotFoundError("share link", share_id)
            if row.revoked_at is None:
                row.revoked_at = now()
                audit(
                    s, actor=actor, action="share.revoked", entity_type="report",
                    entity_id=row.report_id, org_id=org_id, details={"share_id": share_id},
                )  # fmt: skip

    def open(self, token: str) -> str | None:
        """The report id a live link points at (and count the view), else None."""
        with self._db.session() as s:
            row = s.execute(
                select(ShareLinkRow).where(ShareLinkRow.token_hash == hash_secret(token))
            ).scalar_one_or_none()
            if row is None or row.revoked_at is not None or _aware(row.expires_at) <= now():  # type: ignore[operator]
                return None
            org = s.get(OrganisationRow, row.org_id)
            if org is None or org.deleted_at is not None or org.status != "active":
                return None  # a switched-off organisation shares nothing
            row.views += 1
            row.last_viewed_at = now()
            return str(row.report_id)

    @staticmethod
    def _out(row: ShareLinkRow) -> dict[str, Any]:
        expired = _aware(row.expires_at) <= now()  # type: ignore[operator]
        return {
            "id": row.id,
            "report_id": row.report_id,
            "created_by": row.created_by,
            "created_at": row.created_at,
            "expires_at": row.expires_at,
            "state": "revoked" if row.revoked_at else "expired" if expired else "live",
            "views": row.views,
            "last_viewed_at": row.last_viewed_at,
        }
