"""
Organisation scoping: one place decides which organisation owns an id in a URL.

Every route under ``/api/v1`` that takes a case, document, report or review-item id is checked by
:func:`enforce_org_scope` before its handler runs. An id that belongs to another organisation is
answered exactly like an id that does not exist (404), so a caller cannot tell whether it is real.
A route that takes an id-like path parameter this module does not know about is refused with a
500 rather than served unchecked, and a test walks the whole route table to catch it before release.
"""

from __future__ import annotations

from sqlalchemy import func, select

from ipo_engine.screening.core.constants import DEFAULT_ORG_ID
from ipo_engine.screening.db.base import Database
from ipo_engine.screening.db.models import CaseRow, DocumentRow, ReportRow, ReviewItemRow

#: path parameter name -> how to find the owning organisation of its value
SCOPED_PARAMS = ("case_id", "document_id", "report_id", "item_id")
#: path parameters that name a public, organisation-independent resource
UNSCOPED_PARAMS = ("rule_id", "page", "review_id")


def owner_org(db: Database, param: str, value: str) -> str | None:
    """Organisation owning ``value`` for path parameter ``param``; None if there is no such id."""
    with db.session() as s:
        if param == "case_id":
            stmt = select(CaseRow.org_id).where(CaseRow.id == value)
        elif param == "document_id":
            stmt = (
                select(CaseRow.org_id)
                .join(DocumentRow, DocumentRow.case_id == CaseRow.id)
                .where(DocumentRow.id == value)
            )
        elif param == "report_id":
            # A report made through the legacy /screen endpoint has no case; it belongs to the
            # default organisation, the one every pre-accounts record was assigned to.
            stmt = (
                select(func.coalesce(CaseRow.org_id, DEFAULT_ORG_ID))
                .select_from(ReportRow)
                .outerjoin(CaseRow, ReportRow.case_id == CaseRow.id)
                .where(ReportRow.report_id == value)
            )
        elif param == "item_id":
            stmt = (
                select(CaseRow.org_id)
                .join(ReviewItemRow, ReviewItemRow.case_id == CaseRow.id)
                .where(ReviewItemRow.id == value)
            )
        else:
            raise ValueError(f"no organisation lookup for path parameter {param!r}")
        return s.execute(stmt).scalar()
