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


def test_the_concluding_statement_outranks_a_defined_term_on_another_figure() -> None:
    """Laxmi Finance prints three tests; the turnover test carries the quoted defined term, but
    the figure the filing says it uses is the lowest one. Taking the quoted one showed 49.14."""
    doc = _doc(
        "(i) 5% of the average profit i.e. ₹ 12.41 million; or (ii) 2% of the net worth i.e. "
        "₹ 51.49 million; or (iii) 2% of the turnover i.e. ₹ 49.14 million (“Materiality "
        "Threshold”). Accordingly, ₹ 12.41 million being the lowest of the above criteria has been "
        "considered as Materiality Threshold for the purpose of this section."
    )
    res = check(doc, SECTIONS)
    assert res.litigation and res.litigation.rupees == Decimal("12410000")


def test_lakhs_are_read_and_converted() -> None:
    doc = _doc("Accordingly, the Material Threshold is determined to be ₹ 140.17 lakhs.")
    res = check(doc, SECTIONS)
    assert res.litigation and res.litigation.rupees == Decimal("14017000")


def test_thresholds_for_different_parties_are_withheld() -> None:
    doc = _doc(
        "any litigation which exceeds ₹616.4 million, being the amount equivalent to 5% of the "
        "profit. For Bajaj Finance, litigation which exceeds ₹5,497.8 million, being 5% of the "
        "consolidated profit."
    )
    res = check(doc, SECTIONS)
    assert res.litigation is None and res.withheld and res.withheld[0][0] == "litigation"


# ---- wordings from the third label set (sentences as the filings print them) ----------------
def _lit(text: str) -> Decimal | None:
    r = check(_doc(text), SECTIONS)
    return r.litigation.rupees if r.litigation else None


def _cred(text: str) -> Decimal | None:
    r = check(_doc(text), SECTIONS)
    return r.creditor.rupees if r.creditor else None


def test_a_single_five_percent_of_profit_test_stated_as_in_excess_of_being() -> None:
    text = (
        "the claim value involved in any such pending litigation is in excess of 5 % of the "
        "average of absolute value of profit/ loss after tax for last three financial years, "
        "being ₹ 16.93 million as per the Restated Consolidated Financial Information; or"
    )
    assert _lit(text) == Decimal("16930000")


def test_exceeds_the_amount_shall_be_considered_material_litigation() -> None:
    text = (
        "the monetary value of which or the adverse impact resulting from such litigation "
        "exceeds ₹6.02 million shall be considered Material Litigation."
    )
    assert _lit(text) == Decimal("6020000")


def test_the_defined_term_after_a_figure_across_a_sentence_end() -> None:
    text = (
        "(a) two percent of turnover, being ₹ 325.76 million for the most recent year; or "
        "(b) two percent of net worth, being ₹ 78.99 million as at the end of the year; or "
        "(c) five percent of the average of absolute value of profit or loss after tax, being "
        "₹ 19.52 million for the last three Financial Years as per the Restated Consolidated "
        "Financial Information. (“Materiality Threshold”)."
    )
    assert _lit(text) == Decimal("19520000")


def test_exceeding_the_lower_of_the_tests_i_e_the_figure() -> None:
    text = (
        "Accordingly, any transaction exceeding the lower of i, ii or iii herein mentioned "
        "i.e. ₹138.09 Lakhs, will be considered for the herein mentioned purpose."
    )
    assert _lit(text) == Decimal("13809000")


def test_a_figure_followed_by_the_board_approval_then_the_defined_term() -> None:
    text = (
        "in this case being 5% of the average of absolute value of profit after tax for the "
        "last three Fiscals, i.e., ₹ 426.75 million, as approved pursuant to Board resolution "
        "dated September 28, 2026 (“Materiality Threshold”); or (b) any outstanding litigation"
    )
    assert _lit(text) == Decimal("426750000")


def test_a_creditor_figure_written_as_a_percentage_of_payables_which_is() -> None:
    text = (
        "all creditors of our Company to whom the amount due exceeds 5.00% of the total trade "
        "payables of the Company are material creditors (i.e., 5.00% of ₹463.11 million which "
        "is ₹ 23.16 million based on the Restated Consolidated Financial Statements)."
    )
    assert _cred(text) == Decimal("23160000")  # not 463.11, the total payables


def test_total_trade_payables_are_never_taken_for_the_creditor_threshold() -> None:
    paras = (
        "creditors of our Company to whom the amount due is equal to, or in excess of, five per "
        "cent. of the total trade payables of our Company i.e. ₹ 130.64 million as at the end of "
        "the latest financial period would be considered as material creditors."
    )
    swastika = (
        "creditors would be considered as material creditors. The material trade payables of "
        "our Company as on March 31, 2026 were ₹3,699.50 Lakhs."
    )
    assert _cred(paras) is None and _cred(swastika) is None


def test_the_earlier_wordings_still_win_where_they_state_a_conclusion() -> None:
    text = (
        "(iii) 5% of the average of absolute value of profit, being ₹ 55.85 million, "
        "Accordingly, ₹ 55.85 million being the lowest of the above criteria has been "
        "considered as the materiality threshold. In excess of 5 % of the average of absolute "
        "value of profit, being ₹ 99.00 million."
    )
    assert _lit(text) == Decimal("55850000")
