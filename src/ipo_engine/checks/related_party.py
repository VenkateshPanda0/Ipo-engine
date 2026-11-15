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
from collections.abc import Callable
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
    """`body` under the header of `header`, when the parser split them.

    Same width: the header goes on as it is. Narrower body (the parser kept the header's spacer
    columns and dropped them from the rows): the header's periods and percentage columns are laid
    over the right-hand end of the rows, amount and percentage side by side for each period. Which
    of the two comes first is not guessed here; the arithmetic tie-out decides, or the table is
    withheld.
    """
    n = _n_head(header)
    width = max((len(r) for r in header.rows), default=0)
    body_width = max((len(r) for r in body.rows), default=0)
    if not n or not body_width:
        return None
    unit = header.unit or body.unit
    if width == body_width:
        return Table(
            pdf_pages=body.pdf_pages,
            rows=[*header.rows[:n], *body.rows],
            row_pages=[*header.row_pages[:n], *body.row_pages],
            unit=unit,
            n_header_rows=n,
        )
    heads = _heads(header)
    periods = _periods(heads)
    k = sum(1 for h in heads if "%" in h or "percent" in h.lower())
    if k == 0 or len(periods) != k or body_width != 2 * k + 1:
        return None
    pct_head = next(h for h in heads if _is_revenue_pct(h))
    head: list[str] = [""]
    for kind, year in periods:
        date = f"March 31, {year}" if kind == "fy" else f"June 30, {year}"
        head += [date, pct_head]
    return Table(
        pdf_pages=body.pdf_pages,
        rows=[head, *body.rows],
        row_pages=[body.row_pages[0] if body.row_pages else body.pdf_pages[0], *body.row_pages],
        unit=unit,
        n_header_rows=1,
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
    row_tie: bool = False  # order taken from the filing's other tables: every shown row must tie


def orientation(col: Column) -> str | None:
    """Which way round the amount and its share sit, for a plain-number column."""
    if col.amount is None:
        return None
    return "amount_first" if col.amount == col.pct - 1 else "pct_first"


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
    orient: str | None = None,
) -> Column | None:
    """A revenue percentage printed as a plain number: accepted only if it ties to the amounts.

    The share and its amount sit side by side, in either order (some filings print the percentage
    first). A layout that ties out against the filing's own verified revenue, uniquely, is used. A
    table too small to tie by itself may take the order that the filing's other tables established
    (`orient`); then every row shown from it must tie on its own (`row_tie`).
    """
    unit = t.unit or unit_hint
    if unit is None or year not in revenue:
        return None
    r_table = revenue[year] / MULTIPLIER[unit]
    if r_table <= 0:
        return None
    strong: list[Column] = []
    n = max((len(r) for r in t.rows), default=0)
    for pct in (header_col - 1, header_col, header_col + 1):
        for amount in (pct - 1, pct + 1):
            if pct < 0 or amount < 0 or pct >= n or amount >= n:
                continue
            tested, tied = _tie(t, pct, amount, r_table)
            if tested >= 2 and tied * 10 >= tested * 9:
                strong.append(Column(pct, amount, year, signless=True))
    if len(strong) == 1:
        return strong[0]
    if strong or orient is None:
        return None
    pct, amount = (
        (header_col, header_col - 1) if orient == "amount_first" else (header_col - 1, header_col)
    )
    if pct < 0 or amount < 0 or max(pct, amount) >= n:
        return None
    return Column(pct, amount, year, signless=True, row_tie=True)


def row_ties(pct: Decimal, amount: Decimal | None, revenue_table: Decimal) -> bool:
    """One row's printed share equals its amount over revenue (same tolerance as `_tie`)."""
    if amount is None:
        return False
    expected = abs(amount) / revenue_table * 100
    return abs(abs(pct) - expected) <= max(Decimal("0.02"), expected * Decimal("0.015"))


def _pct_column(
    t: Table,
    revenue: dict[int, Decimal] | None = None,
    unit_hint: Unit | None = None,
    orient: str | None = None,
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
    return _signless_column(
        t, heads, header_cols[latest[0]], best, revenue or {}, unit_hint, orient
    )


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= SPAN_CHARS else text[: SPAN_CHARS - 1].rstrip() + "…"


_FIGURE = re.compile(r"\d[\d,]*\.\d{1,2}(?!\d)")


def _uncaptured(page: int, text: str, tables: list[Table]) -> str | None:
    """A reason, if the page prints clearly more decimal figures than the tables hold from it."""
    printed = len(_FIGURE.findall(text))
    captured = sum(
        len(_FIGURE.findall(c))
        for t in tables
        for r, pg in zip(t.rows, t.row_pages, strict=True)
        if pg == page
        for c in r
    )
    if printed - captured > max(5, printed // 4):
        return (
            f"the page prints about {printed} figures but only {captured} were captured from its "
            "tables, so rows may be missing"
        )
    return None


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
    doc: ParsedDocument,
    sections: list[Section],
    revenue: dict[int, Decimal] | None = None,
    pdf_text: Callable[[int], str] | None = None,
) -> Result:
    """`revenue` maps a fiscal year to the verified revenue from operations in rupees; it is what
    lets a percentage printed without a % sign be checked against its amount. `pdf_text` gives a
    page's text from the PDF itself: a summary page that prints clearly more figures than the table
    reader captured from it is withheld, because rows it never saw cannot be reported as absent."""
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
    unit_hint = _unit_on_pages(page_text)
    if pdf_text is not None:
        for p in pages:
            gap = _uncaptured(p, pdf_text(p), tables)
            if gap:
                res.withheld.append((p, gap))
    # Pass 1: put each table with its header (the parser sometimes separates them).
    pending: Table | None = None  # the latest header that the parser left without rows
    work: list[tuple[Table, int, bool]] = []  # (table, first summary page, header was borrowed)
    for t in tables:
        first = next((p for p in t.pdf_pages if p in page_set), t.pdf_pages[0])
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
            work.append((joined, first, True))
        elif any("%" in c for r in t.rows for c in r):
            work.append((t, first, False))  # (a table with no percentage on it is not one)
    # The way round amount and share sit in plain-number tables that tie out by themselves; used
    # for the filing's smaller tables only when every such table agrees.
    own = {
        orientation(c)
        for t, _, _ in work
        if (c := _pct_column(t, revenue, unit_hint)) is not None and c.signless
    }
    orient = own.pop() if len(own) == 1 and None not in own else None
    # Pass 2: read each table.
    for t, first, merged in work:
        col = _pct_column(t, revenue, unit_hint)
        if col is None and orient is not None:
            col = _pct_column(t, revenue, unit_hint, orient)
        if col is None or (merged and not col.signless):
            # a borrowed header is trusted only where the arithmetic confirms the columns
            res.withheld.append((first, _UNPAIRED))
            continue
        j, year = col.pct, col.year
        r_table = (
            revenue[year] / MULTIPLIER[t.unit or unit_hint]  # type: ignore[index]
            if col.signless and revenue and (t.unit or unit_hint) and year in revenue
            else None
        )
        rows: list[Row] = []
        keys: list[tuple[Decimal | None, Decimal]] = []
        broken = False
        for r, page in _body(t):
            if j >= len(r):
                continue
            pct = _dec(r[j], _NUM if col.signless else _PCT)
            if pct is None or pct < CUTOFF:
                continue
            amount = _dec(r[col.amount], _NUM) if col.amount is not None else None
            if col.row_tie and (r_table is None or not row_ties(pct, amount, r_table)):
                broken = True  # a large figure that does not tie: the order is not what we assumed
                break
            rows.append(Row(page, pct, amount, _clip(" | ".join(r))))
            keys.append((amount, pct))
        if broken:
            res.withheld.append(
                (first, "a share at or above the cut-off does not tie to its amount")
            )
            continue
        years.add(year)
        for row, key in zip(rows, keys, strict=True):
            if key in seen:  # the same transaction printed twice (from both parties' side)
                prev = res.rows[seen[key]]
                res.rows[seen[key]] = Row(
                    prev.page,
                    prev.percent,
                    prev.amount,
                    prev.text,
                    (*prev.mirror_pages, *(row.page,)),
                )
                continue
            seen[key] = len(res.rows)
            res.rows.append(row)
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
