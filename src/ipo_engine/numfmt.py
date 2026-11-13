"""One place for how numbers are shown.

Rules: rupee amounts in the Indian system (1,23,45,678.50) and, for filings, in ₹ crore with two
decimals; the same number of decimals down a column; an ASCII minus in terminal text and a true
minus sign on pages, where a negative is also marked so a loss stands out; percentages with one
decimal and an explicit sign when they are a change. Money is Decimal, never a float.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from html import escape

CRORE = Decimal(10_000_000)
MINUS = "−"


def indian(x: Decimal, places: int = 2) -> str:
    """12345678.5 -> '1,23,45,678.50' (lakh/crore grouping), negatives with an ASCII minus."""
    q = x.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    sign = "-" if q < 0 else ""
    whole, _, frac = f"{abs(q):f}".partition(".")
    head, tail = whole[:-3], whole[-3:]
    groups: list[str] = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    body = ",".join([*groups, tail]) if groups else tail
    return f"{sign}{body}.{frac}" if places else f"{sign}{body}"


def crore(rupees: Decimal, places: int = 2) -> str:
    """Rupees as ₹ crore text (ASCII minus)."""
    return indian(rupees / CRORE, places)


def amount_html(text: str) -> str:
    """A formatted number for a page: true minus, and negatives marked with class `neg`."""
    if text.startswith("-"):
        return f"<span class=neg>{MINUS}{escape(text[1:])}</span>"
    return escape(text)


def crore_html(rupees: Decimal, places: int = 2) -> str:
    return amount_html(crore(rupees, places))


def pct(value: Decimal, places: int = 1, *, signed: bool = False) -> str:
    """A percentage with fixed decimals; `signed` adds + for gains and a true minus for falls."""
    q = value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    sign = "+" if signed and q > 0 else (MINUS if q < 0 else "")
    return f"{sign}{abs(q):f}%"
