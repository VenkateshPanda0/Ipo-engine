# Contributing

Thank you for helping. Read `docs/CHARTER.md` first: the aims are fixed, and they decide what fits.
In short, the software runs **fully offline with no language model**, is **never silently wrong**
(a figure is shown with its page, or withheld with the reason), and **saves the reader time**.

By taking part you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). For a security problem, do not
open an issue: see [SECURITY.md](SECURITY.md). For questions, see [SUPPORT.md](SUPPORT.md).

## Set up

You need Python 3.12 or newer and [uv](https://docs.astral.sh/uv/); the web app also needs Node.js 22.

```bash
git clone https://github.com/VenkateshPanda0/Ipo-engine.git && cd Ipo-engine
uv sync                      # all Python dependencies, from the lockfile
cd frontend && npm ci        # only if you touch the web app
uv run pre-commit install    # optional: lint and format hooks on every commit
```

PDFs are not in the repository. To work on extraction you need the public filings:
`uv run ipo --data-dir data ingest`, then `parse` and `analyze` (parse takes minutes). Do **not**
commit anything under `data/` except `manifest.jsonl` and `sources.toml`.

## Everyday commands

```bash
make gate                    # format, lint, strict type-check, all tests (= tools/gate.sh)
make frontend-test           # type-check and unit tests for frontend/
make test                    # only the Python tests
make run                     # the API on http://127.0.0.1:8000; `make frontend-dev` for the web app
```

`make gate` must print `GATE OK` before a change goes in. Do not pipe it through `tail` or `grep`:
that hides the exit status (`tools/gate.sh; echo rc=$?`). CI runs the same checks, on Python 3.12 and
3.13, plus the end-to-end suite, container builds and scans, CodeQL and a secret scan.

## Branches, commits, pull requests

- **Contributors:** fork, make a branch (`fix/...`, `feat/...`, `docs/...`), open a pull request into
  `main`. Keep one change per pull request. The maintainer commits straight to `main`.
- **Commit messages** follow [Conventional Commits](https://www.conventionalcommits.org/): a type
  (`feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`, `chore`, `security`), an optional
  scope, and a short imperative summary: `fix(related-party): withhold a table whose header slips`.
  Say *why* in the body. Reference a D-number when a decision is recorded.
- Do not rewrite published history. Add a commit instead.
- The pull request template lists what is checked: gate, tests, changelog, version bumps, decision
  record, no secrets or non-public data.

## The behaviour-freeze rule

Output is versioned. **Any change that alters extracted figures, a rule outcome or a threshold needs:**

1. the matching version bump (`docs/VERSIONING.md`: `ANALYSIS_VERSION`, the ruleset version, or
   `API_VERSION`; `PARSER_VERSION` for parsing output);
2. the benchmark re-run and its numbers in the pull request and in `docs/status.md`
   (`uv run ipo --data-dir data eval --labels-dir labels`; plus `tools/rp_score.py` and
   `tools/lit_score.py` for the text checks);
3. a D-number in `docs/decisions.md` (what, the alternatives, why) and a line in `CHANGELOG.md`.

A change that is **not** meant to alter output (a refactor, packaging, docs, CI) must leave
`ANALYSIS_VERSION`, the ruleset and the `ipo eval` numbers identical, and must not bump them. If the
numbers move when you did not intend it, that is a bug.

## Rules of the house

- **A defect fix starts with a test that fails.** Then the fix.
- **Accuracy is measured, not asserted.** Quote the numbers the tools print.
- **Labels before code.** For a new check, write and commit the labels first, then score the code
  against them (`tools/rp_score.py` and `tools/lit_score.py` are the pattern). A set of filings stays
  held out unless a defect it exposed was fixed (`docs/decisions.md`, D-037).
- **Withhold, do not guess.** A figure that cannot be tied to its page, or a table whose header cannot
  be read with certainty, is reported as withheld with the reason.
- **No language model, no network** outside `src/ipo_engine/ingest/fetch.py`; `tests/test_offline.py`
  enforces it. Local, measured machine learning (OCR) is allowed.
- **A regulatory threshold names its clause, effective date and the date it was checked** against the
  primary text.
- **Public filings only.** Never commit or paste a confidential document, a key or personal data.

## How to add a red-flag rule (the reader)

A rule is one TOML file in `src/ipo_engine/flags/rules/`; no Python is needed for the kinds the engine
already supports (`src/ipo_engine/flags/spec.py` lists them: ratio against a cap, persistent breach,
required-if, and so on). Start from a similar file, for example `fin_cfo_vs_pat.toml`.

1. Write the spec: `id`, `name`, a one-sentence `rationale`, `platforms`, `severity`, a `[logic]`
   table over fact keys (`financials.profit_after_tax`, `objects.gcp_amount`, ...), and a
   `citation_requirement`.
2. Add at least one `[[sources]]` entry, and set `heuristic` (it is required). A **regulatory**
   threshold has `heuristic = false` and a `regulation` source that names the `clause`, its
   `effective` date and `checked_on`, taken from the primary text; the spec fails to load if a
   non-heuristic rule cites no regulation or enforcement source, or a regulation source has no
   clause. A threshold of our own is `heuristic = true`; by convention it cites the literature that
   motivates it and says plainly that the number is the project's choice.
3. Add tests in `tests/test_flags.py`: a hit, a near miss, and the case where inputs are missing (the
   rule must report it could not run, never pass silently).
4. Run the gate and `ipo eval`. Adding a rule does not change extraction, so the benchmark must not
   move; record the new rule count in `docs/status.md`, add a changelog line, and bump the version
   that `docs/VERSIONING.md` says applies.

Rules of the screening app (SEBI ICDR eligibility, Python classes in
`src/ipo_engine/screening/rules/`) are versioned as a ruleset: copy the current ruleset to a new
version, edit it, and follow `docs/screening/DEVELOPER_GUIDE.md` ("Adding or changing a rule").
Those paths have code owners (`.github/CODEOWNERS`), because a change there changes eligibility
outcomes.

## How to add a labelled filing

Labels are hand-written values and pages, read **independently of the extractor**, so they can catch
it being wrong. See `labels/README.md` for the format and its limits.

1. Add the public PDF to `data/sources.toml` (a `[[document]]` block with the source URL) and
   `uv run ipo --data-dir data ingest`.
2. Read the values off the PDF with a different tool from the extractor: `tools/pg.py` prints pages
   as poppler text (`page N`, `grep REGEX`). Do not copy values out of the extractor's output
   (`ipo label-init` pre-fills a draft from it; use that only to get the file layout, then replace
   every value with what you read).
3. Write a spec of the printed values and build the file with `tools/label_build.py`; it finds the
   pages and spans mechanically and fails on a value the PDF does not contain. For every field you
   label **absent**, run `--audit-absent` and read every line it prints before committing.
4. `uv run ipo --data-dir data label-check` validates the labels against the PDFs.
5. Commit the labels **before** running the extractor on a filing you want to keep held out. Then
   `ipo parse`, `ipo analyze`, `ipo eval`, and `tools/diff_eval.py` to see only the misses.
6. Record the run in `docs/history/` if it is a held-out set, with the first-run numbers.

## The demo site

`site/` is static. After re-analysing filings, `make demo` rewrites `site/briefs.json` (public filings
only; the exclusion list is `SKIP_IDS` in `tools/build_demo.py`); commit it and the Pages workflow
publishes it.

## Layout

`docs/README.md` is the index and `docs/ARCHITECTURE.md` the architecture. Helper scripts are in
`tools/` (`tools/README.md`).
