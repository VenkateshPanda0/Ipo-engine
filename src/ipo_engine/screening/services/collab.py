"""
Working together: assignments, comments, notifications, saved filters, organisation settings, the
getting-started checklist and usage counts. Everything is scoped to an organisation (and, for
notifications and saved filters, to a person) by the caller's identity, never by an id the client
supplies.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select

from ipo_engine.screening.db.base import Database
from ipo_engine.screening.db.models import (
    ApiTokenRow,
    AuditEventRow,
    CaseRow,
    CommentRow,
    DocumentRow,
    InvitationRow,
    MembershipRow,
    NotificationRow,
    OrganisationRow,
    ReportRow,
    SavedFilterRow,
    UserRow,
)
from ipo_engine.screening.db.repositories import audit
from ipo_engine.screening.models.exceptions import NotFoundError
from ipo_engine.screening.services.accounts import AccountError, now

#: organisation settings that exist, with their type and default
SETTINGS: dict[str, tuple[type, Any]] = {
    "four_eyes": (bool, False),  # the person who ran a screening cannot also sign it off
    "webhooks_enabled": (bool, True),
}
MAX_COMMENT = 5000
SAVED_SCOPES = ("cases", "reports")
MAX_SAVED = 50


class CollabService:
    def __init__(self, db: Database) -> None:
        self._db = db

    # ------------------------------------------------------------ assignment
    def assign(
        self, case_id: str, org_id: str, assignee_id: str | None, *, actor: str
    ) -> dict[str, Any]:
        with self._db.session() as s:
            case = s.get(CaseRow, case_id)
            if case is None or case.org_id != org_id:
                raise NotFoundError("case", case_id)
            if assignee_id is not None:
                member = s.execute(
                    select(MembershipRow.id).where(
                        MembershipRow.org_id == org_id, MembershipRow.user_id == assignee_id
                    )
                ).first()
                if member is None:
                    raise AccountError("Cases can only be assigned to members of the organisation.")
            before, case.assignee_id = case.assignee_id, assignee_id
            case.updated_at = now()
            audit(
                s, actor=actor, action="case.assigned", entity_type="case", entity_id=case_id,
                case_id=case_id, details={"from": before, "to": assignee_id},
            )  # fmt: skip
            if assignee_id and assignee_id != actor:
                self._notify(
                    s, assignee_id, org_id, "assigned", f"You were assigned {case.company_name}",
                    f"/cases/{case_id}",
                )  # fmt: skip
            return {"case_id": case_id, "assignee_id": assignee_id}

    # -------------------------------------------------------------- comments
    def add_comment(self, case_id: str, org_id: str, author_id: str, body: str) -> dict[str, Any]:
        body = body.strip()
        if not body:
            raise AccountError("A comment cannot be empty.")
        if len(body) > MAX_COMMENT:
            raise AccountError(f"A comment is limited to {MAX_COMMENT} characters.")
        with self._db.session() as s:
            case = s.get(CaseRow, case_id)
            if case is None or case.org_id != org_id:
                raise NotFoundError("case", case_id)
            row = CommentRow(
                id=str(uuid4()), case_id=case_id, org_id=org_id, author_id=author_id, body=body
            )
            s.add(row)
            s.flush()
            audit(
                s, actor=author_id, action="comment.added", entity_type="comment",
                entity_id=row.id, case_id=case_id,
            )  # fmt: skip
            for person in {case.assignee_id, case.created_by} - {None, author_id}:
                if person and self._is_member(s, org_id, person):
                    self._notify(
                        s, person, org_id, "comment", f"New comment on {case.company_name}",
                        f"/cases/{case_id}",
                    )  # fmt: skip
            return self._comment_out(s, row)

    def comments(self, case_id: str, org_id: str) -> list[dict[str, Any]]:
        with self._db.session() as s:
            case = s.get(CaseRow, case_id)
            if case is None or case.org_id != org_id:
                raise NotFoundError("case", case_id)
            rows = (
                s.execute(
                    select(CommentRow)
                    .where(CommentRow.case_id == case_id, CommentRow.deleted_at.is_(None))
                    .order_by(CommentRow.created_at)
                )
                .scalars()
                .all()
            )
            return [self._comment_out(s, r) for r in rows]

    def delete_comment(
        self, case_id: str, comment_id: str, org_id: str, *, actor: str, is_admin: bool
    ) -> None:
        with self._db.session() as s:
            row = s.get(CommentRow, comment_id)
            if row is None or row.case_id != case_id or row.org_id != org_id or row.deleted_at:
                raise NotFoundError("comment", comment_id)
            if row.author_id != actor and not is_admin:
                raise AccountError("Only the author or an admin can delete a comment.")
            row.deleted_at = now()
            audit(
                s, actor=actor, action="comment.deleted", entity_type="comment",
                entity_id=comment_id, case_id=case_id,
            )  # fmt: skip

    @staticmethod
    def _comment_out(s: Any, row: CommentRow) -> dict[str, Any]:
        author = s.get(UserRow, row.author_id)
        return {
            "id": row.id,
            "case_id": row.case_id,
            "author_id": row.author_id,
            "author": (author.name or author.email) if author else row.author_id,
            "body": row.body,
            "created_at": row.created_at,
        }

    # --------------------------------------------------------- notifications
    @staticmethod
    def _is_member(s: Any, org_id: str, user_id: str) -> bool:
        return (
            s.execute(
                select(MembershipRow.id).where(
                    MembershipRow.org_id == org_id, MembershipRow.user_id == user_id
                )
            ).first()
            is not None
        )

    @staticmethod
    def _notify(s: Any, user_id: str, org_id: str, kind: str, title: str, link: str) -> None:
        s.add(
            NotificationRow(
                id=str(uuid4()), user_id=user_id, org_id=org_id, kind=kind, title=title, link=link
            )
        )

    def notify(self, user_id: str, org_id: str, kind: str, title: str, link: str | None) -> None:
        with self._db.session() as s:
            s.add(
                NotificationRow(
                    id=str(uuid4()),
                    user_id=user_id,
                    org_id=org_id,
                    kind=kind,
                    title=title,
                    link=link,
                )
            )

    def notifications(
        self, user_id: str, org_id: str, *, unread_only: bool = False, limit: int = 50
    ) -> dict[str, Any]:
        with self._db.session() as s:
            base = select(NotificationRow).where(
                NotificationRow.user_id == user_id, NotificationRow.org_id == org_id
            )
            unread = s.execute(
                select(func.count()).select_from(
                    base.where(NotificationRow.read_at.is_(None)).subquery()
                )
            ).scalar_one()
            if unread_only:
                base = base.where(NotificationRow.read_at.is_(None))
            rows = s.execute(
                base.order_by(NotificationRow.created_at.desc()).limit(limit)
            ).scalars()
            return {
                "unread": int(unread),
                "items": [
                    {
                        "id": n.id,
                        "kind": n.kind,
                        "title": n.title,
                        "link": n.link,
                        "created_at": n.created_at,
                        "read": n.read_at is not None,
                    }
                    for n in rows
                ],
            }

    def mark_read(self, user_id: str, org_id: str, notification_id: str | None) -> int:
        """Mark one notification (or all, if ``notification_id`` is None) read; returns how many."""
        with self._db.session() as s:
            stmt = select(NotificationRow).where(
                NotificationRow.user_id == user_id,
                NotificationRow.org_id == org_id,
                NotificationRow.read_at.is_(None),
            )
            if notification_id:
                stmt = stmt.where(NotificationRow.id == notification_id)
            rows = list(s.execute(stmt).scalars())
            if notification_id and not rows:
                raise NotFoundError("notification", notification_id)
            for n in rows:
                n.read_at = now()
            return len(rows)

    # --------------------------------------------------------- saved filters
    def save_filter(
        self, user_id: str, org_id: str, name: str, scope: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        name = name.strip()
        if not 1 <= len(name) <= 100:
            raise AccountError("A saved search needs a name of 1 to 100 characters.")
        if scope not in SAVED_SCOPES:
            raise AccountError(f"Scope must be one of {', '.join(SAVED_SCOPES)}.")
        allowed = {"status", "q", "assignee", "mine"}
        if set(params) - allowed or any(not isinstance(v, str | bool) for v in params.values()):
            raise AccountError("A saved search can only hold status, q, assignee and mine.")
        with self._db.session() as s:
            count = s.execute(
                select(func.count())
                .select_from(SavedFilterRow)
                .where(SavedFilterRow.user_id == user_id, SavedFilterRow.org_id == org_id)
            ).scalar_one()
            row = s.execute(
                select(SavedFilterRow).where(
                    SavedFilterRow.user_id == user_id,
                    SavedFilterRow.org_id == org_id,
                    SavedFilterRow.name == name,
                )
            ).scalar_one_or_none()
            if row is None:
                if count >= MAX_SAVED:
                    raise AccountError(f"You can keep at most {MAX_SAVED} saved searches.")
                row = SavedFilterRow(
                    id=str(uuid4()), user_id=user_id, org_id=org_id, name=name, scope=scope,
                    params=params,
                )  # fmt: skip
                s.add(row)
            else:
                row.scope, row.params = scope, params
            s.flush()
            return self._filter_out(row)

    def saved_filters(self, user_id: str, org_id: str) -> list[dict[str, Any]]:
        with self._db.session() as s:
            rows = s.execute(
                select(SavedFilterRow)
                .where(SavedFilterRow.user_id == user_id, SavedFilterRow.org_id == org_id)
                .order_by(SavedFilterRow.name)
            ).scalars()
            return [self._filter_out(r) for r in rows]

    def delete_filter(self, user_id: str, org_id: str, filter_id: str) -> None:
        with self._db.session() as s:
            row = s.get(SavedFilterRow, filter_id)
            if row is None or row.user_id != user_id or row.org_id != org_id:
                raise NotFoundError("saved search", filter_id)
            s.delete(row)

    @staticmethod
    def _filter_out(row: SavedFilterRow) -> dict[str, Any]:
        return {"id": row.id, "name": row.name, "scope": row.scope, "params": row.params}

    # -------------------------------------------------------------- settings
    def settings(self, org_id: str) -> dict[str, Any]:
        with self._db.session() as s:
            org = s.get(OrganisationRow, org_id)
            if org is None:
                raise NotFoundError("organisation", org_id)
            stored = org.settings or {}
            return {k: stored.get(k, default) for k, (_t, default) in SETTINGS.items()}

    def update_settings(
        self, org_id: str, changes: dict[str, Any], *, actor: str
    ) -> dict[str, Any]:
        for key, value in changes.items():
            if key not in SETTINGS:
                raise AccountError(f"Unknown setting {key!r}.")
            if not isinstance(value, SETTINGS[key][0]):
                raise AccountError(f"Setting {key!r} must be {SETTINGS[key][0].__name__}.")
        with self._db.session() as s:
            org = s.get(OrganisationRow, org_id)
            if org is None:
                raise NotFoundError("organisation", org_id)
            org.settings = {**(org.settings or {}), **changes}
            audit(
                s, actor=actor, action="org.settings_changed", entity_type="organisation",
                entity_id=org_id, org_id=org_id, details=changes,
            )  # fmt: skip
        return self.settings(org_id)

    def report_creator(self, report_id: str) -> str | None:
        with self._db.session() as s:
            return s.execute(
                select(ReportRow.created_by).where(ReportRow.report_id == report_id)
            ).scalar_one_or_none()

    # ------------------------------------------------------------ onboarding
    def onboarding(self, org_id: str, user_id: str) -> dict[str, Any]:
        with self._db.session() as s:
            org = s.get(OrganisationRow, org_id)
            if org is None:
                raise NotFoundError("organisation", org_id)

            def n(model: Any, *where: Any) -> int:
                return int(
                    s.execute(select(func.count()).select_from(model).where(*where)).scalar_one()
                )

            cases = n(CaseRow, CaseRow.org_id == org_id)
            docs = s.execute(
                select(func.count())
                .select_from(DocumentRow)
                .join(CaseRow, CaseRow.id == DocumentRow.case_id)
                .where(CaseRow.org_id == org_id)
            ).scalar_one()
            reports = s.execute(
                select(func.count())
                .select_from(ReportRow)
                .join(CaseRow, CaseRow.id == ReportRow.case_id)
                .where(CaseRow.org_id == org_id)
            ).scalar_one()
            members = n(MembershipRow, MembershipRow.org_id == org_id)
            invites = n(InvitationRow, InvitationRow.org_id == org_id)
            tokens = n(ApiTokenRow, ApiTokenRow.org_id == org_id, ApiTokenRow.user_id == user_id)
            steps = [
                ("create_case", "Create your first case", cases > 0, "/"),
                ("upload_document", "Upload an offer document", docs > 0, "/"),
                ("run_screening", "Run a screening", reports > 0, "/"),
                ("invite_teammate", "Invite a teammate", members > 1 or invites > 0, "/settings"),
                ("create_token", "Create an API token (optional)", tokens > 0, "/settings"),
            ]
            return {
                "organisation": org.name,
                "steps": [
                    {"id": i, "title": t, "done": d, "link": link} for i, t, d, link in steps
                ],
                "complete": all(d for _, _, d, _ in steps[:4]),
            }

    # ----------------------------------------------------------------- usage
    def usage(self, org_id: str, *, days: int = 30) -> dict[str, Any]:
        since = now() - timedelta(days=days)
        with self._db.session() as s:

            def n(stmt: Any) -> int:
                return int(s.execute(stmt).scalar_one() or 0)

            return {
                "period_days": days,
                "cases_total": n(
                    select(func.count()).select_from(CaseRow).where(CaseRow.org_id == org_id)
                ),
                "documents_uploaded": n(
                    select(func.count())
                    .select_from(DocumentRow)
                    .join(CaseRow, CaseRow.id == DocumentRow.case_id)
                    .where(CaseRow.org_id == org_id, DocumentRow.created_at >= since)
                ),
                "pages_processed": n(
                    select(func.coalesce(func.sum(DocumentRow.page_count), 0))
                    .select_from(DocumentRow)
                    .join(CaseRow, CaseRow.id == DocumentRow.case_id)
                    .where(CaseRow.org_id == org_id, DocumentRow.created_at >= since)
                ),
                "screenings_run": n(
                    select(func.count())
                    .select_from(ReportRow)
                    .join(CaseRow, CaseRow.id == ReportRow.case_id)
                    .where(CaseRow.org_id == org_id, ReportRow.created_at >= since)
                ),
                "members": n(
                    select(func.count())
                    .select_from(MembershipRow)
                    .where(MembershipRow.org_id == org_id)
                ),
                "audit_events": n(
                    select(func.count())
                    .select_from(AuditEventRow)
                    .where(AuditEventRow.org_id == org_id, AuditEventRow.ts >= since)
                ),
            }
