"""A one-page brief per filing, and a triage table across filings.

The full report lists everything that was found. The brief answers the question that costs a
reader time: what should I open first, and what can I skip? It states the issue and the latest
financials in a few lines, then a ranked "read first" list in which every item names its page. It
only restates what the analysis already verified (nothing new is read here), so it adds no new way
to be wrong; a figure the sources disagreed on is listed as something to check, never shown.

Text from the document is untrusted and escaped; the page has no script and works offline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal
from html import escape

from ipo_engine.analyze import AnalysisReport, ConsensusRecord, FactRecord
from ipo_engine.extract.periods import fiscal_key
from ipo_engine.ingest.manifest import ManifestEntry
from ipo_engine.report_html import CRORE, DISCLAIMER, indian
from ipo_engine.segment import Section, section_of

_FY = re.compile(r"^FY(\d{4})$")
_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2, "info": 3}
_METRICS = (
    ("revenue_from_operations", "Revenue from operations"),
    ("profit_after_tax", "Profit after tax"),
    ("cash_from_operations", "Cash from operations"),
    ("total_assets", "Total assets"),
)
_ISSUE = (
    ("issue.fresh_issue_amount", "Fresh issue"),
    ("issue.ofs_amount", "Offer for sale"),
    ("issue.total_issue_amount", "Total issue"),
)
# on a tie in rank, text a reader cannot see comes first: it undermines every figure beneath it
_KIND_ORDER = {"hidden_text": 0, "flag": 1, "related_party": 2, "conflict": 3, "unchecked": 4}
YEARS_SHOWN = 3
MAX_CONFLICT_READINGS = 4
SPAN_CHARS = 200


@dataclass(frozen=True)
class Item:
    """One thing to look at. `rank` orders the list: lower is read first."""

    rank: int
    kind: str  # flag | hidden_text | related_party | conflict | unchecked
    text: str
    page: int | None  # the page to open, if there is one
    # (page, text) rows the item rests on, each re-found on its page by the verifier
    evidence: tuple[tuple[int, str], ...] = ()
    section: str = ""  # the document section the page falls in, when the section map has one


@dataclass(frozen=True)
class Metric:
    label: str
    cells: list[tuple[str, Decimal, int]]  # (FY label, rupees, page), newest first
    growth_pct: Decimal | None  # newest over the one before, only when both are positive


@dataclass(frozen=True)
class Brief:
    issuer: str
    doc_type: str
    platform: str
    filed: str
    url: str
    issue: list[tuple[str, Decimal, int]]  # (label, rupees, page)
    metrics: list[Metric]
    read_first: list[Item]
    rules_checked: tuple[int, int]  # (decisive, applicable)
    numbers_verified: tuple[int, int]  # (verified, total)
    notes: tuple[str, ...] = ()  # things that were read and found unremarkable, stated plainly


def _growth(newest: Decimal, previous: Decimal) -> Decimal | None:
    if newest <= 0 or previous <= 0:
        return None  # a percentage change across zero or a loss misleads more than it informs
    return ((newest / previous - 1) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _metrics(facts: dict[str, FactRecord]) -> list[Metric]:
    out: list[Metric] = []
    for concept, label in _METRICS:
        years = sorted(
            (
                m.group(1)
                for k in facts
                if k.startswith(f"financials.{concept}.") and (m := _FY.match(k.rsplit(".", 1)[-1]))
            ),
            reverse=True,
        )[:YEARS_SHOWN]
        cells = [
            (
                f"FY{y}",
                facts[f"financials.{concept}.FY{y}"].value,
                facts[f"financials.{concept}.FY{y}"].pdf_page,
            )
            for y in years
        ]
        if cells:
            growth = _growth(cells[0][1], cells[1][1]) if len(cells) > 1 else None
            out.append(Metric(label, cells, growth))
    return out


RECENT_YEARS = 2  # a withheld figure matters most for the latest years; older ones are counted


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= SPAN_CHARS else text[: SPAN_CHARS - 1].rstrip() + "…"


def _readings(report: AnalysisReport, c: ConsensusRecord) -> tuple[tuple[int, str], ...]:
    """Table rows behind a withheld figure: verified readings only, the chosen one first."""
    rows: list[tuple[int, str, bool]] = []
    for v in report.values:
        if not v.verified or v.concept != c.concept or v.period is None:
            continue
        if fiscal_key(v.period) != c.period_key:
            continue
        rows.append((v.pdf_page, _clip(v.span), v.raw == c.chosen_raw))
    rows.sort(key=lambda r: not r[2])
    out: list[tuple[int, str]] = []
    for page, span, _ in rows:
        if (page, span) not in out:
            out.append((page, span))
    return tuple(out[:MAX_CONFLICT_READINGS])


def _conflicts(report: AnalysisReport) -> list[Item]:
    kept = {f.key for f in report.facts}
    withheld = [
        c
        for c in report.consensus
        if _FY.match(c.period_key) and f"financials.{c.concept.value}.{c.period_key}" not in kept
    ]
    years = [int(m.group(1)) for c in report.consensus if (m := _FY.match(c.period_key))]
    cutoff = max(years, default=0) - (RECENT_YEARS - 1)
    items: list[Item] = []
    older = 0
    for c in withheld:
        if int(c.period_key[2:]) < cutoff:
            older += 1
            continue
        readings = list(dict.fromkeys([c.chosen_raw, *c.alternatives_raw]))  # distinct, in order
        shown = ", ".join(readings[:MAX_CONFLICT_READINGS])
        more = (
            f" and {len(readings) - MAX_CONFLICT_READINGS} more"
            if len(readings) > MAX_CONFLICT_READINGS
            else ""
        )
        items.append(
            Item(
                3,
                "conflict",
                f"{c.concept.value.replace('_', ' ')} {c.period_key} is withheld: the tables give "
                f"{len(readings)} different readings ({shown}{more}). Compare them in the source.",
                c.chosen_page,
                _readings(report, c),
            )
        )
    if older:
        items.append(
            Item(
                5,
                "conflict",
                f"{older} figure(s) for earlier years are also withheld because the tables "
                "disagree; "
                "see the full report.",
                None,
            )
        )
    return items


def _flag_text(name: str, explanation: str) -> str:
    """Rule name, then what was found; many explanations already open with the name."""
    return explanation if explanation.startswith(name) else f"{name}: {explanation}"


def _span(pages: list[int]) -> str:
    return f"p.{pages[0]}" if len(pages) == 1 else f"pp.{pages[0]}-{pages[-1]}"


def _related_party(report: AnalysisReport) -> tuple[list[Item], list[str]]:
    """Items and notes from the related-party check: figures the document prints, never a sum."""
    rp = report.related_party
    if rp is None or rp.status == "no_summary" or not rp.pages:
        return [], []
    where = _span(rp.pages)
    items: list[Item] = []
    notes: list[str] = []
    for r in rp.rows:
        amount = f" (amount printed: {indian(r.amount)})" if r.amount is not None else ""
        items.append(
            Item(
                2,
                "related_party",
                f"A related-party transaction is printed at {r.percent}% of revenue from "
                f"operations for {rp.year}{amount}. Read the row and what it is for.",
                r.page,
                (
                    (r.page, r.text),
                    *((m, "the same transaction, other party's side") for m in r.mirror_pages),
                ),
            )
        )
    if rp.status in ("partial", "withheld"):
        pages = sorted({p for p, _ in rp.withheld})
        shown = ", ".join(str(p) for p in pages[:6]) + (" and others" if len(pages) > 6 else "")
        items.append(
            Item(
                4,
                "unchecked",
                f"Related-party summary ({where}): tables on page(s) {shown} could not be read "
                "with certainty (the header does not give one revenue-percentage column per "
                "period, or the percentage is on another basis). Read them by hand.",
                pages[0] if pages else rp.pages[0],
            )
        )
    elif rp.status in ("no_percentage_printed", "no_percentage_table"):
        notes.append(
            f"The related-party summary ({where}) prints amounts only, with no share of revenue."
        )
    elif rp.status == "ok" and not rp.rows:
        notes.append(
            f"Related-party summary ({where}) read: no transaction is printed at or above "
            f"{rp.cutoff_percent}% of revenue from operations for {rp.year}."
        )
    return items, notes


def _with_section(item: Item, sections: list[Section]) -> Item:
    sec = section_of(sections, item.page) if item.page else None
    return replace(item, section=sec.title.title() if sec else "")


def build_brief(
    report: AnalysisReport, entry: ManifestEntry, sections: list[Section] | None = None
) -> Brief:
    facts = {f.key: f for f in report.facts}
    verified = {f.key.value: f for f in report.issue_facts if f.verified}
    issue = [
        (label, verified[key].value, verified[key].pdf_page)
        for key, label in _ISSUE
        if key in verified
    ]
    items: list[Item] = []
    for fl in report.flags:
        page = fl.citations[0].pdf_page if fl.citations else None
        items.append(
            Item(
                _SEVERITY_RANK.get(fl.severity, 3),
                "flag",
                _flag_text(fl.rule_name, fl.explanation),
                page,
                tuple((c.pdf_page, _clip(c.span)) for c in fl.citations),
            )
        )
    hidden = sorted(report.pages_with_hidden_text)
    if hidden:
        shown = ", ".join(str(p) for p in hidden[:8]) + (" and others" if len(hidden) > 8 else "")
        items.append(
            Item(
                0,
                "hidden_text",
                f"Text a reader cannot see on page(s) {shown}; figures cited from them need a "
                "check against the rendered page.",
                hidden[0],
            )
        )
    items += _conflicts(report)
    rp_items, notes = _related_party(report)
    items += rp_items
    unchecked = [a for a in report.rule_audit if a.status == "missing_inputs"]
    if unchecked:
        needed = sorted({m for a in unchecked for m in a.missing})
        names = ", ".join(a.rule_id for a in unchecked)
        what = ", ".join(needed) if needed else "figures not extracted"
        many = f"{len(unchecked)} rules" if len(unchecked) > 1 else "1 rule"
        items.append(
            Item(
                4,
                "unchecked",
                f"{many} could not run because these were not found as stated figures ({what}); "
                f"in a draft they are often printed as [●]. Rules: {names}. Check by hand.",
                None,
            )
        )
    items.sort(key=lambda i: (i.rank, _KIND_ORDER[i.kind], i.page or 0))
    if sections is None:
        sections = [Section(s.title, s.start_page, s.printed_page) for s in report.sections]
    if sections:
        items = [_with_section(i, sections) for i in items]
    s = report.summary
    return Brief(
        issuer=entry.issuer,
        doc_type=entry.doc_type.value,
        platform=entry.platform.value if entry.platform else "platform not recorded",
        filed=entry.filing_date.isoformat() if entry.filing_date else "not recorded",
        url=entry.url,
        issue=issue,
        metrics=_metrics(facts),
        read_first=items,
        rules_checked=(s.rules_decisive, s.rules_applicable),
        numbers_verified=(s.values_verified, s.values_total),
        notes=tuple(notes),
    )


def _crore(rupees: Decimal) -> str:
    return indian(rupees / CRORE)


def brief_text(b: Brief) -> str:
    """The brief as plain text for a terminal."""
    lines = [f"{b.issuer} ({b.doc_type}, {b.platform}, filed {b.filed})", ""]
    if b.issue:
        lines.append(
            "Issue (₹ crore): "
            + "; ".join(f"{label} {_crore(v)} (p.{p})" for label, v, p in b.issue)
        )
    for m in b.metrics:
        cells = "  ".join(f"{fy} {_crore(v)} (p.{p})" for fy, v, p in m.cells)
        growth = f"  [{m.growth_pct:+}% on the year before]" if m.growth_pct is not None else ""
        lines.append(f"{m.label} (₹ crore): {cells}{growth}")
    lines += ["", "Read first:" if b.read_first else "Nothing flagged or withheld."]
    for i, item in enumerate(b.read_first, 1):
        where = f" -> p.{item.page}" if item.page else ""
        where += f" ({item.section})" if item.section else ""
        lines.append(f"  {i}. [{item.kind}] {item.text}{where}")
        lines += [f"       p.{p}: {t}" for p, t in item.evidence]
    d, a = b.rules_checked
    v, t = b.numbers_verified
    lines += ["", *b.notes] if b.notes else []
    lines += [
        "",
        f"{d} of {a} applicable rules could be evaluated; {v} of {t} extracted numbers were found "
        "again on their cited page.",
        DISCLAIMER,
    ]
    return "\n".join(lines)


def _link(url: str, page: int | None) -> str:
    if page is None:
        return ""
    return f' <a href="{escape(url, quote=True)}#page={page}">open p.{page}</a>'


_STYLE = (
    ":root{--bg:#fff;--fg:#1c1c1e;--mute:#5b5b66;--line:#d9d9e0;--card:#f6f6f9;--hi:#b3261e;--med:#a15c00}"
    "@media (prefers-color-scheme:dark){:root{--bg:#16161a;--fg:#ececf1;--mute:#a0a0ad;"
    "--line:#33333c;"
    "--card:#1f1f25;--hi:#ff8a80;--med:#ffb74d}}"
    "body{margin:0 auto;max-width:48rem;padding:1rem 16px 2rem;background:var(--bg);"
    "color:var(--fg);"
    "font:16px/1.5 system-ui,sans-serif}h1{font-size:1.4rem;margin:.2rem 0}"
    "h2{font-size:1.05rem;margin:1.4rem 0 .4rem;border-bottom:1px solid var(--line)}"
    ".meta,.note{color:var(--mute);font-size:.9rem}table{border-collapse:collapse;width:100%;font-size:.95rem}"
    "th,td{padding:.25rem .5rem;border-bottom:1px solid var(--line);text-align:left}"
    "td.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}"
    "ul.ev{font-size:.85rem;color:var(--mute);padding-left:1rem}ul.ev code{word-break:break-word}"
    "ol{padding-left:1.2rem}li{margin:.4rem 0}.tag{font-size:.75rem;border:1px solid currentColor;"
    "border-radius:4px;padding:0 .3rem;margin-right:.3rem;color:var(--med)}"
    ".tag.flag,.tag.hidden_text,.tag.related_party{color:var(--hi)}.banner{background:var(--card);"
    "border-left:4px solid "
    "var(--med);padding:.5rem .8rem;margin:.8rem 0}.table-wrap{overflow-x:auto}"
)


def _section_html(item: Item) -> str:
    return f" <span class=note>({escape(item.section)})</span>" if item.section else ""


def _evidence_html(url: str, item: Item) -> str:
    if not item.evidence:
        return ""
    rows = "".join(f"<li><code>{escape(t)}</code>{_link(url, p)}</li>" for p, t in item.evidence)
    return f"<ul class=ev>{rows}</ul>"


def brief_html(b: Brief) -> str:
    issue = (
        "<table><tbody>"
        + "".join(
            f"<tr><th>{escape(label)}</th><td class=num>{_crore(v)}{_link(b.url, p)}</td></tr>"
            for label, v, p in b.issue
        )
        + "</tbody></table>"
        if b.issue
        else "<p class=note>No issue size is stated in a form that could be read (placeholders "
        "such as [●] are not read as figures).</p>"
    )
    rows = []
    for m in b.metrics:
        cells = "".join(
            f"<td class=num>{escape(fy)}: {_crore(v)}{_link(b.url, p)}</td>" for fy, v, p in m.cells
        )
        growth = (
            f"<td class=num>{m.growth_pct:+}%</td>" if m.growth_pct is not None else "<td></td>"
        )
        rows.append(f"<tr><th>{escape(m.label)}</th>{cells}{growth}</tr>")
    metrics = (
        "<div class=table-wrap><table><tbody>" + "".join(rows) + "</tbody></table></div>"
        if rows
        else "<p class=note>No annual figures could be extracted with enough confidence.</p>"
    )
    todo = (
        "<ol>"
        + "".join(
            f"<li><span class='tag {escape(i.kind)}'>{escape(i.kind.replace('_', ' '))}</span>"
            f"{escape(i.text)}{_link(b.url, i.page)}{_section_html(i)}"
            f"{_evidence_html(b.url, i)}</li>"
            for i in b.read_first
        )
        + "</ol>"
        if b.read_first
        else "<p>Nothing flagged and nothing withheld. That is <strong>not</strong> a clean bill of"
        " "
        "health: only the rules below could be evaluated.</p>"
    )
    d, a = b.rules_checked
    v, t = b.numbers_verified
    notes = "".join(f"<p class=note>{escape(n)}</p>" for n in b.notes)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(b.issuer)}: brief</title><style>{_STYLE}</style></head><body>
<h1>{escape(b.issuer)}</h1>
<p class=meta>{escape(b.doc_type)} · {escape(b.platform)} · filed {escape(b.filed)} ·
<a href="{escape(b.url, quote=True)}">source</a></p>
<div class=banner><strong>{escape(DISCLAIMER)}</strong></div>
<h2>Read first</h2>{todo}
<h2>The issue (₹ crore)</h2>{issue}
<h2>Financials (₹ crore)</h2>{metrics}
<p class=note>Growth is the newest year over the one before, shown only when both are positive.</p>
<h2>How far to trust this</h2>
<p>{d} of {a} applicable rules could be evaluated. {v} of {t} extracted numbers were found again on
their cited page. A figure the document's tables disagreed on is listed above, not shown.</p>
{notes}
</body></html>
"""


def triage_html(rows: list[tuple[str, Brief]], reports: dict[str, str] | None = None) -> str:
    """The home page: one row per filing, most to read first.

    `rows` is (brief link, brief); `reports` maps a brief link to its full-report link, where one
    has been written.
    """
    reports = reports or {}

    def sort_key(row: tuple[str, Brief]) -> tuple[int, int, str]:
        b = row[1]
        top = min((i.rank for i in b.read_first), default=9)
        return (top, -len(b.read_first), b.issuer.lower())

    body = []
    for target, b in sorted(rows, key=sort_key):
        kinds = {
            k: sum(i.kind == k for i in b.read_first)
            for k in ("flag", "related_party", "conflict", "unchecked")
        }
        hidden = "yes" if any(i.kind == "hidden_text" for i in b.read_first) else ""
        full = (
            f'<a href="{escape(reports[target], quote=True)}">full report</a>'
            if target in reports
            else ""
        )
        body.append(
            f'<tr><td><a href="{escape(target, quote=True)}">{escape(b.issuer)}</a></td>'
            f"<td>{escape(b.doc_type)}</td><td>{escape(b.filed)}</td>"
            f"<td>{len(b.read_first)}</td><td>{kinds['flag']}</td>"
            f"<td>{kinds['related_party']}</td>"
            f"<td>{kinds['conflict']}</td><td>{kinds['unchecked']}</td><td>{hidden}</td>"
            f"<td>{b.rules_checked[0]} of {b.rules_checked[1]}</td><td>{full}</td></tr>"
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>IPO Engine: filings</title><style>{_STYLE}body{{max-width:76rem}}
td:not(:first-child){{white-space:nowrap}}</style></head><body>
<h1>Filings: what to open first</h1>
<div class=banner><strong>{escape(DISCLAIMER)}</strong></div>
<p class=note>Ordered by the most serious item to read. Open a filing's brief first; the full
report lists every figure. A filing with nothing to read is not cleared: see "rules checked".</p>
<div class=table-wrap><table><thead><tr><th>Issuer (brief)</th><th>Document</th><th>Filed</th>
<th>To read</th><th>Flags</th><th>Related party</th><th>Withheld</th><th>Unchecked</th>
<th>Hidden text</th><th>Rules checked</th><th></th></tr></thead>
<tbody>{"".join(body)}</tbody></table></div></body></html>
"""
