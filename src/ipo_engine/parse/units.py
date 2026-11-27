"""Currency-unit detection and Indian-format number parsing.

Offer documents state units in table captions ("(₹ in lakhs)", "(Rs. in Million)",
"All amounts in ₹ crore, unless otherwise stated"). Units vary by issuer and sometimes by
table within one document, so they are detected per table and stored with it.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from enum import StrEnum


class Unit(StrEnum):
    RUPEES = "rupees"
    THOUSAND = "thousand"
    LAKH = "lakh"
    MILLION = "million"
    CRORE = "crore"
    BILLION = "billion"


MULTIPLIER: dict[Unit, Decimal] = {
    Unit.RUPEES: Decimal(1),
    Unit.THOUSAND: Decimal(10) ** 3,
    Unit.LAKH: Decimal(10) ** 5,
    Unit.MILLION: Decimal(10) ** 6,
    Unit.CRORE: Decimal(10) ** 7,
    Unit.BILLION: Decimal(10) ** 9,
}

_WORD_TO_UNIT: dict[str, Unit] = {
    "lakh": Unit.LAKH,
    "lakhs": Unit.LAKH,
    "lac": Unit.LAKH,
    "lacs": Unit.LAKH,
    "crore": Unit.CRORE,
    "crores": Unit.CRORE,
    "cr": Unit.CRORE,
    "million": Unit.MILLION,
    "millions": Unit.MILLION,
    "mn": Unit.MILLION,
    "mm": Unit.MILLION,
    "billion": Unit.BILLION,
    "billions": Unit.BILLION,
    "bn": Unit.BILLION,
    "thousand": Unit.THOUSAND,
    "thousands": Unit.THOUSAND,
    "000": Unit.THOUSAND,
    "000s": Unit.THOUSAND,
    "rupees": Unit.RUPEES,
}

_UNIT_WORD = r"(lakhs?|lacs?|crores?|cr|millions?|mn|mm|billions?|bn|thousands?|'?000s?)(?![a-z])"
_CURRENCY = r"(?:₹|`|rs\.?|inr|rupees)"

# "in lakhs", "in ₹ million", "amounts in Rs. crore"  /  "₹ in lakhs", "Rs. million", "INR Mn"
_PATTERNS = (
    re.compile(rf"\bin\s*{_CURRENCY}?\s*{_UNIT_WORD}", re.IGNORECASE),
    re.compile(rf"{_CURRENCY}\s*(?:in\s*)?{_UNIT_WORD}", re.IGNORECASE),
)


# "(US$ in million)" declares dollars: scaling those figures as rupees would be silently wrong.
_FOREIGN_CURRENCY = re.compile(r"us\s?\$|\busd\b|\$|€|\beur\b|£|\bgbp\b", re.IGNORECASE)


def detect_unit(text: str) -> tuple[Unit, str] | None:
    """Return (unit, matched_text) for the first unit declaration in `text`, if any.

    Abstains (None) when the text names a currency other than the rupee, or declares two
    different units ("(₹ in Crore) (₹ in Lakhs)"): a guess there would scale a table wrongly.
    """
    if _FOREIGN_CURRENCY.search(text):
        return None
    found: list[tuple[int, Unit, str]] = []
    for pat in _PATTERNS:
        for m in pat.finditer(text):
            word = m.group(1).lower().lstrip("'")
            unit = _WORD_TO_UNIT.get(word)
            if unit is not None:
                found.append((m.start(), unit, m.group(0).strip()))
    if not found or len({u for _, u, _ in found}) > 1:
        return None
    best = min(found, key=lambda f: f[0])
    return best[1], best[2]


def to_rupees(value: Decimal, unit: Unit) -> Decimal:
    return value * MULTIPLIER[unit]


_NIL = {"nil", "-", "–", "—", "‒"}
_MISSING = {"", "na", "n.a.", "n.a", "n/a", "nm", "n.m."}


def parse_amount(cell: str, *, allow_percent: bool = False) -> Decimal | None:
    """Parse a table cell like '1,23,456.78', '(1,234)', '₹ 12.5', 'Nil' into a Decimal.

    - parentheses and leading minus (ASCII or Unicode) mean negative
    - 'Nil' means zero; '-', 'NA', blanks mean "no value" (None)
    - trailing footnote markers (* # ^ †) are ignored
    - percentages are rejected unless `allow_percent`
    """
    s = cell.strip().replace(" ", " ")
    if not s:
        return None
    low = s.lower()
    if low == "nil":
        return Decimal(0)
    if low in _NIL or low in _MISSING:
        return None
    s = re.sub(r"[*#^†‡]+$", "", s).strip()
    if s.endswith("%"):
        if not allow_percent:
            return None
        s = s[:-1].strip()
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1].strip()
    s = re.sub(r"^(?:₹|`|rs\.?|inr)\s*", "", s, flags=re.IGNORECASE)
    if s[:1] in "-−–—":
        negative, s = True, s[1:].strip()
    if not re.fullmatch(r"\d{1,3}(?:,\d{2,3})*(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+", s):
        return None
    try:
        value = Decimal(s.replace(",", ""))
    except InvalidOperation:
        return None
    return -value if negative else value
