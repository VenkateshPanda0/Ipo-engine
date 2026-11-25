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

- Working together (accounts mode): assign a case to a member (`PUT /api/v1/cases/{id}/assignee`, `GET /cases?assignee=me`, "assigned to me" on the dashboard), comments on cases (viewers read, analysts write, authors and admins delete), in-app notifications for assignments and comments, per-person saved searches, organisation settings (`four_eyes`: the person who ran a screening cannot also sign it off, 409), a getting-started checklist (`/api/v1/onboarding`) and per-organisation usage counts (`/api/v1/org/usage`). Comments are included in the organisation export and in case erasure, and the tenant-isolation walker covers the new comment routes. Migration 0005; 17 new tests, run on SQLite and PostgreSQL.
- Data lifecycle: an organisation admin can export everything the organisation holds as a zip of JSON files (`GET /api/v1/org/export`, PDFs optional) and any person can export what is held about them (`GET /api/v1/me/export`, no secrets); an admin can erase a case for good (`DELETE /api/v1/cases/{id}?confirm=<exact name>`: rows, history and the stored PDF, which is kept if another case holds the identical file); an owner can switch an organisation off (sign-in, tokens and sessions stop at once) and `ipo accounts purge-org` erases it after the grace period. Erasure lifts the append-only triggers inside one transaction and restores them before commit (tested: they are back after success and after failure, on SQLite and PostgreSQL); the audit trail keeps an identifier-only record that the erasure happened. `ipo backup create|verify|restore`: a consistent online SQLite copy (or `pg_dump`), every stored PDF and a checksummed manifest; a damaged or incomplete backup is detected, and restore refuses to overwrite without `--force`. Round trips tested with data and documents on SQLite and PostgreSQL.
- Shared job queue and rate limits: `JOB_MODE=queue` leaves uploaded documents waiting in the database; any number of processes (the API itself, or `ipo worker`) claim them with one conditional update, so no job is taken twice (tested with four racing workers on SQLite and PostgreSQL), renew a lease while they work, and a job whose worker died is handed back after `JOB_LEASE_SECONDS`, or failed after `JOB_MAX_ATTEMPTS` so a poison document cannot loop. Starting a second process no longer marks another process's running jobs as failed (that restart behaviour is unchanged in the default `local` mode). `RATE_LIMIT_STORE=database` makes the upload limit one limit across processes, and `API_RATE_LIMIT_PER_MINUTE` adds a per-user request limit (429 with `Retry-After`). Migration 0004.
- PostgreSQL support (`DATABASE_URL=postgresql://…`, optional extra `postgres`, included in the container image): connection pool with liveness checks, URL normalised to the psycopg 3 driver, and append-only audit tables enforced by triggers on PostgreSQL as on SQLite (migration 0003). The whole application test suite (533 tests) passes unchanged against PostgreSQL 16 (`IPO_TEST_PG_ADMIN_URL=… pytest tests/screening` gives each app a fresh database), and a new CI job `postgres 16` runs it on every push. New tests assert the audit tables reject UPDATE and DELETE and that migrations round-trip on both backends.
- Accounts, part 2: browser sessions and optional Google sign-in (`GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`, off by default; authorization code with PKCE, single-use state bound to the browser, nonce and claim checks, no new dependency). Sessions are HttpOnly SameSite=Lax cookies (Secure in production or behind `TRUST_HTTPS`), stored only as a hash, with an absolute lifetime and an idle limit; every cookie-authenticated change needs the session's CSRF token and a known origin; sessions can be listed, revoked one by one or all but the current, and end at once when the user is suspended or removed. Invitations by link (shown once, expiring, revocable, bound to the invited address), invite-only sign-up by default (`SIGNUP_MODE=open` to change), an optional e-mail-domain allow list, per-session organisation switching. Tested end to end against an in-process identity provider (PKCE, nonce, replayed or foreign callbacks, forged claims, open redirects). The network code is confined to `screening/network/`, lazily imported and absent from a default start (D-068); `tests/test_offline.py` exempts only that package and `urllib.parse`.
- Accounts, part 1 (off by default, `ACCOUNTS_ENABLED=true`): organisations, users, memberships with per-organisation roles, and personal API tokens (`ipo_…`, shown once, only a SHA-256 stored, expiry, revocation, never above the owner's current role). Every case belongs to an organisation (migration 0002 assigns existing data to `org-default`); a router-wide check answers any case, document, report or review-item id from another organisation with the same 404 as an unknown id, lists and the dashboard are scoped, and the audit trail records the organisation and the real user id. A test builds the route list from the OpenAPI schema, calls every id route with another organisation's ids and demands 404, fails on an id parameter no rule covers, and a second test breaks the check on purpose to prove it would notice. The old unversioned routes are not served in accounts mode. `ipo accounts create-org|add-member|create-token|suspend|reinstate` for the first admin and recovery. Key-file and offline modes are unchanged; benchmark unchanged (521/525 values, 449/521 citations; litigation 20/20, 20/20, 12/12).
- The release workflow can be started by hand as a dry run (Actions > release > Run workflow): the same gate, wheel, SBOMs, provenance and two-architecture image builds, with no registry login, no image push or attestation, and no GitHub Release. A test asserts that mode cannot publish. It exists because a release tag cannot be pushed from the build session (the proxy refuses tag refs), and a pipeline that has never run should not be first exercised by a real release.
- Observability: `LOG_FORMAT=json|text` (JSON stays the default); every request log line now carries `principal` and the matched `route` template as well as `request_id`, method, path, status and duration. An optional Prometheus `/metrics` (`METRICS_ENABLED=true`, off by default, admin role only) with request counts and a duration histogram by route template and `ipo_build_info`; counters are per process. Tests cover the log fields (including `anonymous` for a rejected key and a bounded `unmatched` label), the formats, and the endpoint's absence, protection and content.
- Documentation consolidated (W7): one index (`docs/README.md`) linking every document, including all held-out runs and the seven ADRs; one architecture diagram (Mermaid, validated) covering the reader, the screening app and the bridge between them; the 1.5-year-old audit of the first engine restored from git history (`docs/screening/audit/BASELINE.md`, deleted by mistake in the merge); a "where things moved" table at the top of the decision log. `tests/test_docs.py` fails on a broken relative link, a document not linked from the index, or a named file that does not exist; the CI `docs-links` job runs lychee in offline mode over the Markdown. The README gains release, licence and Python badges and three ways to run it (`uvx` straight from the repository, verified; Docker Compose; from source), and its limitations are stated up front.
- Community and governance files: `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), issue forms for a bug, a wrong figure and a feature request (blank issues off, security reports routed to private advisories), a pull request template with the release checklist, `CODEOWNERS` naming the regulatory and workflow paths, `SUPPORT.md`, `CITATION.cff`, and a `NOTICE` on the public-filing excerpts, their sources and the no-advice position. `docs/REPO_SETTINGS.md` lists the GitHub settings that must be applied by hand. `tests/test_repo_files.py` keeps these valid, every workflow action pinned to a commit SHA, and workflow permissions read-only by default.
- Workflows: CodeQL (Python and JavaScript/TypeScript, on pull requests, pushes and weekly), a full-history secret scan (gitleaks), and OpenSSF Scorecard with its badge in the README.
- One package version, written only in `pyproject.toml` and read by `ipo_engine.__version__`; `ipo --version`; `/api/v1/system/health` now reports `package_version`, `api_version`, `analysis_version` and `ruleset_version` (the older `version` field is kept); `docs/VERSIONING.md` explains the independent version numbers and the old `v1.0.0` tag. A release workflow, release checklist (`docs/RELEASING.md`) and release-notes extractor.
- Containers: the API `Dockerfile` is now two-stage, installs from `uv.lock`, pins its base images by digest, runs as uid 10001 and writes only to `/data`; a `frontend/Dockerfile` (Next.js standalone, non-root); `compose.yaml` (`docker compose up --build` gives the web app on :3000 and the API on :8000, both on 127.0.0.1, read-only root filesystems); a `docker` workflow that builds both images on every pull request, smoke-tests and scans them with Trivy (fixable HIGH/CRITICAL fail the build, all findings go to code scanning); the release workflow publishes both images; `.github/dependabot.yml` for uv, npm, docker and GitHub Actions.
- Litigation check, first slice (`checks/litigation.py`, D-065): reads the materiality-policy threshold and the material-creditor threshold from the first pages of the outstanding-litigation section, each with page and sentence; none or conflicting figures are reported, not guessed. Labels for ten filings (`labels/litigation/`), scorer `tools/lit_score.py`: 20 of 20 right, 0 wrong. Run over 28 other filings, 22 figures shown, all matching their pages after a fix for two wrong ones (a creditor figure read as the litigation threshold). 6 new tests. Now part of `ipo analyze` (`ANALYSIS_VERSION` 31, field `litigation`) and shown in the brief as a note ("a civil matter is disclosed above ₹ X crore (p.N); dues to a creditor are material above ₹ Y crore"); the demo site data was rebuilt. Benchmark unchanged (449/521 citations, 521/525 values); related-party plain-number set still 7 of 7.
- Related-party check reads percentages printed without a % sign (Runwal) when they tie out to amount over
  verified revenue; refuses to read an amount as a share; no longer treats a header with no rows as a
  successful read; withholds figures that have no header of their own. Analysis version 30.

### Deprecated

- The legacy v0 API endpoints (`/screen/*`, `/reports/{id}`, `/reviews/*`, `/rules`, `/rules/{id}`, `/health`, `/ready`) will be **removed on 2027-05-25**. They still answer as before, and every response now carries `Deprecation: true`, `Sunset: Tue, 25 May 2027 00:00:00 GMT` and `Link: </api/v1/...>; rel="successor-version"` naming the v1 replacement; each call logs a `deprecated_v0_endpoint` warning with the path, the successor and the request ID. The web app uses `/api/v1` only. Move callers to `/api/v1` (`docs/screening/ARCHITECTURE.md`).

### Changed

- `services/cases.py` (899 lines) split along its existing seams: `case_values.py` (status enums, value parsing, and the status-derivation function that both services used), `case_screening.py` (the screening service and dashboard counts) and `cases.py` (the case lifecycle service, 649 lines), which re-exports every name it used to define, so no importer changed. The split also removed the only dependency of the screening service on the case service. No behaviour change: 968 tests pass (7 skipped as before), coverage stays 94%, the benchmark is identical.
- Lint carve-outs for the screening app removed where they were stale or mechanical: ruff's per-folder ignores for `src/ipo_engine/screening/` went from 11 rules to 2 (`UP042` and `UP046`, each with its reason in `pyproject.toml`) and for `tests/screening/` from 8 rules to a single `E402` in `conftest.py`; `RUF002` joined `RUF001` as a global ignore (typographic characters in docstrings that describe filings). `B008` (92 hits) is fixed properly with ruff's `extend-immutable-calls` for FastAPI's `Depends` and friends, which also caught one real case in new code. Fixed: 18 over-long docstring lines, `zip(x, x[1:])` to `itertools.pairwise`, list concatenation to unpacking, a sorted `__all__`, and a `ClassVar` annotation. No behaviour change: the benchmark, the litigation sets and the related-party set are identical.
- `tests/screening/` is now type-checked by mypy (it had been excluded): 34 errors fixed (annotations, narrowing asserts, casts for `Any` returns, two unneeded ignores removed); `reportlab`, which has no type stubs, joins the other untyped libraries in the existing override. mypy now checks 217 files, clean.
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

- Frontend test tooling upgraded to vitest 5, vite 8 and `@vitejs/plugin-react` 6, clearing the six dev-only advisories (one critical in `tinypool`, one high in vite): the full `npm audit` now reports 0 vulnerabilities, with no `--force` or `--legacy-peer-deps`, and CI audits everything at `--audit-level=high` instead of production only. The regenerated lockfile also moved React 19.2.7 to 19.3.1 and TanStack Query 5.101 to 5.108 (both within their ranges); typecheck, 31 unit tests, the production build and all 5 end-to-end tests pass, and the page CSP check shows no violation.
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
