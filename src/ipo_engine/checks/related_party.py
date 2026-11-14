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
from ipo_engine.parse.units import MULTIPLIER, Unit, detect_unit
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
    # ok | partial | withheld | no_percentage_printed | no_percentage_table | no_summary
    status: str
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


def _n_head(t: Table) -> int:
    """Header rows: as the parser found them, else the leading rows that hold no printed figure.

    A figure here is a decimal such as 14.55; a lone integer (a serial number, a year) is not one.
    """
    if t.n_header_rows:
        return t.n_header_rows
    n = 0
    for r in t.rows[:10]:
        if any("." in c and (_dec(c, _NUM) is not None or _dec(c, _PCT) is not None) for c in r):
            break
        n += 1
    return n


def _figure_rows(t: Table) -> int:
    """Body rows that hold at least one printed decimal figure."""
    return sum(
        any("." in c and (_dec(c, _NUM) is not None or _dec(c, _PCT) is not None) for c in r)
        for r, _ in _body(t)
    )


def _with_header(header: Table, body: Table) -> Table | None:
    """`body` under the header of `header`, when the parser split them and the columns match."""
    n = _n_head(header)
    width = max((len(r) for r in header.rows), default=0)
    if not n or width != max((len(r) for r in body.rows), default=-1):
        return None
    return Table(
        pdf_pages=body.pdf_pages,
        rows=[*header.rows[:n], *body.rows],
        row_pages=[*header.row_pages[:n], *body.row_pages],
        unit=header.unit or body.unit,
        n_header_rows=n,
    )


def _heads(t: Table) -> list[str]:
    n = max((len(r) for r in t.rows), default=0)
    head_rows = t.rows[: _n_head(t)]
    return [
        " ".join(r[j].strip() for r in head_rows if j < len(r) and r[j].strip()) for j in range(n)
    ]


# Matched on text with all spaces removed: a narrow column splits words ("Marc h 31, 2026").
_PERIOD = re.compile(
    r"(march|june|september|december)(31|30),?(20\d\d)|fiscal(?:year)?(20\d\d)|fy(20\d\d)"
)


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())


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
            for m in _PERIOD.finditer(_squash(h))
        ]
        for f in found:
            if not out or out[-1] != f:
                out.append(f)
    return out


def _is_revenue_pct(head: str) -> bool:
    h = _squash(head)
    return ("%" in h or "percent" in h) and "revenue" in h


_HEADERISH = re.compile(r"revenue|percentage|% of|operations|amount|\(in %\)", re.I)


def _body(t: Table) -> list[tuple[list[str], int]]:
    """Body rows with their pages, leaving out header text repeated at a page break.

    A stitched table carries the header again on each page; such a row has words like "revenue" or
    "% of" and no figure in it.
    """
    out = []
    for r, page in zip(t.rows[_n_head(t) :], t.row_pages[_n_head(t) :], strict=True):
        has_figure = any(_dec(c, _PCT) is not None or _dec(c, _NUM) is not None for c in r)
        if not has_figure and any(_HEADERISH.search(c) for c in r):
            continue
        out.append((r, page))
    return out


_SPILL = re.compile(r"^\(?\s*(in\s*)?%\s*\)?$", re.I)


def _column_is_percentages(t: Table, j: int) -> bool:
    """Cells under a percentage header must be percentages with a % sign (dashes aside)."""
    cells = [r[j].strip() for r, _ in _body(t) if j < len(r) and r[j].strip()]
    values = [c for c in cells if c not in {"-", "–", "—"} and not _SPILL.match(c)]
    return sum(_dec(c, _PCT) is not None for c in values) >= 0.9 * len(values)


def _columns_with_percentages(t: Table) -> list[int]:
    n = max((len(r) for r in t.rows), default=0)
    return [
        j
        for j in range(n)
        if sum(_dec(r[j], _PCT) is not None for r in t.rows[_n_head(t) :] if j < len(r)) >= 1
    ]


def _align(t: Table, header_cols: list[int]) -> list[int] | None:
    """Percentage columns as the cells have them, or None if header and cells disagree.

    A header cell can sit one column to the right of its figures. That is accepted only when every
    percentage column moves by the same one step, each column then holds percentages, and no
    percentage lies outside the columns found.
    """
    for shift in (0, 1):
        cols = [j - shift for j in header_cols]
        if min(cols, default=-1) < 0:
            continue
        if all(_column_is_percentages(t, c) for c in cols) and not (
            set(_columns_with_percentages(t)) - set(cols)
        ):
            return cols
    return None


@dataclass(frozen=True)
class Column:
    pct: int  # column holding the share of revenue
    amount: int | None  # the amount column beside it, where the layout pairs them
    year: int
    signless: bool = False  # the percentage is printed without a % sign (read only if it ties out)


def _tie(t: Table, pct_col: int, amount_col: int, revenue: Decimal) -> tuple[int, int]:
    """(rows that can be tested, rows whose printed percentage equals amount over revenue).

    `revenue` is in the table's own unit. A row is testable when the share is large enough that two
    printed decimals pin it down (0.5% or more); a row ties when the printed share is within 1.5%
    (or 0.02 points) of amount / revenue * 100.
    """
    tested = tied = 0
    for r, _ in _body(t):
        if max(pct_col, amount_col) >= len(r):
            continue
        pct, amount = _dec(r[pct_col], _NUM), _dec(r[amount_col], _NUM)
        if pct is None or amount is None:
            continue
        expected = abs(amount) / revenue * 100
        if expected < Decimal("0.5"):
            continue
        tested += 1
        if abs(abs(pct) - expected) <= max(Decimal("0.02"), expected * Decimal("0.015")):
            tied += 1
    return tested, tied


def _signless_column(
    t: Table,
    heads: list[str],
    header_col: int,
    year: int,
    revenue: dict[int, Decimal],
    unit_hint: Unit | None,
) -> Column | None:
    """A revenue percentage printed as a plain number: accepted only if it ties to the amounts.

    The share and its amount sit side by side, in either order (some filings print the percentage
    first). Every layout that ties out against the filing's own verified revenue is a candidate;
    one that ties uniquely is used, anything else is withheld.
    """
    unit = t.unit or unit_hint
    if unit is None or year not in revenue:
        return None
    r_table = revenue[year] / MULTIPLIER[unit]
    if r_table <= 0:
        return None
    found: list[Column] = []
    n = max((len(r) for r in t.rows), default=0)
    for pct in (header_col - 1, header_col, header_col + 1):
        for amount in (pct - 1, pct + 1):
            if pct < 0 or amount < 0 or pct >= n or amount >= n:
                continue
            tested, tied = _tie(t, pct, amount, r_table)
            if tested >= 2 and tied * 10 >= tested * 9:
                found.append(Column(pct, amount, year, signless=True))
    return found[0] if len(found) == 1 else None


def _pct_column(
    t: Table, revenue: dict[int, Decimal] | None = None, unit_hint: Unit | None = None
) -> Column | None:
    """The revenue-percentage column of the latest full year, or None.

    The header gives the periods in order and the percentage columns in order; they are paired
    only when there are equally many and every such column really holds percentages, so a misread
    header or a shifted column withholds the table instead of moving a figure to the wrong year.
    A percentage printed without a % sign is read only when it ties out arithmetically.
    """
    heads = _heads(t)
    if not _n_head(t) or not any(_is_revenue_pct(h) for h in heads):
        return None
    periods = _periods(heads)
    header_cols = [j for j, h in enumerate(heads) if "%" in h or "percent" in h.lower()]
    full = [(i, y) for i, (kind, y) in enumerate(periods) if kind == "fy"]
    if not periods or not full or len(periods) != len(header_cols):
        return None
    best = max(y for _, y in full)
    latest = [i for i, y in full if y == best]
    if len(latest) != 1:
        return None
    pcols = _align(t, header_cols)
    if pcols is not None:
        return Column(pcols[latest[0]], pcols[latest[0]] - 1 if pcols[latest[0]] else None, best)
    return _signless_column(t, heads, header_cols[latest[0]], best, revenue or {}, unit_hint)


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= SPAN_CHARS else text[: SPAN_CHARS - 1].rstrip() + "…"


def _unit_on_pages(page_text: dict[int, str]) -> Unit | None:
    """The unit the summary pages state, only if they state one and all agree."""
    found = (detect_unit(t) for t in page_text.values())
    units = {hit[0] for hit in found if hit is not None}
    return units.pop() if len(units) == 1 else None


def _summary_pages(doc: ParsedDocument, sections: list[Section]) -> tuple[int, ...]:
    for i, s in enumerate(sections):
        t = s.title.lower()
        if "related party" in t and "summary" in t:
            end = sections[i + 1].start_page if i + 1 < len(sections) else doc.n_pages + 1
            return tuple(range(s.start_page, end))
    return ()


def check(
    doc: ParsedDocument, sections: list[Section], revenue: dict[int, Decimal] | None = None
) -> Result:
    """`revenue` maps a fiscal year to the verified revenue from operations in rupees; it is what
    lets a percentage printed without a % sign be checked against its amount."""
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
    pending: Table | None = None  # the latest header that the parser left without rows
    for t in tables:
        first = next((p for p in t.pdf_pages if p in page_set), t.pdf_pages[0])
        merged = False
        if _n_head(t) > 0 and _figure_rows(t) == 0:
            # A header with nothing under it: the parser split header and body. It reads nothing.
            if any(_is_revenue_pct(h) for h in _heads(t)):
                pending = t
            continue
        if _n_head(t) == 0 and _figure_rows(t) >= 2:
            joined = _with_header(pending, t) if pending is not None else None
            if joined is None:
                res.withheld.append((first, "figures with no header of their own"))
                continue
            t, merged = joined, True
        elif not any("%" in c for r in t.rows for c in r):
            continue  # a table with no percentage on it (a list of parties, say)
        col = _pct_column(t, revenue, _unit_on_pages(page_text))
        if col is None or (merged and not col.signless):
            # a borrowed header is trusted only where the arithmetic confirms the columns
            res.withheld.append((first, _UNPAIRED))
            continue
        j, year = col.pct, col.year
        years.add(year)
        for r, page in _body(t):
            if j >= len(r):
                continue
            pct = _dec(r[j], _NUM if col.signless else _PCT)
            if pct is None or pct < CUTOFF:
                continue
            amount = _dec(r[col.amount], _NUM) if col.amount is not None else None
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
    if not years and not res.withheld:
        # a % sign on the pages, but no table with a percentage in it: nothing was read
        res.status = "no_percentage_table"
        return res
    res.year = f"FY{years.pop()}" if years else None
    if res.withheld:
        res.status = "partial" if res.year else "withheld"
    return res
