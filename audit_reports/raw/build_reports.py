"""Build 11_AUDIT_CHECKLIST.csv and 02/03/04 markdown from checklist_data.py.

python audit_reports/raw/build_reports.py
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE.parent
sys.path.insert(0, str(HERE))
import checklist_data as d  # noqa: E402

STATUS = {
    "FV": "Fixed — Verified",
    "NF": "Tested — Not Found",
    "NA": "Not Applicable",
    "IN": "Inconclusive",
    "CF": "Confirmed",
    "FP": "Fixed — Verification Pending",
    "BL": "Blocked",
}
PREFIX = {"SEC": d.SEC, "BUG": d.BUG, "GLT": d.GLT}
TITLE = {
    "SEC": ("02_SECURITY_AUDIT.md", "Security audit (SEC-001 to SEC-100)"),
    "BUG": ("03_BUG_AUDIT.md", "Software error audit (BUG-001 to BUG-100)"),
    "GLT": (
        "04_GLITCH_AND_RELIABILITY_AUDIT.md",
        "Glitch and reliability audit (GLT-001 to GLT-100)",
    ),
}
COMMIT_URL = "commit "


def methodology(tag: str, status: str) -> str:
    parts = []
    for t in tag.split(";"):
        t = t.strip()
        if t.startswith("agent:"):
            name = t[6:].split(" ")[0]
            parts.append(f"independent subagent probes ({name}); see 05_AGENT_REPORTS")
        elif t.startswith("own:"):
            parts.append("run by the lead auditor: " + t[4:])
        elif t.startswith("exist:"):
            parts.append("existing repository test: " + t[6:])
        elif t.startswith("sast"):
            parts.append("static analysis / dependency scan")
        elif t.startswith("na"):
            parts.append("component absent")
        elif t.startswith("nt"):
            parts.append("not exercised in this audit")
        else:
            parts.append(t)
    return "; ".join(parts)


def execution(status: str, tag: str) -> str:
    if status == "NA":
        return "Not run (component absent)"
    if status == "BL":
        return "Blocked by the environment"
    if tag.startswith("nt") or (status == "IN" and "nt" in tag.split(";")[0][:3]):
        return "Not executed"
    return "Executed"


def relevance(status: str) -> str:
    return "Not applicable to this project" if status == "NA" else "Relevant to this project"


def solution(status: str, issue: str) -> str:
    if not issue:
        return ""
    return d.ISSUES[issue][1] and (
        "Fixed in the audit branch; see the ledger"
        if status in ("FV", "FP")
        else "See 09_UNRESOLVED_ISSUES.md"
    )


rows = []
for cat, items in PREFIX.items():
    for i, (name, st, tag, comp, sev, ref) in enumerate(items, 1):
        eid = f"{cat}-{i:03d}"
        issue = d.ISSUES.get(ref) if ref else None
        sev_out = sev or ("P4" if st == "IN" else "")
        rows.append(
            {
                "id": eid,
                "category": cat,
                "issue_name": name,
                "technical_description": issue[1] if issue else name,
                "relevance": relevance(st),
                "affected_components": comp,
                "testing_methodology": methodology(tag, st),
                "test_execution_status": execution(st, tag),
                "evidence": tag,
                "severity": sev if st in ("FV", "CF", "FP") else "",
                "root_cause": d.NOTES[ref][0] if ref and ref in d.NOTES else "",
                "proposed_solution": d.NOTES[ref][1] if ref and ref in d.NOTES else "",
                "fix_implementation_status": (
                    "Implemented"
                    if st in ("FV",)
                    else "Implemented, not run"
                    if st == "FP"
                    else "Not implemented"
                    if st == "CF"
                    else ""
                ),
                "verification_results": (
                    "Regression test red before, green after; full gate passes"
                    if st == "FV"
                    else "Edited; the deployment was not run (no Docker)"
                    if st == "FP"
                    else ""
                ),
                "remaining_limitations": (
                    "Not exercised: needs a person, a service or a tool that was not available"
                    if st == "IN"
                    else "Not run: no suitable environment"
                    if st == "BL"
                    else ""
                ),
                "status": STATUS[st],
                "issue_id": ref,
                "fix_commit": d.ISSUES[ref][3] if ref and st in ("FV", "FP") else "",
            }
        )

with open(OUT / "11_AUDIT_CHECKLIST.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)

counts = Counter((r["category"], r["status"]) for r in rows)


def md(cat: str) -> None:
    fname, title = TITLE[cat]
    mine = [r for r in rows if r["category"] == cat]
    c = Counter(r["status"] for r in mine)
    lines = [f"# {title}", ""]
    lines += [
        "Every entry below was assessed one of these ways, and the CSV (`11_AUDIT_CHECKLIST.csv`) holds all 13 "
        "requested fields per entry. A **Tested — Not Found** means a named test, probe or review looked for the "
        "problem and did not find it; it does not mean the problem cannot exist. **Inconclusive** means it was not "
        "exercised here, and says so. The 100 entries are the issue types judged relevant to this project; they were "
        "chosen from the codebase's own surface (see `12_RESEARCH_SOURCES.md`), not generated to a quota.",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for k in STATUS.values():
        if c.get(k):
            lines.append(f"| {k} | {c[k]} |")
    lines += ["", "## Confirmed and fixed or open", ""]
    lines += ["| ID | Issue | Severity | Status | Ledger | Fix |", "|---|---|---|---|---|---|"]
    for r in mine:
        if r["status"] in ("Fixed — Verified", "Confirmed", "Fixed — Verification Pending"):
            lines.append(
                f"| {r['id']} | {r['issue_name']} | {r['severity']} | {r['status']} | {r['issue_id']} | {r['fix_commit'] or '—'} |"
            )
    lines += ["", "## Full checklist", ""]
    lines += ["| ID | Issue type | Status | Evidence |", "|---|---|---|---|"]
    for r in mine:
        ev = r["evidence"].replace("|", "/")
        lines.append(f"| {r['id']} | {r['issue_name']} | {r['status']} | {ev} |")
    (OUT / fname).write_text("\n".join(lines) + "\n", encoding="utf-8")


for cat in PREFIX:
    md(cat)

tot = Counter(r["status"] for r in rows)
print({k: tot.get(k, 0) for k in STATUS.values()})
for cat in PREFIX:
    print(cat, {k: counts.get((cat, k), 0) for k in STATUS.values() if counts.get((cat, k))})
