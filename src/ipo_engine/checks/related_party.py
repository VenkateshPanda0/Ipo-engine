"""Related-party transactions: rows of the summary table whose printed share of revenue is large.

Nothing is computed. A row is listed only when the document itself prints a percentage of revenue
from operations for it, in the column of the latest full fiscal year, at or above the cut-off. The
column is found from the table's own header; if the header cannot be read with certainty the page
is withheld with the reason, never guessed (so "no rows" always means the readable tables had none).
Rows for share issues or buybacks are not told apart here: the row text is shown and the reader
decides. Design and labels: docs/decisions.md D-049, D-054, D-055.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from ipo_engine.parse.models import ParsedDocument, Table
from ipo_engine.segment import Section

CUTOFF = Decimal("5.00")
SPAN_CHARS = 200
_PCT = re.compile(r"^\(?\s*(-?[\d,]*\.?\d+)\s*\)?\s*%$")
_NUM = re.compile(r"^\(?\s*(-?[\d,]*\.?\d+)\s*\)?$")
_UNPAIRED = (
    "header and data do not pair up (periods versus percentage columns), or no revenue basis"
)


@dataclass(frozen=True)
class Row:
    page: int
    percent: Decimal
    amount: Decimal | None
    text: str  # the table row as printed, cells joined by " | ", clipped
    mirror_pages: tuple[int, ...] = ()


@dataclass
class Result:
    status: str  # ok | partial | withheld | no_percentage_printed | no_summary
    year: str | None = None  # latest full fiscal year the rows are for, e.g. "FY2026"
    pages: tuple[int, ...] = ()  # pages of the summary section
    rows: list[Row] = field(default_factory=list)
    withheld: list[tuple[int, str]] = field(default_factory=list)  # (page, reason)


def _dec(text: str, pattern: re.Pattern[str]) -> Decimal | None:
    m = pattern.match(text.strip())
    if not m:
        return None
    try:
        v = Decimal(m.group(1).replace(",", ""))
    except InvalidOperation:
        return None
    return -v if text.strip().startswith("(") else v


def _heads(t: Table) -> list[str]:
    n = max((len(r) for r in t.rows), default=0)
    head_rows = t.rows[: t.n_header_rows]
    return [
        " ".join(r[j].strip() for r in head_rows if j < len(r) and r[j].strip()) for j in range(n)
    ]


_PERIOD = re.compile(
    r"(march|june|september|december)\s*(31|30)\s*,?\s*(20\d\d)|fiscal\s*(?:year\s*)?(20\d\d)|fy\s*(20\d\d)",
    re.I,
)


def _periods(heads: list[str]) -> list[tuple[str, int]]:
    """Periods named by the header, left to right, a repeat in the next column counted once.

    Kind is "fy" for a year ended 31 March or a named fiscal year, "stub" for anything else
    (three months ended 30 June ...).
    """
    out: list[tuple[str, int]] = []
    for h in heads:
        found = [
            (
                (
                    "fy"
                    if (m.group(1) or "").lower() == "march" or m.group(4) or m.group(5)
                    else "stub"
                ),
                int(m.group(3) or m.group(4) or m.group(5)),
            )
            for m in _PERIOD.finditer(h)
        ]
        for f in found:
            if not out or out[-1] != f:
                out.append(f)
    return out


def _is_revenue_pct(head: str) -> bool:
    h = head.lower()
    return ("%" in h or "percent" in h) and "revenue" in h


def _column_is_percentages(t: Table, j: int) -> bool:
    """Cells under a percentage header must be percentages with a % sign (dashes aside)."""
    cells = [r[j].strip() for r in t.rows[t.n_header_rows :] if j < len(r) and r[j].strip()]
    values = [c for c in cells if c not in {"-", "–", "—"}]
    return sum(_dec(c, _PCT) is not None for c in values) >= 0.9 * len(values)


def _columns_with_percentages(t: Table) -> list[int]:
    n = max((len(r) for r in t.rows), default=0)
    return [
        j
        for j in range(n)
        if sum(_dec(r[j], _PCT) is not None for r in t.rows[t.n_header_rows :] if j < len(r)) >= 2
    ]


def _pct_column(t: Table) -> tuple[int, int] | None:
    """(column index, year) of the revenue percentage of the latest full year, or None.

    The header gives the periods in order and the percentage columns in order; they are paired
    only when there are equally many and every such column really holds percentages, so a misread
    header or a shifted column withholds the table instead of moving a figure to the wrong year.
    """
    heads = _heads(t)
    if not t.n_header_rows or not any(_is_revenue_pct(h) for h in heads):
        return None
    periods = _periods(heads)
    pcols = [j for j, h in enumerate(heads) if "%" in h or "percent" in h.lower()]
    if not periods or len(periods) != len(pcols):
        return None
    if not all(_column_is_percentages(t, j) for j in pcols):
        return None  # the header has slipped against the cells
    if set(_columns_with_percentages(t)) - set(pcols):
        return None  # percentages sit in a column the header did not name: header slipped
    full = [(i, y) for i, (kind, y) in enumerate(periods) if kind == "fy"]
    if not full:
        return None
    best = max(y for _, y in full)
    latest = [i for i, y in full if y == best]
    return (pcols[latest[0]], best) if len(latest) == 1 else None


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= SPAN_CHARS else text[: SPAN_CHARS - 1].rstrip() + "…"


def _summary_pages(doc: ParsedDocument, sections: list[Section]) -> tuple[int, ...]:
    for i, s in enumerate(sections):
        t = s.title.lower()
        if "related party" in t and "summary" in t:
            end = sections[i + 1].start_page if i + 1 < len(sections) else doc.n_pages + 1
            return tuple(range(s.start_page, end))
    return ()


def check(doc: ParsedDocument, sections: list[Section]) -> Result:
    pages = _summary_pages(doc, sections)
    if not pages:
        return Result("no_summary")
    page_set = set(pages)
    page_text = {
        p.pdf_page: " ".join(b.text for b in p.blocks) for p in doc.pages if p.pdf_page in page_set
    }
    tables = [t for t in doc.tables if page_set.intersection(t.pdf_pages)]
    raw_cells = [
        c
        for p in doc.pages
        if p.pdf_page in page_set
        for rt in p.tables
        for r in rt.rows
        for c in r
    ]
    printed = any("%" in t for t in page_text.values()) or any("%" in c for c in raw_cells)
    printed = printed or any("%" in c for t in tables for r in t.rows for c in r)
    if not printed:
        return Result("no_percentage_printed", pages=pages)
    res = Result("ok", pages=pages)
    years: set[int] = set()
    seen: dict[tuple[Decimal | None, Decimal], int] = {}
    for t in tables:
        first = next((p for p in t.pdf_pages if p in page_set), t.pdf_pages[0])
        if not any("%" in c for r in t.rows for c in r):
            continue  # a table with no percentage on it (a list of parties, say)
        col = _pct_column(t)
        if col is None:
            res.withheld.append((first, _UNPAIRED))
            continue
        j, year = col
        years.add(year)
        for r, page in zip(t.rows[t.n_header_rows :], t.row_pages[t.n_header_rows :], strict=True):
            if j >= len(r):
                continue
            pct = _dec(r[j], _PCT)
            if pct is None or pct < CUTOFF:
                continue
            amount = _dec(r[j - 1], _NUM) if j > 0 else None
            key = (amount, pct)
            if key in seen:  # the same transaction printed twice (from both parties' side)
                prev = res.rows[seen[key]]
                res.rows[seen[key]] = Row(
                    prev.page, prev.percent, prev.amount, prev.text, (*prev.mirror_pages, page)
                )
                continue
            seen[key] = len(res.rows)
            res.rows.append(Row(page, pct, amount, _clip(" | ".join(r))))
    if len(years) > 1:
        res.withheld.append((pages[0], f"tables disagree on the latest year: {sorted(years)}"))
        res.rows.clear()
        res.status = "withheld"
        return res
    res.year = f"FY{years.pop()}" if years else None
    if res.withheld:
        res.status = "partial" if res.year else "withheld"
    return res
