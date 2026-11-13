# Contributing

```bash
uv sync                      # Python 3.12, all dependencies
cd frontend && npm ci        # only for the web app
```

## Before every commit

```bash
tools/gate.sh; echo rc=$?    # format, lint, strict type-check, all tests; never pipe it
make frontend-test           # if you touched frontend/
```

`rc=0` and `GATE OK` or it does not go in. CI runs the same commands plus a package build and a
production build of the web app.

## Rules of the house

- **A defect fix starts with a test that fails.** Then the fix.
- **Accuracy is measured, not asserted.** If output can change, run `uv run ipo --data-dir data eval
  --labels-dir labels` (needs the filings: `ipo ingest`, `ipo parse`, `ipo analyze`) and report the
  numbers it prints. Bump `PARSER_VERSION` or `ANALYSIS_VERSION` when stored output changes shape or
  meaning.
- **Labels before code.** For a new check, write and commit the labels first, then score the code
  against them (`tools/rp_score.py` is the pattern). A set of filings stays held out unless a defect
  it exposed was fixed.
- **Withhold, do not guess.** A figure that cannot be tied to its page, or a table whose header
  cannot be read with certainty, is reported as withheld with the reason.
- **No language model, no network** outside `ipo_engine/ingest/fetch.py`; `tests/test_offline.py`
  enforces it. Local, measured machine learning (OCR) is allowed.
- **A regulatory threshold names its clause, effective date and the date it was checked** against the
  primary text.
- Record a design decision in `docs/decisions.md`: what, the alternatives, why.

## Layout

See `docs/ARCHITECTURE.md`. Helper scripts are in `tools/` (see `tools/README.md`).
