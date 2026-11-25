"""Outstanding litigation, first slice: the two monetary thresholds the section prints.

The section opens with the issuer's materiality policy: the amount above which a civil matter is
disclosed on its own, and the amount above which dues to a creditor are called material. Both are
printed figures, so they are read, not computed, and each carries its page and the sentence it came
from. A threshold is shown only when exactly one distinct figure matches on the section's first
pages; none found, or several different ones, is reported as such and nothing is guessed. The
matters themselves (counts, amounts by type) are a later slice. Labels: labels/litigation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from ipo_engine.parse.models import ParsedDocument
from ipo_engine.segment import Section

SECTION_PAGES = 3  # the policy is printed on the section's first pages
SPAN_CHARS = 220
_UNIT = {
    "million": Decimal(10) ** 6,
    "crore": Decimal(10) ** 7,
    "crores": Decimal(10) ** 7,
    "lakh": Decimal(10) ** 5,
    "lakhs": Decimal(10) ** 5,
}
_AMT = r"₹\s*(?P<n>\d[\d,]*(?:\.\d+)?)\s*(?P<u>million|crores?|lakhs?)"
_Q = "[“\"']"  # opening quote
_QE = "[”\"']"  # closing quote
_NAME = r"Materiality\s+(?:Threshold|Amount)"
# How filings word the litigation threshold, strongest first. A concluding statement ("Accordingly,
# Rs N has been considered as the Materiality Threshold") names the figure the filing uses; when
# one is printed it outranks the weaker mentions (a defined term attached to one of several tests,
# the policy's own wording), which are read only when there is none.
_CONCLUDING = [
    re.compile(_AMT + r"\s+(?:has|have)\s+been\s+considered\s+as\s+(?:the\s+)?" + _NAME, re.I),
    re.compile(r"being\s*" + _AMT + r"[^.₹]{0,200}?considered\s+as\s+(?:the\s+)?" + _NAME, re.I),
    # "Rs N being the lowest of the above ... has been considered as the materiality threshold"
    re.compile(
        _AMT + r"[^.₹]{0,80}?(?:has|have)\s+been\s+considered\s+as\s+(?:the\s+)?" + _NAME, re.I
    ),
    # "a materiality threshold of Rs N", "the Material Threshold is determined to be Rs N"
    re.compile(
        r"Materiality\s+(?:Threshold|Amount)\s+(?:of|is\s+determined\s+to\s+be)\s*" + _AMT, re.I
    ),
    re.compile(r"Material\s+Threshold\s+is\s+determined\s+to\s+be\s*" + _AMT, re.I),
    re.compile(_AMT + r"\s+is\s+the\s+materiality\s+threshold", re.I),
    # '("Materiality Threshold"), which amounts to Rs N'
    re.compile(_NAME + _QE + r"\)?\s*,?\s*which\s+amounts?\s+to\s*" + _AMT, re.I),
    # "any transaction exceeding the lower of i, ii or iii herein mentioned i.e. Rs N"
    re.compile(r"exceeding\s+the\s+lower\s+of[^₹]{0,80}?" + _AMT, re.I),
    # "... exceeds Rs N shall be considered Material Litigation"
    re.compile(r"exceeds\s*" + _AMT + r"\s+shall\s+be\s+considered\s+material\s+litigation", re.I),
]
_STATED = [
    re.compile(_AMT + r"\s*\(\s*(?:the\s*)?" + _Q + _NAME + _QE, re.I),
    re.compile(
        r"(?:in\s+excess\s+of|exceeds)\s*"
        + _AMT
        + r"(?:\s*,\s*which\s+is\s+\d+\s*%|\s+individually)",
        re.I,
    ),
    # "exceeds Rs N, being (the amount equivalent to) 5% of ..."
    re.compile(
        r"exceeds\s*" + _AMT + r"\s*,\s*being\s+(?:the\s+amount\s+equivalent\s+to\s+)?\d+\s*%",
        re.I,
    ),
    # "in excess of 5% of the average of absolute value of profit ... , being Rs N": the one test
    # a filing states (several tests are not read this way: each must be the defined term)
    re.compile(
        r"(?:in\s+excess\s+of|exceeds)\s+\d+(?:\.\d+)?\s*%\s+of\s+the\s+average\s+of[^₹]{0,160}?"
        r"being\s*" + _AMT,
        re.I,
    ),
    # "Rs N [for the last three years ...] (“Materiality Threshold”)": the figure the defined term
    # is attached to, with no other figure between them (a full stop may precede the bracket)
    re.compile(
        _AMT + r"(?:[^₹.]|\.(?=\s*\())" + r"{0,140}?\(\s*(?:the\s*)?" + _Q + _NAME + _QE,
        re.I,
    ),
    # "the monetary amount of claim is equivalent to or in excess of Rs N"
    re.compile(
        r"monetary\s+amount\s+of\s+claim[^.₹]{0,80}?(?:in\s+excess\s+of|exceeds?)\s*" + _AMT,
        re.I,
    ),
]
_CREDITOR = re.compile(r"(?:exceed(?:s|ing)?|in\s+excess\s+of|which\s+is)\s*" + _AMT, re.I)
_CREDITOR_CONTEXT = re.compile(r"\bdues\b|\bcreditors?\b|\btrade\s+payables\b", re.I)


@dataclass(frozen=True)
class Threshold:
    rupees: Decimal
    printed: str  # the figure and unit as printed, e.g. "₹ 46.75 million"
    page: int
    span: str  # the sentence it came from, clipped


@dataclass
class Result:
    # ok | partial | no_section | not_found
    status: str
    pages: tuple[int, ...] = ()
    litigation: Threshold | None = None
    creditor: Threshold | None = None
    # (what, reason) for a threshold that was found more than once with different figures
    withheld: list[tuple[str, str]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.withheld is None:
            self.withheld = []


def _pages(doc: ParsedDocument, sections: list[Section]) -> tuple[int, ...]:
    for i, s in enumerate(sections):
        if "outstanding litigation" in s.title.lower():
            end = sections[i + 1].start_page if i + 1 < len(sections) else doc.n_pages + 1
            return tuple(range(s.start_page, min(end, s.start_page + SECTION_PAGES)))
    return ()


def _value(m: re.Match[str]) -> tuple[Decimal, str]:
    n = Decimal(m["n"].replace(",", ""))
    return n * _UNIT[m["u"].lower()], f"₹ {m['n']} {m['u'].lower()}"


def _whole_sentence(text: str, start: int, end: int) -> str:
    cut = text.rfind(". ", 0, start)
    lo = 0 if cut == -1 else cut + 2
    hi = text.find(". ", end)
    return text[lo : hi + 1 if hi != -1 else len(text)]


def _sentence(text: str, start: int, end: int) -> str:
    """The sentence the figure is in; when it is long, the stretch around the figure."""
    cut = text.rfind(". ", 0, start)
    lo = 0 if cut == -1 else cut + 2
    hi = text.find(". ", end)
    hi = len(text) if hi == -1 else hi + 1
    if hi - lo <= SPAN_CHARS:
        return text[lo:hi]
    a = max(lo, start - SPAN_CHARS // 2)
    b = min(hi, a + SPAN_CHARS)
    return ("…" if a > lo else "") + text[a:b] + ("…" if b < hi else "")


def _pick(found: list[tuple[Decimal, str, int, str]], what: str, res: Result) -> Threshold | None:
    figures = {f[0] for f in found}
    if not found:
        return None
    if len(figures) > 1:
        shown = sorted({f[1] for f in found})
        res.withheld.append((what, f"the section prints several different figures: {shown}"))
        return None
    rupees, printed, page, span = found[0]
    return Threshold(rupees, printed, page, span)


def check(doc: ParsedDocument, sections: list[Section]) -> Result:
    pages = _pages(doc, sections)
    if not pages:
        return Result("no_section")
    res = Result("ok", pages=pages)
    concluding: list[tuple[Decimal, str, int, str]] = []
    stated: list[tuple[Decimal, str, int, str]] = []
    cred: list[tuple[Decimal, str, int, str]] = []
    for page in doc.pages:
        if page.pdf_page not in pages:
            continue
        text = " ".join(" ".join(b.text.split()) for b in page.blocks)
        for tier, patterns in ((concluding, _CONCLUDING), (stated, _STATED)):
            for pat in patterns:
                for m in pat.finditer(text):
                    if _CREDITOR_CONTEXT.search(_whole_sentence(text, m.start(), m.end())):
                        continue  # a creditor figure, not the litigation threshold
                    v, printed = _value(m)
                    tier.append((v, printed, page.pdf_page, _sentence(text, m.start(), m.end())))
        for m in _CREDITOR.finditer(text):
            if not _CREDITOR_CONTEXT.search(text[max(0, m.start() - 250) : m.start()]):
                continue
            v, printed = _value(m)
            cred.append((v, printed, page.pdf_page, _sentence(text, m.start(), m.end())))
    res.litigation = _pick(concluding or stated, "litigation", res)
    res.creditor = _pick(cred, "creditor", res)
    if res.litigation is None and res.creditor is None and not res.withheld:
        res.status = "not_found"
    elif res.litigation is None or res.creditor is None:
        res.status = "partial"
    return res
