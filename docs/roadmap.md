# Roadmap and TODO

The one place to see what is done and what to do next. Phases, gates and owner needs are in
`plan.md`; the numbers behind each state are in `status.md`; the reasons are in `decisions.md`.
Updated 2026-11-18.

## Done

| Area | What exists |
|---|---|
| Foundation | Fetcher with integrity checks (`ingest`), page-tagged parser with tables, units and headers, CLI, CI, decision log |
| Extraction | Statement lines, issue facts, objects of the issue, period parsing, sector detection; offline, no language model (D-042) |
| Verification | Citation re-read, footing, cross-table consensus, column trust |
| Benchmark | `ipo eval`: 647 labelled fields, 38 filings, 521/525 correct, 0 wrong, 4 withheld; held-out sets 8 and 12 never used for a fix |
| Section map | `segment.py`, 29 of 29 labelled start pages correct |
| Rules | 12 TOML red-flag rules (nine regulatory with clause and date, three heuristic) |
| Text check 1 | Related-party transactions (`checks/related_party.py`): rows at or above 5% of revenue, with page and text; 0 wrong, 0 silent misses on three label sets |
| Outputs | One-page brief, triage home page, full report, version diff on figures; `ipo run FILE.pdf` does it all |
| Screening app | FastAPI and Next.js: 19 versioned eligibility rules, review queue, audit trail, signed reports |
| The two meet | The reader runs inside the web app ("Reader brief" tab) |
| Demo | Static site on GitHub Pages from `site/briefs.json` |
| Hardening | Hostile-PDF tests, hidden-text removal, dependency audits in CI |

## Next, in order

Pick the first unchecked item. Each ships only when its gate (in `plan.md`) is met.

- [ ] **1. Related-party gaps.** Two summary pages are still withheld (Moneyview p.100, SFC p.115).
  Looked at 2026-11-20: SFC p.115 is a guarantee table with no percentage column; it is withheld by
  the page-coverage guard (figures on the page that the table reader did not capture), which cannot
  tell it from the continuation page of a plain-number table (Nityas p.115, whose header is on the
  page before). Exempting it would risk a silent miss, so it stays withheld until labels on more
  continuation pages exist to separate the two. Moneyview p.100 looked at 2026-11-21: its percentages are against employee benefits expense, not revenue (blind label `other_basis`), so the check correctly lists nothing from it; the page is not a gap in coverage. Labels first, then
  code, scored with `tools/rp_score.py` (wrong rows and silent misses must be 0).
- [ ] **2. Outstanding litigation check.** Counts and amounts by type, from the section map. Labels
  first (`labels/litigation/`), then code. Evidence and quotes, never a verdict.
- [ ] **3. Phase 5 M1.** Move one figure family of the screening app onto the reader's verified core,
  scored on the screening benchmark (`tools/screening/benchmark_extraction.py`). It changes
  outcomes, so one family at a time.
- [ ] **4. New held-out set** for the core extractor (needs new public filings; SEBI's list loads
  dynamically, so they are added to `data/sources.toml` by hand).
- [ ] **5. Remaining text checks**, same method as 1 and 2: promoter pledges, customer and supplier
  concentration, contingent liabilities, tax liabilities, auditor remarks.
- [ ] **6. Text diff, DRHP to RHP:** issue wording, objects, risk factors, litigation.
- [ ] **7. Install in one command** (`pip install` or a single binary) and a short analyst guide.

## Needs a person (cannot be built here)

- [ ] An independent reader checks about 100 labels (no label has had a second reader).
- [ ] A lawyer reviews the regulation rules (SCRR and exchange rules are marked unverified).
- [ ] Two or three analysts try the reader on real filings; re-rank the brief from what they used.
- [ ] Decision on licence and commercial model before selling (MIT today).
- [ ] Review of the data sources' terms of use (D-010).

## Not started

| Item | Note |
|---|---|
| Issuer-side preparer (`plan.md` Phase 3) | Input templates, eligibility arithmetic, draft consistency checker, DRHP skeleton, filing checklist. Prepares and checks; never certifies or files |
| Scanned filings | OCR exists in the screening app only; the reader reports scanned pages as unreadable. Needs labelled scanned pages first |
| Review layer on the reader's items (M2) | Confirm, correct or reject a withheld item, with audit trail |
| One front end over one core (M4) | Eligibility figures in the web app still come from the screening app's own extraction |
| Outcome backtest | Only with written hypotheses and a price source whose terms allow it |

## Known loose ends

- The Docker image builds from the Dockerfile but has not been run (no daemon in the build
  environment).
- Six advisories remain in test tooling only (vitest, vite, esbuild); production dependencies audit
  clean (D-063).
- `docs/screening/` holds the earlier engine's own docs; where they disagree with `ARCHITECTURE.md`
  or `status.md`, the latter win.
