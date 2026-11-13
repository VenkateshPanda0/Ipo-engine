"""Build the data file for the public demo site (site/briefs.json) from analysed filings.

    uv run python tools/build_demo.py            # all filings that have been analysed
    uv run python tools/build_demo.py DOC_ID ... # only these

The site is static and offline-capable: it shows the briefs this tool exports, for public filings
only, with every page reference linking to the filing's public source. Numbers are formatted here,
by the same module the briefs use, so the page never formats money itself. The exported file is
committed; the GitHub Actions workflow only checks it and publishes `site/`.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from ipo_engine.analyze import ANALYSIS_VERSION, AnalysisReport
from ipo_engine.brief import Brief, build_brief
from ipo_engine.ingest.manifest import Manifest
from ipo_engine.numfmt import crore, pct

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "site" / "briefs.json"
SKIP_TYPES = {"enforcement_order", "regulation", "other"}
# Filings that are test probes, or whose issuer is the subject of a regulator's order (the demo
# must not suggest anything about them): left out.
SKIP_IDS = {"sebi_draft_2010_probe", "varyaa_prospectus_2024", "synoptics_dp_2023"}


def _money(rupees: Decimal) -> dict[str, object]:
    text = crore(rupees)
    return {"text": text.replace("-", "−"), "neg": text.startswith("-")}


def export_brief(b: Brief, report: AnalysisReport) -> dict[str, object]:
    years = sorted({fy for m in b.metrics for fy, _, _ in m.cells}, reverse=True)
    metrics = []
    for m in b.metrics:
        by = {fy: (v, p) for fy, v, p in m.cells}
        metrics.append(
            {
                "label": m.label,
                "cells": [
                    {**_money(by[y][0]), "page": by[y][1]} if y in by else None for y in years
                ],
                "change": pct(m.growth_pct, signed=True) if m.growth_pct is not None else None,
            }
        )
    return {
        "issue": [{"label": label, **_money(v), "page": p} for label, v, p in b.issue],
        "years": years,
        "metrics": metrics,
        "read_first": [
            {
                "kind": i.kind,
                "text": i.text,
                "page": i.page,
                "section": i.section,
                "evidence": [{"page": p, "text": t} for p, t in i.evidence],
            }
            for i in b.read_first
        ],
        "notes": list(b.notes),
        "rules_checked": list(b.rules_checked),
        "numbers_verified": list(b.numbers_verified),
        "sections": len(report.sections),
    }


def benchmark() -> dict[str, int] | None:
    """The reader's measured accuracy, taken from `ipo eval` output (nothing typed by hand)."""
    from ipo_engine.cli import main as cli_main

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli_main(["--data-dir", str(DATA), "eval", "--labels-dir", str(ROOT / "labels")])
    text = buf.getvalue()
    m = re.search(r"Labelled fields: (\d+) \((\d+) present, (\d+) absent\)", text)
    c = re.search(r"value accuracy: (\d+)/(\d+)", text)
    a = re.search(r"abstention rate: (\d+)/", text)
    if rc or not (m and c and a):
        return None
    correct, present, withheld = int(c[1]), int(c[2]), int(a[1])
    return {
        "labelled": int(m[1]),
        "present": present,
        "correct": correct,
        "withheld": withheld,
        "wrong": present - correct - withheld,
    }


def main(argv: list[str]) -> int:
    manifest = Manifest(DATA / "manifest.jsonl")
    wanted = set(argv)
    filings = []
    for e in manifest.entries():
        if (
            e.doc_type.value in SKIP_TYPES
            or e.doc_id in SKIP_IDS
            or (wanted and e.doc_id not in wanted)
        ):
            continue
        path = DATA / "extracted" / f"{e.doc_id}.financials.json"
        if not path.exists():
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("analysis_version") != ANALYSIS_VERSION:
            print(f"skip {e.doc_id}: analysed by an older version; run `ipo analyze`")
            continue
        report = AnalysisReport.model_validate(raw)
        brief = build_brief(report, e)
        filings.append(
            {
                "id": e.doc_id,
                "issuer": e.issuer,
                "doc_type": e.doc_type.value,
                "platform": e.platform.value if e.platform else None,
                "filed": e.filing_date.isoformat() if e.filing_date else None,
                "source": e.url,
                **export_brief(brief, report),
            }
        )
    filings.sort(
        key=lambda f: (
            min((i["kind"] != "x" for i in f["read_first"]), default=True),
            f["issuer"].lower(),
        )
    )
    meta = {
        "generated": datetime.now(UTC).date().isoformat(),
        "analysis_version": ANALYSIS_VERSION,
        "count": len(filings),
        "benchmark": benchmark(),
        "labelled_filings": len(list((ROOT / "labels").glob("*.json"))),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"meta": meta, "filings": filings}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"wrote {OUT} ({len(filings)} filings, {OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
