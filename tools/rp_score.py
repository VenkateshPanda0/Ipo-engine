"""Score the related-party check against labels/related_party/pilot.json.

    uv run python tools/rp_score.py [labels/related_party/pilot.json | blind1.json]

For each labelled filing: rows shown that are not in the label are WRONG (must be 0); labelled rows
missing from a result that claims to be complete are SILENT MISSES (must be 0); labelled rows
missing from a partial or withheld result are WITHHELD (reported, acceptable).
Needs data/parsed/ (`ipo parse`).
"""

import json
import sys
from decimal import Decimal
from pathlib import Path

from ipo_engine.checks.related_party import check
from ipo_engine.parse.models import ParsedDocument
from ipo_engine.segment import build_section_map

ROOT = Path(__file__).resolve().parent.parent
label_file = sys.argv[1] if len(sys.argv) > 1 else "labels/related_party/pilot.json"
labels = json.loads((ROOT / label_file).read_text())["filings"]
wrong = silent = withheld = right = 0
for doc_id, lab in labels.items():
    if lab["status"] not in ("complete", "no_percentage_printed", "no_percentage_column"):
        continue
    path = ROOT / "data/parsed" / f"{doc_id}.json"
    if not path.exists():
        print(f"SKIP {doc_id}: not parsed")
        continue
    doc = ParsedDocument.model_validate_json(path.read_text())
    res = check(doc, build_section_map(doc))
    want = {(r["page"], Decimal(r["percent"])) for r in lab["rows"]}
    mirrors = {(m, Decimal(r["percent"])) for r in lab["rows"] for m in r.get("mirror_pages", [])}
    got = {(r.page, r.percent) for r in res.rows}
    got_all = got | {(m, r.percent) for r in res.rows for m in r.mirror_pages}
    bad = got_all - want - mirrors
    miss = want - got_all
    complete = res.status in ("ok", "no_percentage_printed", "no_percentage_table")
    expect_status = lab["status"]
    status_bad = (
        expect_status == "no_percentage_printed" and res.status != "no_percentage_printed"
    ) or (  # claiming a readable percentage table where the pages have none is a false claim
        expect_status == "no_percentage_column" and (res.status in ("ok", "partial") or res.rows)
    )
    wrong += len(bad) + (1 if status_bad else 0)
    right += len(want & got_all)
    if complete:
        silent += len(miss)
    else:
        withheld += len(miss)
    print(
        f"{doc_id:34} status={res.status:22} year={res.year} rows={sorted(got)} "
        f"want={sorted(want)} withheld={[w[0] for w in res.withheld]}"
        + (f"  WRONG={sorted(bad)}" if bad else "")
        + (f"  SILENT_MISS={sorted(miss)}" if complete and miss else "")
    )
print(f"\nright={right} wrong={wrong} silent_misses={silent} withheld_rows={withheld}")
sys.exit(1 if wrong or silent else 0)
