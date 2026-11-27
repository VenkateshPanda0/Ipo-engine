"""Reporting periods from column headers ("For the year ended March 31, 2026", "Fiscal 2025").

Indian issuers report on a fiscal year ending 31 March. "Fiscal 2026" and "FY 2025-26" mean the
year ended 31 March 2026. A header that gives only a date leaves the duration unknown (`months`
is None and `instant` False) rather than guessing; the caller may infer it from the statement.
"""

from __future__ import annotations

import calendar
import re
from datetime import date

from pydantic import BaseModel, ConfigDict

_MONTHS = (
    {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
    | {name.lower(): i for i, name in enumerate(calendar.month_abbr) if name}
    | {"sept": 9}
)
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))

_MDY = re.compile(
    rf"\b({_MONTH_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*,?\s*((?:19|20)\d{{2}})\b", re.I
)
_DMY_NAMED = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?[\s\-.,/]*({_MONTH_RE})\.?[\s\-.,/]*((?:19|20)?\d{{2}})(?!\d)",
    re.I,
)
_DMY_NUM = re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.]((?:19|20)\d{2})\b")
_FISCAL = re.compile(
    r"\b(?:fy|f\.y\.|fiscal(?:\s+year)?)\s*'?\s*((?:19|20)\d{2})(?:\s*[-–/]\s*(\d{2}|(?:19|20)\d{2}))?\b",
    re.I,
)
_THREE = re.compile(r"\b(?:three|3)\s*-?\s*months?\b|\bquarter\b", re.I)
_SIX = re.compile(r"\b(?:six|6)\s*-?\s*months?\b|\bhalf[\s-]*year\b", re.I)
_NINE = re.compile(r"\b(?:nine|9)\s*-?\s*months?\b", re.I)
_TWELVE = re.compile(r"\b(?:year|twelve\s+months?|12\s+months?)\b|\b(?:fy|f\.y\.|fiscal)\b", re.I)
# a part-year label right next to the fiscal label ("Q1 FY2025", "FY2025 H1"), unlike a
# side note ("FY2022-23 (including Q4 adjustments)")
_PART_NEXT_TO_FISCAL = re.compile(
    r"\b(?:q\s?[1-4]|h\s?[12]|[369]\s?m|quarter(?:\s+ended)?|half[\s-]*year(?:\s+ended)?"
    r"|stub|interim)\s*[-:,]?\s*(?:fy|f\.y\.|fiscal)(?![a-z])"
    r"|\b(?:fy|f\.y\.|fiscal(?:\s+year)?)\s*'?\s*(?:19|20)\d{2}(?:\s*[-–/]\s*(?:\d{2}|(?:19|20)\d{2}))?"
    r"\s*[-:,]?\s*(?:q\s?[1-4]|h\s?[12]|[369]\s?m)\b",
    re.I,
)
_N_MONTHS = re.compile(r"\b(\d{1,2})\s*-?\s*months?\b", re.I)
_RANGE_SPLIT = re.compile(r"\s+to\s+|\s*[–—]\s*", re.I)
_INSTANT = re.compile(r"\bas\s+(?:at|on)\b", re.I)


class Period(BaseModel):
    """A reporting period. `months` is None for a balance-sheet date or an unknown duration."""

    model_config = ConfigDict(frozen=True)

    end: date
    months: int | None
    instant: bool


def _last_day(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _full_year(text: str) -> int:
    """'2026' -> 2026; two-digit years pivot at 70 ('22' -> 2022, '99' -> 1999)."""
    year = int(text)
    if len(text) == 4:
        return year
    return 2000 + year if year < 70 else 1900 + year


def _safe_date(year: int, month: int, day: int) -> date | None:
    if 1 <= month <= 12 and 1 <= day <= _last_day(year, month):
        return date(year, month, day)
    return None


def _first_date(text: str) -> tuple[int, date, bool] | None:
    """(position, end date, from_fiscal_label) of the earliest date expression in `text`."""
    found: list[tuple[int, date, bool]] = []
    if m := _MDY.search(text):
        d = _safe_date(int(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2)))
        if d:
            found.append((m.start(), d, False))
    if m := _DMY_NAMED.search(text):
        d = _safe_date(_full_year(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1)))
        if d:
            found.append((m.start(), d, False))
    if m := _DMY_NUM.search(text):
        d = _safe_date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if d:
            found.append((m.start(), d, False))
    if m := _FISCAL.search(text):
        first_year = int(m.group(1))
        second = m.group(2)
        if second is None:
            end_year = first_year
        elif len(second) == 2:
            end_year = (first_year // 100) * 100 + int(second)
            if first_year - end_year == 1:  # "FY 2022-21": years written in reverse order
                end_year = first_year
            elif end_year < first_year:  # "1999-00": the century turns over
                end_year += 100
        else:
            end_year = int(second)
        found.append((m.start(), date(end_year, 3, 31), True))
    return min(found, key=lambda f: f[0]) if found else None


def parse_period(header: str) -> Period | None:
    """Parse a column header into a Period, or None if it carries no date."""
    hit = _first_date(header)
    if hit is None:
        return None
    _, end, from_fiscal = hit
    if from_fiscal and _PART_NEXT_TO_FISCAL.search(header):
        # "Q1 FY2025" is a quarter that does not end on 31 March: the fiscal label alone cannot
        # place it, and calling it the whole year would put a quarter's figure under the year.
        return None
    range_months: int | None = None
    parts = _RANGE_SPLIT.split(header)
    if len(parts) == 2 and not from_fiscal:
        a, b = _first_date(parts[0]), _first_date(parts[1])
        if a and b and b[1] > a[1]:  # "April 1, 2023 to March 31, 2024": the period ends at the end
            end = b[1]
            if a[1].day == 1:
                range_months = (end.year - a[1].year) * 12 + end.month - a[1].month + 1
    if _INSTANT.search(header) and not _TWELVE.search(re.sub(_INSTANT, "", header)):
        return Period(end=end, months=None, instant=True)
    if _NINE.search(header):
        months: int | None = 9
    elif _SIX.search(header):
        months = 6
    elif _THREE.search(header):
        months = 3
    elif (n := _N_MONTHS.search(header)) and int(n.group(1)) not in (3, 6, 9, 12):
        months = int(n.group(1))  # "15 months ended": keyed by its own length, never as a year
    elif from_fiscal or _TWELVE.search(header):
        months = 12
    else:
        months = range_months
    return Period(end=end, months=months, instant=False)


def period_key(p: Period) -> str:
    """Stable key: FY2026 for a March year end, else <months>M-<end>, AT-<end>, ?-<end>."""
    if p.instant:
        return f"AT-{p.end.isoformat()}"
    if p.months == 12 and (p.end.month, p.end.day) == (3, 31):
        return f"FY{p.end.year}"
    prefix = f"{p.months}M" if p.months is not None else "?"
    return f"{prefix}-{p.end.isoformat()}"


def fiscal_key(p: Period) -> str:
    """Like `period_key`, but a year-end figure dated 31 March gets the fiscal-year key.

    A stock (total assets, net worth ...) at 31 March 2026 is the year-end figure of FY2026, so it
    must line up with flow figures (revenue, profit) of FY2026 and with a "FY2026" column in a KPI
    table. A flow printed under an "As at 31 March" header (some SME filings do this) is likewise
    the year's figure: a flow cannot be an instant. Quarters and stubs keep their `period_key`.
    """
    if (p.end.month, p.end.day) == (3, 31) and (p.instant or p.months in (None, 12)):
        return f"FY{p.end.year}"
    return period_key(p)
