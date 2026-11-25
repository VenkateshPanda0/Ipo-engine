"""
Screening a case, and the dashboard counts.

Split out of ``cases.py``; every name here is still importable from
``ipo_engine.screening.services.cases``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from ipo_engine.screening.db.base import Database
from ipo_engine.screening.db.models import (
    AuditEventRow,
    CaseRow,
    DocumentRow,
    ExtractionRunRow,
    ReportRow,
    ReviewItemRow,
)
from ipo_engine.screening.db.repositories import (
    SqlReportStorage,
    latest_version,
)
from ipo_engine.screening.engine.decision_engine import DecisionEngine
from ipo_engine.screening.models.company_data import CompanyData
from ipo_engine.screening.models.exceptions import InvalidStateError, NotFoundError
from ipo_engine.screening.models.ipo_report import IPOReport
from ipo_engine.screening.services.case_values import (
    CaseStatus,
    ReviewItemStatus,
    refresh_case_status,
)


class CaseScreeningService:
    """Screen the current version of a case and persist an immutable report."""

    def __init__(self, db: Database, engine: DecisionEngine, reports: SqlReportStorage) -> None:
        self._db = db
        self._engine = engine
        self._reports = reports

    def screen(self, case_id: str, *, actor: str) -> IPOReport:
        with self._db.session() as s:
            case = s.get(CaseRow, case_id)
            if case is None:
                raise NotFoundError("case", case_id)
            if case.status == CaseStatus.ARCHIVED.value:
                raise InvalidStateError("case", case.status, "Archived cases cannot be screened.")
            busy = s.execute(
                select(func.count())
                .select_from(DocumentRow)
                .where(
                    DocumentRow.case_id == case_id,
                    DocumentRow.status.in_(("uploaded", "extracting")),
                )
            ).scalar_one()
            if busy:
                raise InvalidStateError("case", case.status, "Documents are still being processed.")
            version = latest_version(s, case_id)
            assert version is not None
            docs = (
                s.execute(select(DocumentRow.sha256).where(DocumentRow.case_id == case_id))
                .scalars()
                .all()
            )
            runs = (
                s.execute(
                    select(ExtractionRunRow.id)
                    .join(DocumentRow, ExtractionRunRow.document_id == DocumentRow.id)
                    .where(DocumentRow.case_id == case_id)
                )
                .scalars()
                .all()
            )
            company = CompanyData.model_validate(version.payload)
            data_version = version.version
        report = self._engine.evaluate(
            company, case_id=UUID(case_id), document_ids=list(docs), extraction_run_ids=list(runs)
        )
        self._reports.save(
            report.report_id, report, case_id=case_id, data_version=data_version, created_by=actor
        )
        with self._db.session() as s:
            case = s.get(CaseRow, case_id)
            assert case is not None
            case.updated_at = datetime.now(tz=UTC)
            refresh_case_status(s, case)  # screened, unless review items remain open
        return report

    def list_reports(self, case_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with self._db.session() as s:
            # Listing columns only: the report payload can be large and is not needed here.
            stmt = select(
                ReportRow.report_id,
                ReportRow.case_id,
                ReportRow.data_version,
                ReportRow.ruleset_version,
                ReportRow.outcome,
                ReportRow.legacy_status,
                ReportRow.company_name,
                ReportRow.created_by,
                ReportRow.created_at,
            )
            if case_id:
                stmt = stmt.where(ReportRow.case_id == case_id)
            rows = s.execute(stmt.order_by(ReportRow.created_at.desc()).limit(limit)).all()
            return [
                {
                    "report_id": r.report_id,
                    "case_id": r.case_id,
                    "data_version": r.data_version,
                    "ruleset_version": r.ruleset_version,
                    "outcome": r.outcome,
                    "legacy_status": r.legacy_status,
                    "company_name": r.company_name,
                    "created_by": r.created_by,
                    "created_at": r.created_at,
                }
                for r in rows
            ]


def dashboard(db: Database) -> dict[str, Any]:
    """Aggregate counts for the dashboard (all computed from stored data)."""
    with db.session() as s:

        def count(stmt: Any) -> int:
            return int(s.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())

        status_rows = s.execute(select(CaseRow.status, func.count()).group_by(CaseRow.status)).all()
        outcome_rows = s.execute(
            select(ReportRow.outcome, func.count()).group_by(ReportRow.outcome)
        ).all()
        by_status: dict[str, int] = {str(k): int(v) for k, v in status_rows}
        latest_outcomes: dict[str, int] = {str(k): int(v) for k, v in outcome_rows}
        recent = (
            s.execute(select(AuditEventRow).order_by(AuditEventRow.id.desc()).limit(15))
            .scalars()
            .all()
        )
        return {
            "cases_total": count(select(CaseRow)),
            "cases_by_status": {k: int(v) for k, v in by_status.items()},
            "cases_awaiting_review": int(by_status.get(CaseStatus.AWAITING_REVIEW.value, 0)),
            "open_review_items": count(
                select(ReviewItemRow).where(ReviewItemRow.status == ReviewItemStatus.OPEN.value)
            ),
            "reports_total": count(select(ReportRow)),
            "reports_by_outcome": {str(k): int(v) for k, v in latest_outcomes.items()},
            "documents_failed": count(select(DocumentRow).where(DocumentRow.status == "failed")),
            "documents_processing": count(
                select(DocumentRow).where(DocumentRow.status.in_(("uploaded", "extracting")))
            ),
            "recent_activity": [
                {
                    "ts": r.ts,
                    "actor": r.actor,
                    "action": r.action,
                    "entity_type": r.entity_type,
                    "entity_id": r.entity_id,
                    "case_id": r.case_id,
                }
                for r in recent
            ],
        }
