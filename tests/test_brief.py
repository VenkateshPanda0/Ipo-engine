from datetime import UTC, date, datetime
from decimal import Decimal

from ipo_engine.analyze import (
    AnalysisReport,
    ConsensusRecord,
    FactRecord,
    Summary,
    VerifiedNumber,
)
from ipo_engine.brief import brief_html, brief_text, build_brief, triage_html
from ipo_engine.extract.models import Concept
from ipo_engine.extract.periods import Period
from ipo_engine.flags.engine import Citation, Flag, RuleAudit
from ipo_engine.flags.spec import Source
from ipo_engine.ingest.manifest import DocType, ManifestEntry, Platform
from ipo_engine.parse.units import Unit

CRORE = Decimal(10_000_000)


def _entry(issuer: str = "Demo Ltd") -> ManifestEntry:
    return ManifestEntry(
        doc_id="demo", url="https://example.invalid/demo.pdf", issuer=issuer,
        doc_type=DocType.RHP, platform=Platform.MAINBOARD, filing_date=date(2026, 1, 5),
        sha256="ab" * 32, size_bytes=1, fetched_at=datetime.now(UTC), local_path="raw/demo.pdf",
        content_type="application/pdf",
    )  # fmt: skip


def _summary() -> Summary:
    return Summary(
        doc_id="demo", values_total=10, values_verified=9, footing_checked=4, footing_passed=4,
        consensus_groups=5, consensus_multi_source=4, consensus_unanimous_multi=3,
        values_without_period=0, values_without_unit=0, concepts={}, issue_facts_total=0,
        issue_facts_verified=0, values_ambiguous_dropped=0, flags=0, rules_decisive=2,
        rules_applicable=5,
    )  # fmt: skip


def _fact(key: str, crore: int, page: int) -> FactRecord:
    return FactRecord(key=key, value=crore * CRORE, step=Decimal(1), pdf_page=page, span="s")


def _flag(severity: str, page: int, name: str = "Rule") -> Flag:
    return Flag(
        rule_id=name, rule_name=name, severity=severity, explanation="why", numbers={},
        citations=[Citation(pdf_page=page, span="x")],
        sources=[Source(kind="regulation", ref="r", clause="c", checked_on=date(2026, 1, 1))],
        heuristic=False,
    )  # fmt: skip


def _report(**kw: object) -> AnalysisReport:
    base: dict[str, object] = dict(
        summary=_summary(), values=[], issue_facts=[], footing=[], consensus=[], facts=[],
        flags=[], rule_audit=[],
    )  # fmt: skip
    return AnalysisReport(**{**base, **kw})


def test_growth_is_the_newest_year_over_the_one_before_and_only_when_both_are_positive() -> None:
    facts = [
        _fact("financials.revenue_from_operations.FY2026", 120, 9),
        _fact("financials.revenue_from_operations.FY2025", 100, 9),
        _fact("financials.profit_after_tax.FY2026", 5, 9),
        _fact("financials.profit_after_tax.FY2025", -3, 9),
    ]
    b = build_brief(_report(facts=facts), _entry())
    by = {m.label: m for m in b.metrics}
    assert by["Revenue from operations"].growth_pct == Decimal("20.0")
    assert by["Profit after tax"].growth_pct is None  # across a loss a percentage misleads


def test_read_first_puts_the_most_serious_item_first_and_names_its_page() -> None:
    report = _report(
        flags=[_flag("low", 30, "Low"), _flag("high", 12, "High")],
        pages_with_hidden_text=[88],
    )
    items = build_brief(report, _entry()).read_first
    assert [i.kind for i in items] == ["hidden_text", "flag", "flag"]  # hidden text outranks all
    assert [i.page for i in items][1:] == [12, 30]  # high before low


def test_a_withheld_figure_is_listed_to_check_never_shown() -> None:
    report = _report(
        consensus=[
            ConsensusRecord(
                concept=Concept.PROFIT_AFTER_TAX, period_key="FY2025", chosen_raw="100",
                chosen_page=40, chosen_rupees=Decimal(1), supporters=1, total=3,
                unanimous=False, alternatives_raw=["90", "80"],
            )
        ]
    )  # fmt: skip
    b = build_brief(report, _entry())
    (item,) = b.read_first
    assert item.kind == "conflict" and item.page == 40 and "3 different readings" in item.text
    assert b.metrics == []  # nothing was shown for it


def test_a_rule_that_could_not_run_is_listed_as_unchecked() -> None:
    audit = [RuleAudit(rule_id="R1", status="missing_inputs", missing=["objects.gcp_amount"])]
    (item,) = build_brief(_report(rule_audit=audit), _entry()).read_first
    assert item.kind == "unchecked" and "objects.gcp_amount" in item.text and item.page is None


def test_no_items_is_not_called_a_clean_bill_of_health() -> None:
    html = brief_html(build_brief(_report(), _entry()))
    assert "not</strong> a clean bill of health" in html
    assert "Nothing flagged" in brief_text(build_brief(_report(), _entry()))


def test_pages_link_to_the_pdf_and_document_text_is_escaped() -> None:
    hostile = "<script>alert(1)</script>"
    report = _report(flags=[_flag("high", 12, hostile)])
    html = brief_html(build_brief(report, _entry(issuer=hostile)))
    assert "<script>alert(1)</script>" not in html
    assert 'href="https://example.invalid/demo.pdf#page=12"' in html


def test_triage_orders_the_filing_with_the_most_serious_item_first() -> None:
    calm = build_brief(_report(), _entry("Calm Ltd"))
    alarm = build_brief(_report(flags=[_flag("high", 3)]), _entry("Alarm Ltd"))
    html = triage_html([("brief_calm.html", calm), ("brief_alarm.html", alarm)])
    assert html.index("Alarm Ltd") < html.index("Calm Ltd")


def test_withheld_figures_of_older_years_are_counted_not_listed() -> None:
    def rec(period: str, page: int) -> ConsensusRecord:
        return ConsensusRecord(
            concept=Concept.PROFIT_AFTER_TAX, period_key=period, chosen_raw="1", chosen_page=page,
            chosen_rupees=Decimal(1), supporters=1, total=2, unanimous=False,
            alternatives_raw=["2"],
        )  # fmt: skip

    report = _report(consensus=[rec("FY2026", 10), rec("FY2025", 11), rec("FY2022", 12)])
    items = build_brief(report, _entry()).read_first
    assert [i.page for i in items if i.page] == [10, 11]  # the two latest years, by page
    assert any("earlier years" in i.text and i.page is None for i in items)


def _vn(raw: str, page: int, span: str, verified: bool = True) -> VerifiedNumber:
    return VerifiedNumber(
        concept=Concept.PROFIT_AFTER_TAX, label="Profit", raw=raw, value=Decimal(raw),
        unit=Unit.CRORE, period=Period(end=date(2025, 3, 31), months=12, instant=False),
        column_header="FY2025", pdf_page=page, table_pages=[page], table_id=0, span=span,
        confidence=0.9, verified=verified, failures=[],
    )  # fmt: skip


def _conflict_report(values: list[VerifiedNumber]) -> AnalysisReport:
    return _report(
        values=values,
        consensus=[
            ConsensusRecord(
                concept=Concept.PROFIT_AFTER_TAX, period_key="FY2025", chosen_raw="100",
                chosen_page=40, chosen_rupees=Decimal(1), supporters=1, total=2,
                unanimous=False, alternatives_raw=["90"],
            )
        ],
    )  # fmt: skip


def test_a_withheld_figure_shows_its_verified_table_rows_chosen_first() -> None:
    vals = [_vn("90", 55, "Profit | 90"), _vn("100", 40, "Profit | 100"),
            _vn("80", 70, "Profit | 80", verified=False)]  # fmt: skip
    (item,) = build_brief(_conflict_report(vals), _entry()).read_first
    assert item.evidence == ((40, "Profit | 100"), (55, "Profit | 90"))  # unverified row left out
    text = brief_text(build_brief(_conflict_report(vals), _entry()))
    assert "p.55: Profit | 90" in text


def test_flag_citations_are_shown_and_evidence_is_escaped_in_html() -> None:
    fl = _flag("high", 12)
    fl = fl.model_copy(update={"citations": [Citation(pdf_page=12, span="<b>x</b> " + "y" * 300)]})
    b = build_brief(_report(flags=[fl]), _entry())
    (page, span) = b.read_first[0].evidence[0]
    assert page == 12 and len(span) <= 200
    html = brief_html(b)
    assert "<b>x</b>" not in html and "&lt;b&gt;x&lt;/b&gt;" in html and "#page=12" in html


def test_items_name_their_section_when_a_map_is_given() -> None:
    from ipo_engine.segment import Section

    secs = [Section("RISK FACTORS", 10, 5), Section("OBJECTS OF THE OFFER", 50, 45)]
    b = build_brief(_report(flags=[_flag("high", 60)]), _entry(), secs)
    assert b.read_first[0].section == "Objects Of The Offer"
    assert "(Objects Of The Offer)" in brief_text(b)
    assert build_brief(_report(flags=[_flag("high", 60)]), _entry()).read_first[0].section == ""


def test_repeated_readings_are_counted_once() -> None:
    report = _report(
        consensus=[
            ConsensusRecord(
                concept=Concept.PROFIT_AFTER_TAX, period_key="FY2025", chosen_raw="100",
                chosen_page=40, chosen_rupees=Decimal(1), supporters=1, total=3,
                unanimous=False, alternatives_raw=["90", "90", "100"],
            )
        ]
    )  # fmt: skip
    (item,) = build_brief(report, _entry()).read_first
    assert "2 different readings (100, 90)" in item.text


def _rp(status: str, rows: list[tuple[int, str]] | None = None, withheld: bool = False):  # type: ignore[no-untyped-def]
    from ipo_engine.analyze import RelatedPartyRecord, RelatedPartyRow

    made = [
        RelatedPartyRow(
            page=p,
            percent=Decimal(pc),
            amount=Decimal("945.41"),
            text="row text",
            mirror_pages=[107],
        )
        for p, pc in rows or []
    ]
    return RelatedPartyRecord(
        status=status,
        cutoff_percent=Decimal("5.00"),
        year="FY2026",
        pages=[69, 70],
        rows=made,
        withheld=[(69, "reason")] if withheld else [],
    )


def test_a_large_related_party_row_is_an_item_with_its_page_and_row() -> None:
    b = build_brief(_report(related_party=_rp("ok", [(70, "12.96")])), _entry())
    (item,) = b.read_first
    assert item.kind == "related_party" and item.page == 70 and "12.96%" in item.text
    assert item.evidence[0] == (70, "row text") and item.evidence[1][0] == 107


def test_an_unreadable_related_party_table_is_listed_to_read_by_hand() -> None:
    (item,) = build_brief(
        _report(related_party=_rp("withheld", withheld=True)), _entry()
    ).read_first
    assert item.kind == "unchecked" and item.page == 69 and "by hand" in item.text


def test_a_clean_related_party_read_is_a_note_not_an_item() -> None:
    b = build_brief(_report(related_party=_rp("ok")), _entry())
    assert b.read_first == [] and "no transaction is printed at or above 5.00%" in b.notes[0]
    assert b.notes[0] in brief_text(b) and "no transaction is printed" in brief_html(b)


def test_the_home_page_links_brief_and_full_report() -> None:
    calm = build_brief(_report(), _entry("Calm Ltd"))
    html = triage_html([("brief_demo.html", calm)], {"brief_demo.html": "demo.html"})
    assert 'href="brief_demo.html"' in html and 'href="demo.html"' in html
