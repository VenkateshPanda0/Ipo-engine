from decimal import Decimal

from ipo_engine.checks.litigation import check
from ipo_engine.parse.models import BBox, Block, ParsedDocument, ParsedPage
from ipo_engine.segment import Section

SECTIONS = [Section("OUTSTANDING LITIGATION AND MATERIAL DEVELOPMENTS", 3, 3), Section("N", 9, 9)]


def _page(n: int, text: str) -> ParsedPage:
    blocks = [Block(pdf_page=n, bbox=BBox(x0=0, top=0, x1=1, bottom=1), text=text)] if text else []
    return ParsedPage(
        pdf_page=n, width=1, height=1, alnum_chars=10, n_images=0, image_coverage=0,
        needs_ocr=False, blocks=blocks,
    )  # fmt: skip


def _doc(*texts: str) -> ParsedDocument:
    pages = [_page(n, texts[n - 3] if 3 <= n < 3 + len(texts) else "") for n in range(1, 10)]
    return ParsedDocument(doc_id="d", n_pages=9, pages=pages, tables=[])


def test_both_thresholds_are_read_with_page_and_sentence() -> None:
    doc = _doc(
        "Accordingly, ₹ 76.07 million has been considered as the Materiality Threshold. "
        "A creditor is material if dues exceeding ₹37.58 million are owed."
    )
    res = check(doc, SECTIONS)
    assert res.status == "ok"
    assert res.litigation and res.litigation.rupees == Decimal("76070000")
    assert res.litigation.page == 3 and "Materiality Threshold" in res.litigation.span
    assert res.creditor and res.creditor.rupees == Decimal("37580000")


def test_crore_is_converted_to_rupees() -> None:
    res = check(
        _doc("i.e. ₹ 8.33 crores has been considered as the Materiality Threshold."), SECTIONS
    )
    assert res.litigation and res.litigation.rupees == Decimal("83300000")


def test_a_creditor_figure_is_never_taken_for_the_litigation_threshold() -> None:
    """Some filings word the creditor test as 'exceeds ₹N, which is 5% of trade payables'. That
    figure is the creditor threshold; reading it as the litigation one showed a wrong number."""
    doc = _doc(
        "outstanding dues to any creditor which exceeds ₹ 51.29 million, which is 5 % of the "
        "total outstanding dues (i.e. consolidated trade payables) of our Company."
    )
    res = check(doc, SECTIONS)
    assert res.litigation is None
    assert res.creditor and res.creditor.rupees == Decimal("51290000")


def test_different_figures_are_withheld_not_picked() -> None:
    doc = _doc(
        "₹ 10.00 million has been considered as the Materiality Threshold. "
        "Later, ₹ 12.00 million has been considered as the Materiality Threshold."
    )
    res = check(doc, SECTIONS)
    assert res.litigation is None and res.withheld and res.withheld[0][0] == "litigation"


def test_nothing_printed_is_not_found_and_no_section_is_said() -> None:
    assert check(_doc("Except as stated, there is no litigation."), SECTIONS).status == "not_found"
    assert check(_doc("x"), [Section("OBJECTS OF THE OFFER", 3, 3)]).status == "no_section"


def test_a_long_sentence_is_clipped_around_the_figure_not_before_it() -> None:
    long = (
        "word " * 80
        + "so the amount of ₹ 15.50 million has been considered as the Materiality Threshold."
    )
    res = check(_doc(long), SECTIONS)
    assert res.litigation and "15.50 million" in res.litigation.span
    assert len(res.litigation.span) <= 224
