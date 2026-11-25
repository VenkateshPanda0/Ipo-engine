"""
Case workflow services: cases, data versions, field corrections and screening.

Case data is stored as immutable, numbered versions of a CompanyData-shaped JSON
payload. Every manual edit, extraction merge or review resolution creates a new
version; a screening report records the exact version it evaluated. Original
extracted values are never overwritten in place.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ipo_engine.screening.core.constants import DEFAULT_ORG_ID
from ipo_engine.screening.db.base import Database
from ipo_engine.screening.db.models import (
    AuditEventRow,
    CaseDataVersionRow,
    CaseRow,
    DocumentRow,
    ReportRow,
    ReviewItemEventRow,
    ReviewItemRow,
)
from ipo_engine.screening.db.repositories import (
    audit,
    latest_version,
    next_version_number,
)
from ipo_engine.screening.models.company_data import CompanyData
from ipo_engine.screening.models.enums import (
    ExtractionMethod,
    FieldStatus,
    ListingRoute,
)
from ipo_engine.screening.models.exceptions import InvalidStateError, NotFoundError
from ipo_engine.screening.models.extracted_value import ExtractedValue
from ipo_engine.screening.models.field_paths import (
    get_value,
    set_value,
    set_value_in_place,
    value_type,
)
from ipo_engine.screening.services.case_screening import (
    CaseScreeningService,
    dashboard,
)
from ipo_engine.screening.services.case_values import (
    CaseStatus,
    ReviewItemStatus,
    is_human_value,
    manual_value,
    parse_field_value,
    refresh_case_status,
)

__all__ = [
    "CaseScreeningService",
    "CaseService",
    "CaseStatus",
    "ReviewItemStatus",
    "dashboard",
    "is_human_value",
    "parse_field_value",
]


class CaseService:
    """Create cases and manage their versioned data."""

    def __init__(self, db: Database) -> None:
        self._db = db

    # -- cases --------------------------------------------------------------

    def create(
        self,
        *,
        company_name: str,
        listing_route: ListingRoute,
        actor: str,
        notes: str | None = None,
        org_id: str = DEFAULT_ORG_ID,
    ) -> dict[str, Any]:
        case_id = str(uuid4())
        # Store only what was provided: schema defaults are not facts.
        payload = CompanyData.model_validate(
            {
                "identification": {"company_name": company_name},
                "issue_details": {"listing_route": listing_route.value},
            }
        ).model_dump(mode="json", exclude_unset=True)
        with self._db.session() as s:
            s.add(
                CaseRow(
                    id=case_id,
                    org_id=org_id,
                    company_name=company_name,
                    listing_route=listing_route.value,
                    status=CaseStatus.DRAFT.value,
                    current_version=1,
                    notes=notes,
                    created_by=actor,
                )
            )
            s.flush()
            s.add(
                CaseDataVersionRow(
                    case_id=case_id,
                    version=1,
                    payload=payload,
                    source="created",
                    created_by=actor,
                    reason="case created",
                )
            )
            audit(
                s,
                actor=actor,
                action="case.created",
                entity_type="case",
                entity_id=case_id,
                case_id=case_id,
                details={"listing_route": listing_route.value},
            )
        return self.get(case_id)

    def _row(self, s: Session, case_id: str) -> CaseRow:
        row = s.get(CaseRow, case_id)
        if row is None:
            raise NotFoundError("case", case_id)
        return row

    @staticmethod
    def _out(row: CaseRow, counts: dict[str, int] | None = None) -> dict[str, Any]:
        return {
            "id": row.id,
            "company_name": row.company_name,
            "listing_route": row.listing_route,
            "status": row.status,
            "assignee_id": row.assignee_id,
            "current_version": row.current_version,
            "notes": row.notes,
            "created_by": row.created_by,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            **(counts or {}),
        }

    def get(self, case_id: str) -> dict[str, Any]:
        with self._db.session() as s:
            row = self._row(s, case_id)
            return self._out(row, self._counts(s, case_id))

    @staticmethod
    def _counts(s: Any, case_id: str) -> dict[str, int]:
        docs = s.execute(
            select(func.count()).select_from(DocumentRow).where(DocumentRow.case_id == case_id)
        ).scalar_one()
        open_items = s.execute(
            select(func.count())
            .select_from(ReviewItemRow)
            .where(
                ReviewItemRow.case_id == case_id,
                ReviewItemRow.status == ReviewItemStatus.OPEN.value,
            )
        ).scalar_one()
        reports = s.execute(
            select(func.count()).select_from(ReportRow).where(ReportRow.case_id == case_id)
        ).scalar_one()
        return {
            "document_count": int(docs),
            "open_review_items": int(open_items),
            "report_count": int(reports),
        }

    @staticmethod
    def _counts_many(s: Any, case_ids: list[str]) -> dict[str, dict[str, int]]:
        """Document / open-item / report counts for many cases in three grouped queries."""
        out = {
            cid: {"document_count": 0, "open_review_items": 0, "report_count": 0}
            for cid in case_ids
        }
        if not case_ids:
            return out
        queries = (
            ("document_count", DocumentRow.case_id, select(DocumentRow.case_id, func.count())),
            (
                "open_review_items",
                ReviewItemRow.case_id,
                select(ReviewItemRow.case_id, func.count()).where(
                    ReviewItemRow.status == ReviewItemStatus.OPEN.value
                ),
            ),
            ("report_count", ReportRow.case_id, select(ReportRow.case_id, func.count())),
        )
        for key, column, stmt in queries:
            for cid, n in s.execute(stmt.where(column.in_(case_ids)).group_by(column)):
                out[cid][key] = int(n)
        return out

    def list_cases(
        self,
        *,
        org_id: str,
        status: str | None = None,
        q: str | None = None,
        assignee_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        with self._db.session() as s:
            stmt = select(CaseRow).where(CaseRow.org_id == org_id)
            if assignee_id:
                stmt = stmt.where(CaseRow.assignee_id == assignee_id)
            if status:
                stmt = stmt.where(CaseRow.status == status)
            if q:
                escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                stmt = stmt.where(CaseRow.company_name.ilike(f"%{escaped}%", escape="\\"))
            total = s.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
            rows = (
                s.execute(stmt.order_by(CaseRow.updated_at.desc()).limit(limit).offset(offset))
                .scalars()
                .all()
            )
            counts = self._counts_many(s, [r.id for r in rows])
            return {
                "items": [self._out(r, counts[r.id]) for r in rows],
                "total": int(total),
                "limit": limit,
                "offset": offset,
            }

    def update(
        self,
        case_id: str,
        *,
        actor: str,
        company_name: str | None = None,
        listing_route: ListingRoute | None = None,
        notes: str | None = None,
        archived: bool | None = None,
    ) -> dict[str, Any]:
        changes: dict[str, Any] = {}
        with self._db.session() as s:
            row = self._row(s, case_id)
            if company_name is not None and company_name != row.company_name:
                changes["company_name"] = company_name
            if listing_route is not None and listing_route.value != row.listing_route:
                changes["listing_route"] = listing_route.value
            if notes is not None:
                row.notes = notes
            if archived is not None:
                row.status = CaseStatus.ARCHIVED.value if archived else CaseStatus.DRAFT.value
                changes["archived"] = archived
            if "company_name" in changes or "listing_route" in changes:
                payload = latest_version(s, case_id).payload  # type: ignore[union-attr]
                if "company_name" in changes:
                    payload = {
                        **payload,
                        "identification": {
                            **payload.get("identification", {}),
                            "company_name": company_name,
                        },
                    }
                    row.company_name = company_name  # type: ignore[assignment]
                if "listing_route" in changes:
                    payload = {
                        **payload,
                        "issue_details": {
                            **payload.get("issue_details", {}),
                            "listing_route": changes["listing_route"],
                        },
                    }
                    row.listing_route = changes["listing_route"]
                self._new_version(
                    s, row, payload, source="metadata", actor=actor, reason="case metadata updated"
                )
            if archived is False:
                s.flush()
                self._refresh_status(s, row)  # restore the status the case's state implies
            row.updated_at = datetime.now(tz=UTC)
            audit(
                s,
                actor=actor,
                action="case.updated",
                entity_type="case",
                entity_id=case_id,
                case_id=case_id,
                details={k: str(v) for k, v in changes.items()},
            )
        return self.get(case_id)

    # -- data versions ------------------------------------------------------------

    @staticmethod
    def _new_version(
        s: Any,
        row: CaseRow,
        payload: dict[str, Any],
        *,
        source: str,
        actor: str,
        reason: str | None = None,
        document_id: str | None = None,
        run_id: str | None = None,
    ) -> int:
        CompanyData.model_validate(payload)  # never persist an invalid snapshot
        version = next_version_number(s, row.id)
        s.add(
            CaseDataVersionRow(
                case_id=row.id,
                version=version,
                payload=payload,
                source=source,
                created_by=actor,
                reason=reason,
                document_id=document_id,
                extraction_run_id=run_id,
            )
        )
        row.current_version = version
        row.updated_at = datetime.now(tz=UTC)
        return version

    def data(self, case_id: str, version: int | None = None) -> dict[str, Any]:
        with self._db.session() as s:
            self._row(s, case_id)
            if version is None:
                v = latest_version(s, case_id)
            else:
                v = s.execute(
                    select(CaseDataVersionRow).where(
                        CaseDataVersionRow.case_id == case_id, CaseDataVersionRow.version == version
                    )
                ).scalar_one_or_none()
            if v is None:
                raise NotFoundError("case data version", f"{case_id}@{version}")
            return {
                "case_id": case_id,
                "version": v.version,
                "source": v.source,
                "reason": v.reason,
                "created_by": v.created_by,
                "created_at": v.created_at,
                "payload": v.payload,
            }

    def versions(self, case_id: str) -> list[dict[str, Any]]:
        with self._db.session() as s:
            self._row(s, case_id)
            rows = (
                s.execute(
                    select(CaseDataVersionRow)
                    .where(CaseDataVersionRow.case_id == case_id)
                    .order_by(CaseDataVersionRow.version.desc())
                )
                .scalars()
                .all()
            )
            return [
                {
                    "version": r.version,
                    "source": r.source,
                    "reason": r.reason,
                    "created_by": r.created_by,
                    "created_at": r.created_at,
                    "document_id": r.document_id,
                }
                for r in rows
            ]

    def replace_data(
        self, case_id: str, payload: dict[str, Any], *, actor: str, reason: str | None
    ) -> dict[str, Any]:
        """Replace the case data with a manually prepared CompanyData payload."""
        with self._db.session() as s:
            row = self._row(s, case_id)
            if row.status == CaseStatus.ARCHIVED.value:
                raise InvalidStateError("case", row.status, "Archived cases cannot be edited.")
            merged = dict(payload)
            merged["identification"] = {
                **payload.get("identification", {}),
                "company_name": row.company_name,
            }
            merged.setdefault("issue_details", {})
            merged["issue_details"] = {
                **merged["issue_details"],
                "listing_route": row.listing_route,
            }
            normalised = CompanyData.model_validate(merged).model_dump(
                mode="json", exclude_unset=True
            )
            version = self._new_version(
                s,
                row,
                normalised,
                source="manual",
                actor=actor,
                reason=reason or "manual data entry",
            )
            audit(
                s,
                actor=actor,
                action="case.data_replaced",
                entity_type="case",
                entity_id=case_id,
                case_id=case_id,
                details={"version": version},
            )
            self._refresh_status(s, row)
        return self.data(case_id)

    def set_fields(
        self, case_id: str, updates: list[dict[str, Any]], *, actor: str
    ) -> dict[str, Any]:
        """Set individual fields manually. Each update: {field_path, value|null, note}."""
        with self._db.session() as s:
            row = self._row(s, case_id)
            if row.status == CaseStatus.ARCHIVED.value:
                raise InvalidStateError("case", row.status, "Archived cases cannot be edited.")
            # One private copy of the stored (append-only) version, then in-place edits.
            payload = copy.deepcopy(latest_version(s, case_id).payload)  # type: ignore[union-attr]
            changed: list[str] = []
            for upd in updates:
                path = upd["field_path"]
                value_type(path)
                if upd.get("value") is None:
                    set_value_in_place(payload, path, None)
                else:
                    value = parse_field_value(path, upd["value"])
                    set_value_in_place(
                        payload,
                        path,
                        manual_value(path, value, actor, upd.get("note")),
                        period_end=upd.get("period_end"),
                    )
                changed.append(path)
            version = self._new_version(
                s,
                row,
                payload,
                source="manual",
                actor=actor,
                reason=f"manual edit of {len(changed)} field(s)",
            )
            audit(
                s,
                actor=actor,
                action="case.fields_set",
                entity_type="case",
                entity_id=case_id,
                case_id=case_id,
                details={"version": version, "fields": changed},
            )
            self._refresh_status(s, row)
        return self.data(case_id)

    # Kept as a static method of the service for existing callers; the logic lives in case_values.
    _refresh_status = staticmethod(refresh_case_status)

    def history(self, case_id: str, limit: int = 200) -> list[dict[str, Any]]:
        with self._db.session() as s:
            self._row(s, case_id)
            rows = (
                s.execute(
                    select(AuditEventRow)
                    .where(AuditEventRow.case_id == case_id)
                    .order_by(AuditEventRow.id.desc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            return [
                {
                    "ts": r.ts,
                    "actor": r.actor,
                    "action": r.action,
                    "entity_type": r.entity_type,
                    "entity_id": r.entity_id,
                    "details": r.details,
                }
                for r in rows
            ]

    # -- review workspace -----------------------------------------------------------

    def review_items(
        self,
        case_id: str | None = None,
        status: str | None = "open",
        *,
        org_id: str | None,
        item_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Review items with their event history and the case's current value.

        Events are fetched in one query and each case's latest payload is loaded once
        (not once per item).
        """
        with self._db.session() as s:
            stmt = select(ReviewItemRow)
            if org_id is not None:  # None only for a caller that has already authorised the item
                stmt = stmt.join(CaseRow, CaseRow.id == ReviewItemRow.case_id).where(
                    CaseRow.org_id == org_id
                )
            if item_id:
                stmt = stmt.where(ReviewItemRow.id == item_id)
            if case_id:
                stmt = stmt.where(ReviewItemRow.case_id == case_id)
            if status:
                stmt = stmt.where(ReviewItemRow.status == status)
            rows = s.execute(stmt.order_by(ReviewItemRow.created_at)).scalars().all()
            events_by_item: dict[str, list[ReviewItemEventRow]] = {}
            if rows:
                events = s.execute(
                    select(ReviewItemEventRow)
                    .where(ReviewItemEventRow.item_id.in_([r.id for r in rows]))
                    .order_by(ReviewItemEventRow.id)
                ).scalars()
                for e in events:
                    events_by_item.setdefault(e.item_id, []).append(e)
            payloads: dict[str, dict[str, Any]] = {}
            out = []
            for r in rows:
                if r.case_id not in payloads:
                    latest = latest_version(s, r.case_id)
                    payloads[r.case_id] = latest.payload if latest else {}
                current = get_value(payloads[r.case_id], r.field_path)
                out.append(
                    {
                        "id": r.id,
                        "case_id": r.case_id,
                        "document_id": r.document_id,
                        "run_id": r.run_id,
                        "field_path": r.field_path,
                        "reason": r.reason,
                        "field_status": r.field_status,
                        "status": r.status,
                        "proposed": r.proposed,
                        "current": current,
                        "candidates": r.candidates,
                        "created_at": r.created_at,
                        "resolved_at": r.resolved_at,
                        "history": [
                            {
                                "action": e.action,
                                "actor": e.actor,
                                "reason": e.reason,
                                "original_value": e.original_value,
                                "new_value": e.new_value,
                                "data_version": e.data_version,
                                "created_at": e.created_at,
                            }
                            for e in events_by_item.get(r.id, [])
                        ],
                    }
                )
            return out

    def resolve_item(
        self, item_id: str, *, action: str, actor: str, reason: str | None, value: Any = None
    ) -> dict[str, Any]:
        """Confirm, correct, reject or request more evidence for a review item."""
        if action not in ("confirm", "correct", "reject", "request_more_evidence"):
            raise ValueError("action must be confirm, correct, reject or request_more_evidence")
        if action in ("correct", "reject") and not (reason and reason.strip()):
            raise ValueError("A reason is required to correct or reject a value.")
        with self._db.session() as s:
            item = s.get(ReviewItemRow, item_id)
            if item is None:
                raise NotFoundError("review item", item_id)
            if item.status not in (
                ReviewItemStatus.OPEN.value,
                ReviewItemStatus.MORE_EVIDENCE_REQUESTED.value,
            ):
                raise InvalidStateError(
                    "review item", item.status, "This review item is already resolved."
                )
            case = self._row(s, item.case_id)
            payload = latest_version(s, item.case_id).payload  # type: ignore[union-attr]
            original = get_value(payload, item.field_path) or item.proposed
            new_value: dict[str, Any] | None = None
            version: int | None = None
            if action == "confirm":
                if (
                    not original
                    or original.get("value") is None
                    or "extraction_method" not in original
                ):
                    raise InvalidStateError(
                        "review item",
                        item.status,
                        "There is no normalised value to confirm (e.g. unknown unit); "
                        "use 'correct'.",
                    )
                confirmed = dict(original)
                confirmed.update(
                    {
                        "confirmed_by_human": True,
                        "field_status": FieldStatus.HUMAN_CONFIRMED.value,
                        "notes": [
                            *original.get("notes", []),
                            f"Confirmed by {actor}" + (f": {reason}" if reason else ""),
                        ],
                    }
                )
                new_value = ExtractedValue[Any].model_validate(confirmed).model_dump(mode="json")
                item.status = ReviewItemStatus.CONFIRMED.value
            elif action == "correct":
                parsed = parse_field_value(item.field_path, value)
                new_value = manual_value(
                    item.field_path,
                    parsed,
                    actor,
                    reason,
                    ExtractionMethod.HUMAN_CORRECTED,
                    original,
                )
                item.status = ReviewItemStatus.CORRECTED.value
            elif action == "reject":
                new_value = None
                item.status = ReviewItemStatus.REJECTED.value
            else:
                item.status = ReviewItemStatus.MORE_EVIDENCE_REQUESTED.value
            if action != "request_more_evidence":
                payload = set_value(payload, item.field_path, new_value)
                version = self._new_version(
                    s,
                    case,
                    payload,
                    source="review",
                    actor=actor,
                    reason=f"{action} {item.field_path}",
                )
                item.resolved_at = datetime.now(tz=UTC)
            s.add(
                ReviewItemEventRow(
                    item_id=item.id,
                    action=action,
                    actor=actor,
                    reason=reason,
                    original_value=original,
                    new_value=new_value,
                    data_version=version,
                )
            )
            audit(
                s,
                actor=actor,
                action=f"review_item.{action}",
                entity_type="review_item",
                entity_id=item.id,
                case_id=item.case_id,
                details={"field_path": item.field_path, "data_version": version},
            )
            s.flush()
            self._refresh_status(s, case)
        return self.review_items(status=None, org_id=None, item_id=item_id)[0]  # authorised above
