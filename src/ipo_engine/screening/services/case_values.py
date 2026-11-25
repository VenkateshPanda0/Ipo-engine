"""
Case vocabulary and field values: status enums and parsing of a manually entered value.

Split out of ``cases.py``; every name here is still importable from
``ipo_engine.screening.services.cases``.
"""

from __future__ import annotations

import enum
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select

from ipo_engine.screening.db.models import CaseRow, DocumentRow, ReportRow, ReviewItemRow
from ipo_engine.screening.models.enums import (
    ConfidenceLevel,
    ExtractionMethod,
    FieldStatus,
)
from ipo_engine.screening.models.extracted_value import ExtractedValue
from ipo_engine.screening.models.field_paths import (
    value_type,
)


class CaseStatus(str, enum.Enum):
    DRAFT = "draft"
    PROCESSING = "processing_documents"
    AWAITING_REVIEW = "awaiting_review"
    READY = "ready_for_screening"
    SCREENED = "screened"
    ARCHIVED = "archived"


class ReviewItemStatus(str, enum.Enum):
    OPEN = "open"
    CONFIRMED = "confirmed"
    CORRECTED = "corrected"
    REJECTED = "rejected"
    MORE_EVIDENCE_REQUESTED = "more_evidence_requested"
    SUPERSEDED = "superseded"  # replaced by a newer extraction run of the same document


_UNIT_FOR_TYPE = {"decimal": "INR_CRORE", "int": "COUNT", "bool": "BOOLEAN"}


def parse_field_value(path: str, raw: Any) -> Decimal | int | bool:
    """Coerce a user-supplied value to the field's type (strict)."""
    kind = value_type(path)
    if kind == "bool":
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str) and raw.lower() in ("true", "false", "yes", "no"):
            return raw.lower() in ("true", "yes")
        raise ValueError(f"{path} expects a boolean")
    if kind == "int":
        if (
            isinstance(raw, bool)
            or not isinstance(raw, (int, str))
            or not str(raw).strip().lstrip("-").isdigit()
        ):
            raise ValueError(f"{path} expects an integer")
        return int(raw)
    if isinstance(raw, bool):
        raise ValueError(f"{path} expects a number")
    try:
        value = Decimal(str(raw))
    except InvalidOperation as exc:
        raise ValueError(f"{path} expects a number") from exc
    if not value.is_finite():
        raise ValueError(f"{path} expects a finite number")
    return value


def manual_value(
    path: str,
    value: Decimal | int | bool,
    actor: str,
    note: str | None,
    method: ExtractionMethod = ExtractionMethod.MANUAL,
    original: dict[str, Any] | None = None,
) -> dict[str, Any]:
    unit = (
        "PERCENT"
        if (
            "percentage" in path or path.endswith(("_pct", "holding", "allocation", "contribution"))
        )
        and value_type(path) == "decimal"
        else _UNIT_FOR_TYPE[value_type(path)]
    )
    if path.endswith("lock_in_months"):
        unit = "MONTHS"
    notes = [
        f"Entered by {actor}" if method == ExtractionMethod.MANUAL else f"Corrected by {actor}"
    ]
    if note:
        notes.append(note)
    ev = ExtractedValue[Any](
        value=value,
        source_document=(original or {}).get("source_document") or "manual entry",
        document_id=(original or {}).get("document_id"),
        page_number=(original or {}).get("page_number"),
        extraction_method=method,
        confidence=ConfidenceLevel.HIGH,
        confirmed_by_human=method == ExtractionMethod.HUMAN_CORRECTED,
        unit=unit,
        original_text=(original or {}).get("original_text"),
        original_unit=(original or {}).get("original_unit"),
        period_label=(original or {}).get("period_label"),
        raw_text=(original or {}).get("raw_text"),
        field_status=FieldStatus.HUMAN_CONFIRMED
        if method == ExtractionMethod.HUMAN_CORRECTED
        else FieldStatus.MANUAL_ENTRY,
        notes=notes,
    )
    return ev.model_dump(mode="json")


def is_human_value(v: dict[str, Any] | None) -> bool:
    if not v:
        return False
    return bool(v.get("confirmed_by_human")) or v.get("extraction_method") in (
        "manual",
        "human_corrected",
    )


def refresh_case_status(s: Any, row: CaseRow) -> None:
    """Derive a case's status from its documents, open review items and reports."""
    if row.status == CaseStatus.ARCHIVED.value:
        return
    processing = s.execute(
        select(func.count())
        .select_from(DocumentRow)
        .where(DocumentRow.case_id == row.id, DocumentRow.status.in_(("uploaded", "extracting")))
    ).scalar_one()
    open_items = s.execute(
        select(func.count())
        .select_from(ReviewItemRow)
        .where(ReviewItemRow.case_id == row.id, ReviewItemRow.status == ReviewItemStatus.OPEN.value)
    ).scalar_one()
    if processing:
        row.status = CaseStatus.PROCESSING.value
    elif open_items:
        row.status = CaseStatus.AWAITING_REVIEW.value
    else:
        # "Screened" only while a report exists for the current data version; once the
        # data changes the case needs screening again.
        screened = s.execute(
            select(ReportRow.report_id)
            .where(ReportRow.case_id == row.id, ReportRow.data_version == row.current_version)
            .limit(1)
        ).first()
        row.status = CaseStatus.SCREENED.value if screened else CaseStatus.READY.value
