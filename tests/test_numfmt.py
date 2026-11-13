from decimal import Decimal

from ipo_engine.numfmt import MINUS, amount_html, crore, crore_html, indian, pct


def test_indian_grouping_and_rounding() -> None:
    assert indian(Decimal("12345678.5")) == "1,23,45,678.50"
    assert indian(Decimal("999.999")) == "1,000.00"
    assert indian(Decimal("-1234.5")) == "-1,234.50"
    assert indian(Decimal("0")) == "0.00"
    assert indian(Decimal("1234567"), 0) == "12,34,567"


def test_crore_is_rupees_over_ten_million_with_two_decimals() -> None:
    assert crore(Decimal("159133200000")) == "15,913.32"
    assert crore(Decimal("-6815300000")) == "-681.53"


def test_pages_use_a_true_minus_and_mark_losses_but_text_does_not() -> None:
    assert crore_html(Decimal("-6815300000")) == f"<span class=neg>{MINUS}681.53</span>"
    assert crore_html(Decimal("6815300000")) == "681.53"
    assert amount_html("-<b>") == f"<span class=neg>{MINUS}&lt;b&gt;</span>"


def test_percentages_have_fixed_decimals_and_signs_only_for_changes() -> None:
    assert pct(Decimal("40.43")) == "40.4%"
    assert pct(Decimal("40.43"), signed=True) == "+40.4%"
    assert pct(Decimal("-3.05"), signed=True) == f"{MINUS}3.1%"
    assert pct(Decimal("0"), signed=True) == "0.0%"
    assert pct(Decimal("12.96"), places=2) == "12.96%"
