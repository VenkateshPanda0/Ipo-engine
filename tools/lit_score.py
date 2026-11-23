"""Score the litigation-threshold check against labels/litigation/thresholds.json.

    uv run python tools/lit_score.py

For each labelled filing and threshold: a figure shown that differs from the label (in rupees) or
sits on another page is WRONG (must be 0); a labelled figure the check did not show is MISSED
(reported; it was stated as not found or withheld, never wrong). Needs data/parsed/ (`ipo parse`).
"""

import json
from decimal import Decimal
from pathlib import Path

from ipo_engine.checks.litigation import check
from ipo_engine.parse.models import ParsedDocument
from ipo_engine.segment import build_section_map

ROOT = Path(__file__).resolve().parent.parent
UNIT = {"million": Decimal(10) ** 6, "crore": Decimal(10) ** 7}
labels = json.loads((ROOT / "labels/litigation/thresholds.json").read_text())["filings"]
right = wrong = missed = 0
for doc_id, lab in labels.items():
    path = ROOT / "data/parsed" / f"{doc_id}.json"
    if not path.exists():
        print(f"SKIP {doc_id}: not parsed")
        continue
    doc = ParsedDocument.model_validate_json(path.read_text())
    res = check(doc, build_section_map(doc))
    for name in ("litigation", "creditor"):
        want = lab[name]
        want_rupees = Decimal(want["amount"].replace(",", "")) * UNIT[want["unit"]]
        got = getattr(res, name)
        if got is None:
            missed += 1
            print(f"MISSED {doc_id} {name}: want {want['amount']} {want['unit']}  [{res.status}]")
        elif got.rupees == want_rupees and got.page == want["page"]:
            right += 1
        else:
            wrong += 1
            print(f"WRONG  {doc_id} {name}: got {got.printed} p{got.page}, want {want['amount']}")
print(f"\nright={right} wrong={wrong} missed={missed}")
