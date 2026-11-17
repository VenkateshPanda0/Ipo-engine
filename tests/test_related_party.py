from decimal import Decimal

from ipo_engine.checks.related_party import check
from ipo_engine.parse.models import BBox, Block, ParsedDocument, ParsedPage, Table
from ipo_engine.parse.units import Unit
from ipo_engine.segment import Section

HEAD = [
    ["Name", "Nature", "Year ended March", "% of revenue", "Year ended March", "% of revenue"],
    ["", "", "31, 2026", "from operations", "31, 2025", "from operations"],
]


def _page(n: int, text: str = "") -> ParsedPage:
    blocks = [Block(pdf_page=n, bbox=BBox(x0=0, top=0, x1=1, bottom=1), text=text)] if text else []
    return ParsedPage(
        pdf_page=n, width=1, height=1, alnum_chars=10, n_images=0, image_coverage=0,
        needs_ocr=False, blocks=blocks,
    )  # fmt: skip


def _doc(body: list[list[str]], head: list[list[str]] = HEAD, extra: str = "") -> ParsedDocument:
    rows = [*head, *body]
    table = Table(pdf_pages=[5], rows=rows, row_pages=[5] * len(rows), n_header_rows=len(head))
    pages = [_page(n, extra if n == 5 else "") for n in range(1, 8)]
    return ParsedDocument(doc_id="d", n_pages=7, pages=pages, tables=[table])


SECTIONS = [Section("SUMMARY OF RELATED PARTY TRANSACTIONS", 5, 5), Section("NEXT", 7, 7)]


def test_a_row_at_or_above_the_cutoff_is_listed_with_its_page_and_amount() -> None:
    body = [["A Ltd", "Sale", "945.41", "12.96%", "-", "-"],
            ["B Ltd", "Rent", "1.0", "0.02%", "-", "-"]]  # fmt: skip
    res = check(_doc(body), SECTIONS)
    assert res.status == "ok" and res.year == "FY2026"
    assert [(r.page, r.percent, r.amount) for r in res.rows] == [
        (5, Decimal("12.96"), Decimal("945.41"))
    ]


def test_only_the_latest_full_year_is_read() -> None:
    res = check(_doc([["A Ltd", "Loan", "-", "-", "50.00", "40.00%"]]), SECTIONS)
    assert res.status == "ok" and res.rows == []  # 40% is FY2025, not the latest year


def test_a_table_whose_header_slips_against_the_cells_is_withheld_not_guessed() -> None:
    slipped = [["A Ltd", "Sale", "945.41", "12.96%", "3.0", "4.5"]]  # last cell is not a percentage
    res = check(_doc(slipped), SECTIONS)
    assert res.status == "withheld" and res.rows == [] and res.withheld


def test_a_header_that_does_not_say_revenue_is_withheld() -> None:
    head = [[h.replace("revenue", "total assets") for h in row] for row in HEAD]
    res = check(_doc([["A Ltd", "Loan", "9.0", "9.93%", "-", "-"]], head), SECTIONS)
    assert res.status == "withheld" and res.rows == []


def test_no_percentage_anywhere_says_so_instead_of_none() -> None:
    head = [["Name", "Year ended March 31, 2026", "Year ended March 31, 2025"]]
    res = check(_doc([["A Ltd", "945.41", "-"]], head), SECTIONS)
    assert res.status == "no_percentage_printed" and res.rows == []


def test_a_transaction_printed_from_both_sides_is_listed_once() -> None:
    body = [["A Ltd", "Loan given", "1144.02", "14.24%", "-", "-"],
            ["B Ltd", "Loan taken", "1144.02", "14.24%", "-", "-"]]  # fmt: skip
    res = check(_doc(body), SECTIONS)
    assert len(res.rows) == 1 and res.rows[0].mirror_pages == (5,)


def test_no_summary_section_is_reported() -> None:
    assert check(_doc([["A", "x", "1", "9%", "-", "-"]]), []).status == "no_summary"


def test_header_text_repeated_at_a_page_break_is_not_data() -> None:
    body = [["A Ltd", "Sale", "945.41", "12.96%", "-", "-"],
            ["", "", "", "% of", "", "% of"],
            ["", "", "", "revenue from operations", "", "revenue from operations"],
            ["B Ltd", "Rent", "1.0", "0.02%", "-", "-"]]  # fmt: skip
    res = check(_doc(body), SECTIONS)
    assert res.status == "ok" and [r.percent for r in res.rows] == [Decimal("12.96")]


def test_a_header_one_column_right_of_its_figures_is_read_when_every_column_agrees() -> None:
    head = [
        [
            "Name",
            "",
            "Year ended March 31, 2026",
            "% of revenue",
            "Year ended March 31, 2025",
            "% of revenue",
        ]
    ]
    body = [["A Ltd", "945.41", "12.96%", "3.0", "1.00%"]]  # header sits one cell to the right
    res = check(_doc(body, head), SECTIONS)
    assert res.status == "ok" and [r.percent for r in res.rows] == [Decimal("12.96")]


def test_a_shift_that_is_not_the_same_for_every_column_is_withheld() -> None:
    head = [
        [
            "Name",
            "",
            "Year ended March 31, 2026",
            "% of revenue",
            "Year ended March 31, 2025",
            "% of revenue",
        ]
    ]
    body = [["A Ltd", "945.41", "12.96%", "", "3.0", "", "1.00%"]]  # second column moved by two
    res = check(_doc(body, head), SECTIONS)
    assert res.status == "withheld" and res.rows == []


def test_a_stray_in_percent_cell_under_the_header_is_ignored() -> None:
    body = [["", "", "", "(in %)", "", ""], ["A Ltd", "Sale", "945.41", "12.96%", "-", "-"]]
    res = check(_doc(body), SECTIONS)
    assert res.status == "ok" and len(res.rows) == 1


def test_a_percent_sign_only_in_prose_is_not_a_readable_percentage_table() -> None:
    head = [["Name", "Year ended March 31, 2026", "Year ended March 31, 2025"]]
    doc = _doc(
        [["A Ltd", "945.41", "-"]], head, extra="2% optionally convertible preference shares"
    )
    res = check(doc, SECTIONS)
    assert res.status == "no_percentage_table" and res.rows == [] and res.year is None


# --- percentages printed without a % sign: read only when they tie out to amount / revenue -------

REVENUE = {2026: Decimal(1_000_000_000)}  # 1,000 million rupees


def _plain_doc(head: list[list[str]], body: list[list[str]], unit: Unit | None = Unit.MILLION):  # type: ignore[no-untyped-def]
    rows = [*head, *body]
    table = Table(
        pdf_pages=[5], rows=rows, row_pages=[5] * len(rows), n_header_rows=len(head), unit=unit
    )
    return ParsedDocument(
        doc_id="d", n_pages=7, pages=[_page(n) for n in range(1, 8)], tables=[table]
    )


PCT_FIRST = [
    ["Party", "As a percentage of revenue from operations (in %)", "March 31, 2026"],
    ["", "", ""],
]
AMOUNT_FIRST = [["Party", "March 31, 2026", "% of revenue from operations"]]


def test_a_plain_number_share_is_read_when_it_ties_out_percentage_first() -> None:
    body = [["Evie", "6.74", "67.4"], ["Free", "0.50", "5.0"], ["Tiny", "0.00", "0.01"]]
    res = check(_plain_doc(PCT_FIRST, body), SECTIONS, REVENUE)
    assert res.status == "ok" and res.year == "FY2026"
    assert [(r.percent, r.amount) for r in res.rows] == [(Decimal("6.74"), Decimal("67.4"))]


def test_a_plain_number_share_is_read_when_it_ties_out_amount_first() -> None:
    body = [["Sales", "145.50", "14.55"], ["Loan", "80.20", "8.02"], ["Rent", "1.0", "0.10"]]
    res = check(_plain_doc(AMOUNT_FIRST, body), SECTIONS, REVENUE)
    assert res.status == "ok"
    assert sorted(r.percent for r in res.rows) == [Decimal("8.02"), Decimal("14.55")]


def test_an_amount_is_never_read_as_a_share_when_the_columns_do_not_tie() -> None:
    # 33.41 and 49.65 are amounts; read as shares they would be false alarms. They tie to nothing.
    body = [["A", "0.19", "33.41"], ["B", "0.28", "49.65"], ["C", "0.70", "90.0"]]
    res = check(_plain_doc(PCT_FIRST, body), SECTIONS, REVENUE)
    assert res.rows == [] and res.status != "ok"  # withheld, not "none"


def test_a_plain_number_share_without_verified_revenue_or_unit_is_withheld() -> None:
    body = [["Evie", "6.74", "67.4"], ["Free", "6.87", "68.7"]]
    assert check(_plain_doc(PCT_FIRST, body), SECTIONS, {}).status == "withheld"
    assert check(_plain_doc(PCT_FIRST, body, unit=None), SECTIONS, REVENUE).status == "withheld"


def test_a_share_of_total_expenses_is_not_a_share_of_revenue() -> None:
    head = [
        ["Party", "Amount", "Percentage contribution to the total expenses (%)", "March 31, 2026"]
    ]
    res = check(_plain_doc(head, [["A", "10.0", "9.50", ""]]), SECTIONS, REVENUE)
    assert res.rows == [] and res.status == "withheld"


def test_a_header_split_from_its_rows_reads_nothing_by_itself() -> None:
    doc = _plain_doc(AMOUNT_FIRST, [])  # a header and nothing under it
    res = check(doc, SECTIONS, REVENUE)
    assert res.status != "ok" and res.rows == []


def test_figures_with_no_header_of_their_own_are_withheld() -> None:
    body = [["Sales", "145.50", "14.55"], ["Loan", "80.20", "8.02"]]
    doc = _plain_doc([], body)
    doc.pages[4].blocks.append(
        Block(pdf_page=5, bbox=BBox(x0=0, top=0, x1=1, bottom=1), text="amounts in % terms")
    )
    res = check(doc, SECTIONS, REVENUE)
    assert res.rows == [] and any("no header of their own" in w[1] for w in res.withheld)


def test_a_date_split_across_lines_in_a_narrow_column_is_still_read() -> None:
    head = [["Party", "As at Marc h 31, 2026", "% of revenue from operation s"]]
    body = [["Sales", "145.50", "14.55"], ["Loan", "80.20", "8.02"]]
    assert check(_plain_doc(head, body), SECTIONS, REVENUE).year == "FY2026"


# --- coverage: rows the table reader never saw cannot be reported as absent ----------------------


def test_a_page_with_figures_the_tables_did_not_capture_is_withheld() -> None:
    body = [["A Ltd", "Sale", "945.41", "1.96%", "-", "-"]]
    text = (
        "A 1.50 2.50 3.50 4.50 5.50 6.50 7.50 8.50 9.50 10.50 11.50 12.50"  # 12 figures on the page
    )
    res = check(_doc(body), SECTIONS, pdf_text=lambda _p: text)
    assert res.status in {"partial", "withheld"} and res.rows == []
    assert any("rows may be missing" in w[1] for w in res.withheld)


def test_a_page_whose_figures_were_all_captured_is_read_normally() -> None:
    body = [["A Ltd", "Sale", "945.41", "12.96%", "-", "-"]]
    text = "A Ltd Sale 945.41 12.96% - -"  # the page prints exactly what the table holds
    res = check(_doc(body), SECTIONS, pdf_text=lambda _p: text)
    assert res.status == "ok" and len(res.rows) == 1 and res.withheld == []


def test_plain_number_order_from_other_tables_is_used_only_if_every_shown_row_ties() -> None:
    # Table one ties by itself (amount first). Table two is too small to tie, so it borrows the
    # order, and its large figure that does not tie must not be shown.
    head = AMOUNT_FIRST
    big = [["Sales", "145.50", "14.55"], ["Loan", "80.20", "8.02"]]
    small_ok = [["Other", "70.00", "7.00"]]
    small_bad = [["Odd", "33.41", "9.99"]]
    unit = Unit.MILLION
    tables = [
        Table(pdf_pages=[5], rows=[*head, *big], row_pages=[5] * 3, n_header_rows=1, unit=unit),
        Table(
            pdf_pages=[5], rows=[*head, *small_ok], row_pages=[5] * 2, n_header_rows=1, unit=unit
        ),
        Table(
            pdf_pages=[6], rows=[*head, *small_bad], row_pages=[6] * 2, n_header_rows=1, unit=unit
        ),
    ]
    doc = ParsedDocument(
        doc_id="d", n_pages=7, pages=[_page(n) for n in range(1, 8)], tables=tables
    )
    res = check(
        doc, [Section("SUMMARY OF RELATED PARTY TRANSACTIONS", 5, 5), Section("N", 8, 8)], REVENUE
    )
    shown = sorted(r.percent for r in res.rows)
    assert Decimal("9.99") not in shown  # 33.41 / 1000 is 3.34%, not 9.99%: never shown
    assert Decimal("14.55") in shown and Decimal("7.00") in shown


# --- rows the table reader left as plain text are recovered, and tied out like any other ---------

WIDE_HEAD = [["S.No", "Particulars", "As at March 31, 2026", "", "% of revenue from operations"]]


def _split_doc(lines: list[str]) -> tuple[ParsedDocument, str]:
    """A header-only table (the parser lost the rows) and the rows as a plain-text block."""
    header = Table(pdf_pages=[5], rows=WIDE_HEAD, row_pages=[5], n_header_rows=1, unit=Unit.MILLION)
    text = "\n".join(lines)
    block = Block(pdf_page=5, bbox=BBox(x0=0, top=0, x1=1, bottom=1), text=text)
    page = ParsedPage(
        pdf_page=5, width=1, height=1, alnum_chars=10, n_images=0, image_coverage=0,
        needs_ocr=False, blocks=[block],
    )  # fmt: skip
    pages = [_page(n) for n in range(1, 8)]
    pages[4] = page
    return ParsedDocument(doc_id="d", n_pages=7, pages=pages, tables=[header]), text


def _good_lines() -> list[str]:
    pairs = [
        ("145.50", "14.55"), ("80.20", "8.02"), ("10.00", "1.00"), ("20.00", "2.00"),
        ("30.00", "3.00"), ("5.00", "0.50"), ("40.00", "4.00"), ("60.00", "6.00"),
        ("70.00", "7.00"), ("90.00", "9.00"), ("15.00", "1.50"), ("25.00", "2.50"),
    ]  # fmt: skip
    return [f"{n} Item {n} {a} {p}" for n, (a, p) in enumerate(pairs, 1)]


def test_rows_left_as_text_are_recovered_and_tied_out() -> None:
    doc, text = _split_doc(_good_lines())
    res = check(doc, SECTIONS, REVENUE, pdf_text=lambda _p: text)
    shown = sorted(r.percent for r in res.rows)
    assert shown == [Decimal(x) for x in ("6.00", "7.00", "8.02", "9.00", "14.55")]
    assert all(p != 5 for p, _ in res.withheld)  # page 5 itself was fully read


def test_a_row_that_does_not_tie_withholds_its_whole_table() -> None:
    # 33.41 over 1,000 million is 3.34%, never 9.99%: one such row at or above the cut-off means the
    # layout is not what the other rows suggest, so nothing from the table is shown.
    doc, text = _split_doc([*_good_lines(), "13 Odd 33.41 9.99"])
    res = check(doc, SECTIONS, REVENUE, pdf_text=lambda _p: text)
    assert res.rows == []
    assert any("does not tie" in w[1] for w in res.withheld)


def test_rows_left_as_text_are_not_guessed_without_a_header_to_lay_over_them() -> None:
    doc, text = _split_doc([f"Item {n} {n}0.50 {n}.05" for n in range(1, 9)] + ["% of revenue"])
    doc.tables.clear()  # no header at all
    res = check(doc, SECTIONS, REVENUE, pdf_text=lambda _p: text)
    assert res.rows == [] and any("rows may be missing" in w[1] for w in res.withheld)


def test_a_table_without_a_header_uses_the_next_pages_copy_of_it() -> None:
    head = Table(
        pdf_pages=[6], rows=AMOUNT_FIRST, row_pages=[6], n_header_rows=1, unit=Unit.MILLION
    )
    body = Table(
        pdf_pages=[5],
        rows=[["Sales", "145.50", "14.55"], ["Loan", "80.20", "8.02"]],
        row_pages=[5, 5],
        unit=Unit.MILLION,
    )
    doc = ParsedDocument(
        doc_id="d", n_pages=7, pages=[_page(n) for n in range(1, 8)], tables=[body, head]
    )
    res = check(
        doc, [Section("SUMMARY OF RELATED PARTY TRANSACTIONS", 5, 5), Section("N", 8, 8)], REVENUE
    )
    assert sorted(r.percent for r in res.rows) == [Decimal("8.02"), Decimal("14.55")]
