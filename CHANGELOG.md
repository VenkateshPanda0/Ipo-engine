# Changelog

Notable changes to IPO Engine. The reasoning behind each is in `docs/decisions.md`; the screening
app's earlier history (to 2.0.1) is in `docs/screening/CHANGELOG.md`.

## Unreleased

- Litigation thresholds (D-066): reads more wordings (lakhs; "exceeds ₹N, being 5% of"; "which amounts to"; "is the materiality threshold"; the policy's claim-amount test), and a concluding statement now outranks a defined term on another test: Laxmi India Finance showed ₹49.14 million (turnover test) where the filing concludes ₹12.41 million, now fixed; party-specific thresholds (Bajaj Housing) are reported as several, none shown. Second label set (`labels/litigation/thresholds2.json`). `tools/lit_score.py`: first set 20/20, second set 20/20 (baseline of the earlier code on the second set: 8 right, 9 missed), 0 wrong. 914 tests collected (903 at the start of the week). `ANALYSIS_VERSION` 32; demo data rebuilt.
- Litigation check, first slice (`checks/litigation.py`, D-065): reads the materiality-policy threshold and the material-creditor threshold from the first pages of the outstanding-litigation section, each with page and sentence; none or conflicting figures are reported, not guessed. Labels for ten filings (`labels/litigation/`), scorer `tools/lit_score.py`: 20 of 20 right, 0 wrong. Run over 28 other filings, 22 figures shown, all matching their pages after a fix for two wrong ones (a creditor figure read as the litigation threshold). 6 new tests. Now part of `ipo analyze` (`ANALYSIS_VERSION` 31, field `litigation`) and shown in the brief as a note ("a civil matter is disclosed above ₹ X crore (p.N); dues to a creditor are material above ₹ Y crore"); the demo site data was rebuilt. Benchmark unchanged (449/521 citations, 521/525 values); related-party plain-number set still 7 of 7.
- `ipo ingest` no longer appends a duplicate manifest row when it re-downloads a PDF whose bytes match the recorded hash (a fresh checkout used to show a diff in `data/manifest.jsonl`: +2 rows on one run, +39 on another; now 0 on a re-download of Varyaa). Changed bytes are still recorded. Test added; 904 tests collected before this one.
- Docs: roadmap rewritten as the ordered TODO (done, next, needs a person, not started); docs index added (`docs/README.md`); plan, README, CONTRIBUTING, labels and tools READMEs brought in line with the code.
- Related-party check recovers rows the table reader left as plain text (Nityas Gems now reads all 3
  labelled rows) and requires every plain-number row to tie to its amount over verified revenue.

- Demo site: a filing's address is now `#filing-<name>` (letters, digits and hyphens), so a brief can be
  linked and also opens inside hosts that pass only a plain `#name`. Also published as a live page.

- Security: Next.js 15.5.27 to 15.5.29 (critical advisory), `source-map-js` fixed, zod 3 to 4 (high
  advisory); `npm audit --omit=dev` reports 0 vulnerabilities. CI now audits both Python and shipped
  frontend dependencies.

- Related-party check: a summary page that prints clearly more figures than the table reader captured
  is withheld instead of reported as having no large row; plain-number tables take the column order
  from the filing's other tables when each shown row ties to its amount over revenue; a header split
  from its rows is laid over the rows' right-hand columns. Runwal reads completely.

- Related-party check reads percentages printed without a % sign (Runwal) when they tie out to amount over
  verified revenue; refuses to read an amount as a share; no longer treats a header with no rows as a
  successful read; withholds figures that have no header of their own. Analysis version 30.

## 0.3.0 (2026-11-13)

- Demo site (`site/`, published by `.github/workflows/pages.yml`): a static page with briefs for 37
  public filings, search and filters, every page link to the public source; built from
  `tools/build_demo.py`, checked by `tests/test_site.py` (no markup from data, no external requests).
- Numbers: one formatting module on each side (`ipo_engine/numfmt.py`, `frontend/src/lib/numfmt.ts`):
  Indian grouping, ₹ crore with two decimals, a true minus with losses in red, exact half-up rounding
  (the web side no longer rounds through binary floats), aligned columns in briefs and terminal output.
- Web app: refreshed styling (palette, elevation, brand mark, navigation icons) and a dashboard
  introduction.

- `ipo run FILE.pdf`: one command registers a PDF, parses, analyses and writes the brief and report.
- Related-party evidence check: rows of the summary table printed at 5% of revenue or more, with page
  and row, in the analysis, the brief and the full report. Withholds tables it cannot read with
  certainty. 0 wrong rows on 13 scored filings, 3 of them never seen before labelling.
- One home page (`data/reports/index.html`) lists every filing by what to read first and links the
  brief and the full report.
- Web app: a "Reader brief" tab on each document runs the reader on the upload
  (`/api/v1/documents/{id}/reader`).
- Section map stored in the analysis; briefs name the section of each cited page.
- The command is `ipo` only (the old `rh` alias is gone). Helper scripts moved to `tools/screening/`;
  held-out run notes moved to `docs/history/`.
- Fixed: the demo and timing scripts could not start after the merge; the extraction benchmark wrote
  its results to a path that no longer existed.

## 0.2.0 (2026-11-07)

- The reader (was `redherring/`) and the screening app (was `backend/`) became one package,
  `ipo_engine`, with one test suite, one CI workflow and one README. Project named IPO Engine.
- `ipo add` registers a local PDF; `ipo serve` starts the API.
- Briefs show the table rows behind each item and count repeated readings once.

## 0.1.0 (2026-10)

- The reader: parse, extract, verify, twelve red-flag rules, HTML report, version diff, benchmark,
  one-page brief and triage table.
