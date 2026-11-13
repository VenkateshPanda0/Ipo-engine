"""The public demo site: its data is well-formed and its script cannot inject markup."""

import json
import re
from pathlib import Path
from typing import Any

SITE = Path(__file__).resolve().parent.parent / "site"
# Issuers that are the subject of a regulator's order, and test probes: never shown in the demo.
EXCLUDED = {"sebi_draft_2010_probe", "varyaa_prospectus_2024", "synoptics_dp_2023"}


def _data() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((SITE / "briefs.json").read_text(encoding="utf-8"))
    return data


def test_every_filing_has_the_fields_the_page_reads() -> None:
    d = _data()
    assert d["meta"]["count"] == len(d["filings"]) > 5
    for f in d["filings"]:
        assert {"id", "issuer", "doc_type", "filed", "source", "issue", "years", "metrics"} <= set(
            f
        )
        assert {"read_first", "notes", "rules_checked", "numbers_verified", "sections"} <= set(f)
        assert f["id"] not in EXCLUDED
        assert f["source"].startswith("https://"), f[
            "id"
        ]  # every page link goes to a public source
        for item in f["read_first"]:
            assert item["kind"] in {"flag", "hidden_text", "related_party", "conflict", "unchecked"}
            for e in item["evidence"]:
                assert isinstance(e["page"], int) and e["text"]
        for m in f["metrics"]:
            assert len(m["cells"]) == len(f["years"])


def test_numbers_are_formatted_by_the_python_side_and_losses_are_marked() -> None:
    money = re.compile(r"^−?\d{1,3}(,\d{2})*(,\d{3})?\.\d{2}$")
    seen_negative = False
    for f in _data()["filings"]:
        for m in f["metrics"]:
            for c in filter(None, m["cells"]):
                assert money.match(c["text"]), (f["id"], c["text"])
                assert c["neg"] == c["text"].startswith("−")
                seen_negative |= c["neg"]
    assert (
        seen_negative
    )  # at least one loss-making figure in the sample, so the marking is exercised


def test_the_benchmark_shown_is_the_measured_one() -> None:
    b = _data()["meta"]["benchmark"]
    assert b["wrong"] == b["present"] - b["correct"] - b["withheld"] == 0


def test_the_script_never_writes_markup_from_data() -> None:
    js = (SITE / "app.js").read_text(encoding="utf-8")
    for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert banned not in js, banned
    assert "noopener" in js  # external links do not get window.opener


def test_the_page_makes_no_external_requests() -> None:
    html = (SITE / "index.html").read_text(encoding="utf-8")
    refs = re.findall(r'(?:src|href)="(https?://[^"]+)"', html)
    allowed = ("https://github.com/VenkateshPanda0/Ipo-engine", "https://docs.astral.sh/uv/")
    assert all(r.startswith(allowed) for r in refs), refs  # links only; no script, font or image
    assert '<script src="http' not in html and "@import" not in (SITE / "style.css").read_text()
