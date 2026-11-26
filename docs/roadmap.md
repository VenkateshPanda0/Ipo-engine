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
- [ ] **2. Outstanding litigation check.** Slice 1 done 2026-11-23 (D-065): the two printed thresholds,
  `tools/lit_score.py` 20/20. Wired into `ipo analyze` (version 31) and the brief the same day. Slice 2 2026-11-24 (D-066): more wordings, ranking, second label set, 20/20 on both. Slice 3 2026-11-25 (D-067): six more wordings, third label set, 12/12; shown thresholds 26 to 31 of 40. Next:
  all three label sets are development data, so the real measure of generalisation is a genuinely unseen set
  (new filings, labelled before any pattern is touched), then counts and amounts of matters by type. Labels
  first, evidence and quotes, never a verdict.
- [ ] **2b. Accessibility, next slice.** Slice 1 done 2026-11-26: axe-core audit in CI, 0 violations on all pages in
  both themes (before: 6 and 9 pages failing on contrast). Next: a person reviews the main flows (create a case,
  upload, review items, sign-off, team and tokens) with only the keyboard and with a screen reader, and anything
  found becomes a test (focus order, live regions for save and error messages). Slice 2 done 2026-11-26: dialog
  focus (trap, no focus theft while typing, return to opener), 7 unit tests, 3 failing before.
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

- Resolved 2026-11-24: the container images were first written without a container engine; the `docker`
  workflow now builds both on every push, starts each and answers its health check, and scans it with
  Trivy (its first run found 10 HIGH findings in the Node base image's own npm, fixed by removing npm
  from the runtime image). `docker compose up` itself has not been run end to end by a person.
- Resolved 2026-11-25: the six advisories in test tooling (vitest, vite, esbuild, tinypool) are gone
  (vitest 5, vite 8); the full `npm audit` reports 0 and CI gates on it (D-063's open item).
- `docs/screening/` holds the earlier engine's own docs; where they disagree with `ARCHITECTURE.md`
  or `status.md`, the latter win.
