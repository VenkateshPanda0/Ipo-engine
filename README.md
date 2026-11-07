# RedHerring: IPO due diligence for Indian offer documents

One project that reads a filed DRHP/RHP, checks it, and (next) helps prepare one. Every number
carries the PDF page it came from, nothing is shown that was not re-read from its page, and it
runs offline with no language model.

> Not investment or legal advice. The software prepares and checks; it never certifies or files.
> The lead manager (a SEBI-registered merchant banker) certifies due diligence and files.

## The product, in three parts

| Part | What it is | Where it lives | State |
|---|---|---|---|
| **Reader** (the core) | parse, extract, verify, cross-check, 12 red-flag rules, briefs, version diff, benchmark | `redherring/` | working: 521/525 labelled fields correct, 0 wrong |
| **Screening and review app** | ICDR eligibility rules, review queue, audit trail, sign-off, web UI, OCR | `backend/`, `frontend/` (the earlier engine) | working, being folded into the core, see below |
| **Preparer** (issuer side) | input templates, eligibility arithmetic, draft consistency check, DRHP skeleton, filing checklist | planned | not started |

Start with `redherring/README.md` (results, quick start) and `redherring/docs/plan.md` (phases).
The earlier engine's own README is kept at `docs/LEGACY_ENGINE.md`.

## How the parts become one

The earlier engine and the reader were built separately and share no code. The merge keeps the
reader's verified-data core (every item sourced and re-checked) and moves the engine's strengths
onto it, one at a time, each with a test and no loss of accuracy:

| From the earlier engine | Becomes | Step |
|---|---|---|
| 19 versioned eligibility rules (ICDR Reg 5, 6, 14, 16, SCRR, advisory) | rules in the reader's TOML rule engine, each with clause and date | M1 |
| Review queue, audit trail, reviewer sign-off | a local review layer over withheld and flagged items | M2 |
| OCR for scanned pages | the reader's scanned-filing path (plan 2.4) | M3 |
| Web UI and case workflow | one front end over the core (plan 4.2) | M4 |

Until M4 both stay runnable. Nothing is deleted before its replacement passes the gates, and
history is never rewritten. Decision record: `redherring/docs/decisions.md` (D-050).
