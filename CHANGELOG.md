# Changelog

All notable changes to IPO Engine are recorded here, in the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format. The package version follows
[Semantic Versioning](https://semver.org/); the other version numbers (API, ruleset, analysis) are
independent and explained in `docs/VERSIONING.md`. The reasoning behind each change is in
`docs/decisions.md` (the D-numbers).

The screening app's history before it joined this package (to 2.0.1) is in
[`docs/screening/CHANGELOG.md`](docs/screening/CHANGELOG.md), linked below under "Earlier history".

## [Unreleased]

### Added

- Documentation consolidated (W7): one index (`docs/README.md`) linking every document, including all held-out runs and the seven ADRs; one architecture diagram (Mermaid, validated) covering the reader, the screening app and the bridge between them; the 1.5-year-old audit of the first engine restored from git history (`docs/screening/audit/BASELINE.md`, deleted by mistake in the merge); a "where things moved" table at the top of the decision log. `tests/test_docs.py` fails on a broken relative link, a document not linked from the index, or a named file that does not exist; the CI `docs-links` job runs lychee in offline mode over the Markdown. The README gains release, licence and Python badges and three ways to run it (`uvx` straight from the repository, verified; Docker Compose; from source), and its limitations are stated up front.
- Community and governance files: `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), issue forms for a bug, a wrong figure and a feature request (blank issues off, security reports routed to private advisories), a pull request template with the release checklist, `CODEOWNERS` naming the regulatory and workflow paths, `SUPPORT.md`, `CITATION.cff`, and a `NOTICE` on the public-filing excerpts, their sources and the no-advice position. `docs/REPO_SETTINGS.md` lists the GitHub settings that must be applied by hand. `tests/test_repo_files.py` keeps these valid, every workflow action pinned to a commit SHA, and workflow permissions read-only by default.
- Workflows: CodeQL (Python and JavaScript/TypeScript, on pull requests, pushes and weekly), a full-history secret scan (gitleaks), and OpenSSF Scorecard with its badge in the README.
- One package version, written only in `pyproject.toml` and read by `ipo_engine.__version__`; `ipo --version`; `/api/v1/system/health` now reports `package_version`, `api_version`, `analysis_version` and `ruleset_version` (the older `version` field is kept); `docs/VERSIONING.md` explains the independent version numbers and the old `v1.0.0` tag. A release workflow, release checklist (`docs/RELEASING.md`) and release-notes extractor.
- Containers: the API `Dockerfile` is now two-stage, installs from `uv.lock`, pins its base images by digest, runs as uid 10001 and writes only to `/data`; a `frontend/Dockerfile` (Next.js standalone, non-root); `compose.yaml` (`docker compose up --build` gives the web app on :3000 and the API on :8000, both on 127.0.0.1, read-only root filesystems); a `docker` workflow that builds both images on every pull request, smoke-tests and scans them with Trivy (fixable HIGH/CRITICAL fail the build, all findings go to code scanning); the release workflow publishes both images; `.github/dependabot.yml` for uv, npm, docker and GitHub Actions.
- Litigation check, first slice (`checks/litigation.py`, D-065): reads the materiality-policy threshold and the material-creditor threshold from the first pages of the outstanding-litigation section, each with page and sentence; none or conflicting figures are reported, not guessed. Labels for ten filings (`labels/litigation/`), scorer `tools/lit_score.py`: 20 of 20 right, 0 wrong. Run over 28 other filings, 22 figures shown, all matching their pages after a fix for two wrong ones (a creditor figure read as the litigation threshold). 6 new tests. Now part of `ipo analyze` (`ANALYSIS_VERSION` 31, field `litigation`) and shown in the brief as a note ("a civil matter is disclosed above ₹ X crore (p.N); dues to a creditor are material above ₹ Y crore"); the demo site data was rebuilt. Benchmark unchanged (449/521 citations, 521/525 values); related-party plain-number set still 7 of 7.
- Related-party check reads percentages printed without a % sign (Runwal) when they tie out to amount over
  verified revenue; refuses to read an amount as a share; no longer treats a header with no rows as a
  successful read; withholds figures that have no header of their own. Analysis version 30.

### Changed

- One contact address, `venkateshpanda00@gmail.com`, in every file that names one: the Code of Conduct, `SECURITY.md` (as the fallback when GitHub private reporting is unavailable), `SUPPORT.md`, `NOTICE`, `CITATION.cff` and the package author field. A test keeps them in step. Git commits keep the GitHub no-reply identity.
- Litigation thresholds (D-067): six more wordings read (a defined term across a line or full stop; a single 5%-of-profit test stated "in excess of ... being"; "exceeds ₹N shall be considered Material Litigation"; "exceeding the lower of ... i.e. ₹N"; a figure followed by the board approval then the defined term; a creditor figure written "5.00% of ₹X which is ₹N"), and a filing that prints only the total trade payables no longer risks that total being read as the threshold (tested). Third label set `labels/litigation/thresholds3.json`; `tools/lit_score.py` 20/20, 20/20 and 12/12, 0 wrong (baseline of the earlier code on the third set: 6 right, 6 missed). Over the 40 parsed filings exactly the six intended figures appeared: litigation thresholds shown 26 to 31, creditor 24 to 25. `ANALYSIS_VERSION` 33; demo data rebuilt. Benchmark unchanged.
- `CONTRIBUTING.md` rewritten: uv-based setup, `make gate`, branch and Conventional Commit conventions, the behaviour-freeze rule (output changes need a version bump, the benchmark numbers and a D-number), how to add a red-flag rule, how to add a labelled filing. `pre-commit` is a dev dependency and the hooks run through uv (the old instruction, `pip install -e ".[dev]"`, did not work). `tools/gate.sh` uses a private temp directory instead of fixed `/tmp/rh-gate-*` files. The Pages workflow grants `pages: write` and `id-token: write` only to the deploy job.
- CI hardened: runs on pull requests and pushes to `main` only, one run per ref (`concurrency`), uv pinned to the lockfile's version with caching, every action in every workflow pinned to a full commit SHA, `contents: read` by default; Python 3.12 and 3.13 (the suite passes on both: 927 passed, 7 skipped without Tesseract); a coverage floor of 92% (currently 94%) with the XML kept as an artifact; the Playwright end-to-end suite now runs in CI against the real API and a production build of the web app (it had not run there before). `pages.yml` uses the same setup.
- Litigation thresholds (D-066): reads more wordings (lakhs; "exceeds ₹N, being 5% of"; "which amounts to"; "is the materiality threshold"; the policy's claim-amount test), and a concluding statement now outranks a defined term on another test: Laxmi India Finance showed ₹49.14 million (turnover test) where the filing concludes ₹12.41 million, now fixed; party-specific thresholds (Bajaj Housing) are reported as several, none shown. Second label set (`labels/litigation/thresholds2.json`). `tools/lit_score.py`: first set 20/20, second set 20/20 (baseline of the earlier code on the second set: 8 right, 9 missed), 0 wrong. 914 tests collected (903 at the start of the week). `ANALYSIS_VERSION` 32; demo data rebuilt.
- Docs: roadmap rewritten as the ordered TODO (done, next, needs a person, not started); docs index added (`docs/README.md`); plan, README, CONTRIBUTING, labels and tools READMEs brought in line with the code.
- Related-party check recovers rows the table reader left as plain text (Nityas Gems now reads all 3
  labelled rows) and requires every plain-number row to tie to its amount over verified revenue.
- Demo site: a filing's address is now `#filing-<name>` (letters, digits and hyphens), so a brief can be
  linked and also opens inside hosts that pass only a plain `#name`. Also published as a live page.
- Related-party check: a summary page that prints clearly more figures than the table reader captured
  is withheld instead of reported as having no large row; plain-number tables take the column order
  from the filing's other tables when each shown row ties to its amount over revenue; a header split
  from its rows is laid over the rows' right-hand columns. Runwal reads completely.

### Fixed

- Stale paths in the screening docs (test files named as they were before the merge) and two references to a file that no longer existed.
- The web image no longer carries npm, corepack or yarn from the Node base image: the container only runs `node server.js`, and their 10 HIGH vulnerabilities were the Trivy gate's first finding on the first CI run.
- The end-to-end test generated its sample PDF from the pre-merge `backend/` directory and had not run since the projects were merged; it now uses the repository root. All 5 end-to-end tests pass.
- `ipo ingest` no longer appends a duplicate manifest row when it re-downloads a PDF whose bytes match the recorded hash (a fresh checkout used to show a diff in `data/manifest.jsonl`: +2 rows on one run, +39 on another; now 0 on a re-download of Varyaa). Changed bytes are still recorded. Test added; 904 tests collected before this one.

### Security

- Production refuses to start with no API keys (it used to run every caller as an admin); `ALLOW_UNAUTHENTICATED=true` is the explicit opt-out, with a startup warning and an `X-IPO-Engine-Auth: disabled` response header. Development mode is unchanged.
- API responses carry `Content-Security-Policy` (closed for JSON, strict for HTML reports), and `Strict-Transport-Security` when `APP_ENV=production` and `TRUST_HTTPS=true`. The web app has a CSP that allows scripts from itself only (no inline, no eval); zod is set to `jitless` so it no longer triggers a CSP violation. Checked in Chromium: no violations while browsing, an injected inline script is blocked.
- `ipo keys hash` prints the `sha256=` form of an API key; key rotation is documented in `docs/security.md`. `SECURITY.md` added.
- Next.js 15.5.27 to 15.5.29 (critical advisory), `source-map-js` fixed, zod 3 to 4 (high
  advisory); `npm audit --omit=dev` reports 0 vulnerabilities. CI now audits both Python and shipped
  frontend dependencies.

## [0.3.0] - 2026-11-13

### Added

- Demo site (`site/`, published by `.github/workflows/pages.yml`): a static page with briefs for 37
  public filings, search and filters, every page link to the public source; built from
  `tools/build_demo.py`, checked by `tests/test_site.py` (no markup from data, no external requests).
- `ipo run FILE.pdf`: one command registers a PDF, parses, analyses and writes the brief and report.
- Related-party evidence check: rows of the summary table printed at 5% of revenue or more, with page
  and row, in the analysis, the brief and the full report. Withholds tables it cannot read with
  certainty. 0 wrong rows on 13 scored filings, 3 of them never seen before labelling.
- One home page (`data/reports/index.html`) lists every filing by what to read first and links the
  brief and the full report.
- Web app: a "Reader brief" tab on each document runs the reader on the upload
  (`/api/v1/documents/{id}/reader`).
- Section map stored in the analysis; briefs name the section of each cited page.

### Changed

- Numbers: one formatting module on each side (`ipo_engine/numfmt.py`, `frontend/src/lib/numfmt.ts`):
  Indian grouping, ₹ crore with two decimals, a true minus with losses in red, exact half-up rounding
  (the web side no longer rounds through binary floats), aligned columns in briefs and terminal output.
- Web app: refreshed styling (palette, elevation, brand mark, navigation icons) and a dashboard
  introduction.
- The command is `ipo` only (the old `rh` alias is gone). Helper scripts moved to `tools/screening/`;
  held-out run notes moved to `docs/history/`.

### Fixed

- the demo and timing scripts could not start after the merge; the extraction benchmark wrote
  its results to a path that no longer existed.

## [0.2.0] - 2026-11-07

### Added

- `ipo add` registers a local PDF; `ipo serve` starts the API.

### Changed

- The reader (was `redherring/`) and the screening app (was `backend/`) became one package,
  `ipo_engine`, with one test suite, one CI workflow and one README. Project named IPO Engine.
- Briefs show the table rows behind each item and count repeated readings once.

## [0.1.0] - 2026-10

### Added

- The reader: parse, extract, verify, twelve red-flag rules, HTML report, version diff, benchmark,
  one-page brief and triage table.

## Earlier history: screening app

Before 0.2.0 the screening app (then `backend/`) had its own versions, 1.0.0 to 2.0.1, with changes to
its ruleset and extraction. That record is kept unchanged in
[`docs/screening/CHANGELOG.md`](docs/screening/CHANGELOG.md).
