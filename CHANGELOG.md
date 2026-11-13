# Changelog

Notable changes to IPO Engine. The reasoning behind each is in `docs/decisions.md`; the screening
app's earlier history (to 2.0.1) is in `docs/screening/CHANGELOG.md`.

## 0.3.0 (2026-11-13)

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
