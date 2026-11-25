"""
Data lifecycle: export what an organisation or person holds, and erase it when asked.

* ``export_org`` / ``export_user``: everything held, as JSON files in a zip (documents optionally).
* ``erase_case``: permanent deletion of one case and everything under it, including the stored PDFs
  (a file is removed only if no other case still holds the identical file).
* ``delete_org``: the organisation stops working immediately (sign-in, tokens and sessions refused)
  and its data stays for a grace period; ``purge_org`` then erases it for good.

Erasure removes rows that are normally append-only, so it goes through
``db.maintenance.append_only_lifted`` and always leaves an audit event behind that names what was
erased (counts and identifiers only).
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date, datetime
from typing import Any

from sqlalchemy import delete, func, select

from ipo_engine.screening.db.base import Database
from ipo_engine.screening.db.maintenance import append_only_lifted
from ipo_engine.screening.db.models import (
    ApiTokenRow,
    AuditEventRow,
    CaseDataVersionRow,
    CaseRow,
    CommentRow,
    DocumentRow,
    ExtractionRunRow,
    FieldResultRow,
    HumanReviewEventRow,
    HumanReviewRow,
    IdentityRow,
    InvitationRow,
    MembershipRow,
    NotificationRow,
    OrganisationRow,
    ReportRow,
    ReviewItemEventRow,
    ReviewItemRow,
    SavedFilterRow,
    SessionRow,
    ShareLinkRow,
    UserRow,
    WebhookDeliveryRow,
    WebhookRow,
)
from ipo_engine.screening.db.repositories import audit
from ipo_engine.screening.models.exceptions import NotFoundError
from ipo_engine.screening.services.accounts import AccountError, now
from ipo_engine.screening.services.file_store import FileStore

EXPORT_FORMAT = 1


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, bytes):
        return None
    return value


def row_dict(row: Any, *, skip: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        c.name: _jsonable(getattr(row, c.name)) for c in row.__table__.columns if c.name not in skip
    }


class LifecycleService:
    def __init__(self, db: Database, files: FileStore) -> None:
        self._db = db
        self._files = files

    # ----------------------------------------------------------------- export
    def export_org(self, org_id: str, *, actor: str, include_files: bool = False) -> bytes:
        buf = io.BytesIO()
        with self._db.session() as s, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            org = s.get(OrganisationRow, org_id)
            if org is None:
                raise NotFoundError("organisation", org_id)
            case_ids = list(s.execute(select(CaseRow.id).where(CaseRow.org_id == org_id)).scalars())

            def put(name: str, rows: list[Any], **kw: Any) -> int:
                z.writestr(name, json.dumps([row_dict(r, **kw) for r in rows], indent=1))
                return len(rows)

            def in_cases(model: Any, col: Any) -> list[Any]:
                return list(s.execute(select(model).where(col.in_(case_ids))).scalars())

            counts: dict[str, int] = {}
            counts["cases"] = put(
                "cases.json",
                list(s.execute(select(CaseRow).where(CaseRow.org_id == org_id)).scalars()),
            )
            counts["case_data_versions"] = put(
                "case_data_versions.json", in_cases(CaseDataVersionRow, CaseDataVersionRow.case_id)
            )
            docs = in_cases(DocumentRow, DocumentRow.case_id)
            counts["documents"] = put("documents.json", docs)
            runs = list(
                s.execute(
                    select(ExtractionRunRow).where(
                        ExtractionRunRow.document_id.in_([d.id for d in docs])
                    )
                ).scalars()
            )
            counts["extraction_runs"] = put("extraction_runs.json", runs)
            counts["field_results"] = put(
                "field_results.json",
                list(
                    s.execute(
                        select(FieldResultRow).where(
                            FieldResultRow.run_id.in_([r.id for r in runs])
                        )
                    ).scalars()
                ),
            )
            items = in_cases(ReviewItemRow, ReviewItemRow.case_id)
            counts["review_items"] = put("review_items.json", items)
            counts["review_item_events"] = put(
                "review_item_events.json",
                list(
                    s.execute(
                        select(ReviewItemEventRow).where(
                            ReviewItemEventRow.item_id.in_([i.id for i in items])
                        )
                    ).scalars()
                ),
            )
            reports = in_cases(ReportRow, ReportRow.case_id)
            counts["reports"] = put("reports.json", reports)
            counts["comments"] = put("comments.json", in_cases(CommentRow, CommentRow.case_id))
            counts["webhooks"] = put(
                "webhooks.json",
                list(s.execute(select(WebhookRow).where(WebhookRow.org_id == org_id)).scalars()),
            )
            counts["audit_events"] = put(
                "audit_events.json",
                list(
                    s.execute(
                        select(AuditEventRow)
                        .where(AuditEventRow.org_id == org_id)
                        .order_by(AuditEventRow.id)
                    ).scalars()
                ),
            )
            members = s.execute(
                select(MembershipRow, UserRow)
                .join(UserRow, UserRow.id == MembershipRow.user_id)
                .where(MembershipRow.org_id == org_id)
            ).all()
            z.writestr(
                "members.json",
                json.dumps(
                    [
                        {"user_id": u.id, "email": u.email, "name": u.name, "role": m.role}
                        for m, u in members
                    ],
                    indent=1,
                ),
            )
            counts["members"] = len(members)
            if include_files:
                seen: set[str] = set()
                for d in docs:
                    if d.sha256 not in seen and (data := self._files.get(d.sha256)) is not None:
                        z.writestr(f"files/{d.sha256}.pdf", data)
                        seen.add(d.sha256)
                counts["files"] = len(seen)
            z.writestr(
                "manifest.json",
                json.dumps(
                    {
                        "format": EXPORT_FORMAT,
                        "organisation": {"id": org.id, "name": org.name},
                        "exported_at": now().isoformat(),
                        "counts": counts,
                    },
                    indent=1,
                ),
            )
            audit(
                s, actor=actor, action="org.exported", entity_type="organisation",
                entity_id=org_id, org_id=org_id, details={"counts": counts, "files": include_files},
            )  # fmt: skip
        return buf.getvalue()

    def export_user(self, user_id: str) -> dict[str, Any]:
        with self._db.session() as s:
            user = s.get(UserRow, user_id)
            if user is None:
                raise NotFoundError("user", user_id)
            memberships = s.execute(
                select(MembershipRow, OrganisationRow)
                .join(OrganisationRow, OrganisationRow.id == MembershipRow.org_id)
                .where(MembershipRow.user_id == user_id)
            ).all()
            return {
                "user": row_dict(user),
                "organisations": [
                    {"id": o.id, "name": o.name, "role": m.role} for m, o in memberships
                ],
                "identities": [
                    row_dict(i)
                    for i in s.execute(
                        select(IdentityRow).where(IdentityRow.user_id == user_id)
                    ).scalars()
                ],
                "tokens": [
                    row_dict(t, skip=("token_hash",))
                    for t in s.execute(
                        select(ApiTokenRow).where(ApiTokenRow.user_id == user_id)
                    ).scalars()
                ],
                "sessions": [
                    row_dict(r, skip=("id", "csrf_token"))
                    for r in s.execute(
                        select(SessionRow).where(SessionRow.user_id == user_id)
                    ).scalars()
                ],
                "activity": [
                    row_dict(a)
                    for a in s.execute(
                        select(AuditEventRow)
                        .where(AuditEventRow.actor == user_id)
                        .order_by(AuditEventRow.id)
                    ).scalars()
                ],
            }

    # ----------------------------------------------------------------- erasure
    def erase_case(self, case_id: str, org_id: str, *, actor: str, confirm: str) -> dict[str, int]:
        """Permanently delete a case and everything under it. ``confirm`` must be its name."""
        with self._db.session() as s:
            case = s.get(CaseRow, case_id)
            if case is None or case.org_id != org_id:
                raise NotFoundError("case", case_id)
            if confirm.strip() != case.company_name:
                raise AccountError("To erase a case, type its exact company name as confirmation.")
            removed, orphans = self._erase(s, case_id)
            audit(
                s, actor=actor, action="case.erased", entity_type="case", entity_id=case_id,
                org_id=org_id, details={"removed": removed},
            )  # fmt: skip
        for sha in orphans:  # after the commit: a failed erase must not lose a file
            self._files.delete(sha)
        return removed

    def _erase(self, s: Any, case_id: str) -> tuple[dict[str, int], list[str]]:
        docs = list(s.execute(select(DocumentRow).where(DocumentRow.case_id == case_id)).scalars())
        doc_ids = [d.id for d in docs]
        shas = {d.sha256 for d in docs}
        run_ids = list(
            s.execute(
                select(ExtractionRunRow.id).where(ExtractionRunRow.document_id.in_(doc_ids))
            ).scalars()
        )
        report_ids = list(
            s.execute(select(ReportRow.report_id).where(ReportRow.case_id == case_id)).scalars()
        )
        review_ids = list(
            s.execute(
                select(HumanReviewRow.review_id).where(HumanReviewRow.report_id.in_(report_ids))
            ).scalars()
        )
        item_ids = list(
            s.execute(select(ReviewItemRow.id).where(ReviewItemRow.case_id == case_id)).scalars()
        )
        counts: dict[str, int] = {}

        def kill(name: str, stmt: Any) -> None:
            result: Any = s.execute(stmt)
            counts[name] = int(result.rowcount or 0)

        with append_only_lifted(s):
            kill(
                "human_review_events",
                delete(HumanReviewEventRow).where(HumanReviewEventRow.review_id.in_(review_ids)),
            )
            kill(
                "review_item_events",
                delete(ReviewItemEventRow).where(ReviewItemEventRow.item_id.in_(item_ids)),
            )
            kill(
                "case_data_versions",
                delete(CaseDataVersionRow).where(CaseDataVersionRow.case_id == case_id),
            )
        kill(
            "human_reviews", delete(HumanReviewRow).where(HumanReviewRow.review_id.in_(review_ids))
        )
        kill("share_links", delete(ShareLinkRow).where(ShareLinkRow.report_id.in_(report_ids)))
        kill("comments", delete(CommentRow).where(CommentRow.case_id == case_id))
        kill("reports", delete(ReportRow).where(ReportRow.case_id == case_id))
        kill("review_items", delete(ReviewItemRow).where(ReviewItemRow.case_id == case_id))
        kill("field_results", delete(FieldResultRow).where(FieldResultRow.run_id.in_(run_ids)))
        kill("extraction_runs", delete(ExtractionRunRow).where(ExtractionRunRow.id.in_(run_ids)))
        kill("documents", delete(DocumentRow).where(DocumentRow.case_id == case_id))
        kill("cases", delete(CaseRow).where(CaseRow.id == case_id))
        orphans = [
            sha
            for sha in shas
            if s.execute(
                select(func.count()).select_from(DocumentRow).where(DocumentRow.sha256 == sha)
            ).scalar_one()
            == 0
        ]
        return counts, orphans

    # ------------------------------------------------------------ organisations
    def delete_org(self, org_id: str, *, actor: str, confirm: str) -> None:
        """Switch an organisation off now. Its data stays until ``purge_org``."""
        with self._db.session() as s:
            org = s.get(OrganisationRow, org_id)
            if org is None or org.deleted_at is not None:
                raise NotFoundError("organisation", org_id)
            if confirm.strip() != org.name:
                raise AccountError(
                    "To delete an organisation, type its exact name as confirmation."
                )
            org.deleted_at, org.status = now(), "deleted"
            stamp = now()
            for row in s.execute(
                select(SessionRow).where(
                    SessionRow.org_id == org_id, SessionRow.revoked_at.is_(None)
                )
            ).scalars():
                row.revoked_at = stamp
            for tok in s.execute(
                select(ApiTokenRow).where(
                    ApiTokenRow.org_id == org_id, ApiTokenRow.revoked_at.is_(None)
                )
            ).scalars():
                tok.revoked_at = stamp
            audit(
                s, actor=actor, action="org.deleted", entity_type="organisation",
                entity_id=org_id, org_id=org_id,
            )  # fmt: skip

    def purge_org(self, org_id: str, *, actor: str) -> dict[str, int]:
        """Erase a deleted organisation's cases, memberships and tokens for good."""
        total: dict[str, int] = {}
        orphans: list[str] = []
        with self._db.session() as s:
            org = s.get(OrganisationRow, org_id)
            if org is None:
                raise NotFoundError("organisation", org_id)
            if org.deleted_at is None:
                raise AccountError("Delete the organisation first; purge only follows a deletion.")
            for cid in list(
                s.execute(select(CaseRow.id).where(CaseRow.org_id == org_id)).scalars()
            ):
                removed, more = self._erase(s, cid)
                orphans += more
                for k, v in removed.items():
                    total[k] = total.get(k, 0) + v
            for model in (
                SessionRow,
                ApiTokenRow,
                InvitationRow,
                MembershipRow,
                NotificationRow,
                SavedFilterRow,
                WebhookDeliveryRow,
                WebhookRow,
                ShareLinkRow,
            ):
                result: Any = s.execute(delete(model).where(model.org_id == org_id))
                total[model.__tablename__] = total.get(model.__tablename__, 0) + int(
                    result.rowcount or 0
                )
            s.delete(org)
            audit(
                s, actor=actor, action="org.purged", entity_type="organisation",
                entity_id=org_id, org_id=org_id, details={"removed": total},
            )  # fmt: skip
        for sha in set(orphans):
            self._files.delete(sha)
        return total


__all__ = ["LifecycleService", "row_dict"]
