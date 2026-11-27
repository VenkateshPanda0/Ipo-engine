# Test results

All commands ran inside the project's own virtual environment (`.venv`, Python 3.12.3) in the sandbox. The final run is after the second round of fixes (see `10_FINAL_VERIFICATION.md`). A first attempt of the baseline ran against the system Python by mistake and failed on a missing `fastapi`; it was discarded and redone, and those figures are not used.

## Python suite

| Run | Command | Result |
|---|---|---|
| Baseline, `main` at `f970795` | `pytest -q --cov=src/ipo_engine` | **1212 passed, 8 skipped**, 207.82 s |
| Final, audit branch | same | **1283 passed, 8 skipped**, 205.67 s |
| Gate, audit branch | `tools/gate.sh` (ruff format, ruff check, mypy, pytest) | `GATE OK` |

Failed tests: 0 in both runs. New passing tests: **71** (47 new test functions, several parametrized).

The 8 skips are the same in both runs: 7 need the Tesseract binary (not installed), 1 needs a PostgreSQL server and client tools (`IPO_TEST_PG_ADMIN_URL`).

## Coverage (line coverage; branch coverage was not enabled)

| | Statements | Covered | Percent |
|---|---:|---:|---:|
| Baseline | 12,250 | 11,438 | 93.37% |
| Final | 12,487 | 11,667 | 93.43% |

Raw figures: `raw/cov_baseline.json`, `raw/cov_final.json`.

## Static analysis and dependency scans

| Tool | Result |
|---|---|
| `ruff check .` | clean before and after |
| `mypy` (265 files before, 267 after) | no issues before and after |
| `pip-audit` in the project venv | no known vulnerabilities (before) |
| `npm audit --omit-dev` (run by the frontend agent) | 0 vulnerabilities |
| `bandit -r src` | 0 high, 1 medium, 25 low. The medium is `urlopen` in `network/http.py`, reached only after `require_https`; the lows are asserts, constant strings that look like passwords (`ipo_` prefix and an enum value), and `subprocess` calls with fixed argument lists. No finding was exploitable. |

A second `pip-audit` of the whole global interpreter listed 97 findings; those are packages of the sandbox's system Python, not of the project, and are not counted.

## Frontend

| Check | Result |
|---|---|
| `tsc --noEmit` | clean |
| `vitest run` | 7 files, 49 tests passed (before and after the one-line change) |
| Production build + Chromium probe of `/organisation` | 0 hydration errors after the fix (the frontend agent reproduced React error 418 there before) |
| axe-core on 14 routes, light and dark, 1366 px (frontend agent) | 0 violations |

Playwright end-to-end specs were not run by me.

## Load and stress

`tools/loadtest.py --selfhost --duration 10` (three organisations, mixed reads and writes, leak check): 0 cross-organisation leaks and 0 unexpected responses in every run, before and after. Throughput is in `08_PERFORMANCE_REPORT.md`.

## Techniques used and not used

| Technique | Status |
|---|---|
| SAST (bandit, ruff, mypy) | run |
| SCA (pip-audit, npm audit) | run |
| Unit, integration, regression | run (full suite twice) |
| Property-based / fuzz | existing Hypothesis tests run; the logic agent ran its own Hypothesis checks (3,000-case number round trip); no coverage-guided fuzzer |
| Boundary and negative testing | by the agents, per `05_AGENT_REPORTS` |
| Concurrency | claim-queue (16 threads, 40 jobs), 8-way sign-in and sign-off races, rate limiter |
| Fault injection | failure inside the erase section; slow-drip server; hostile PDFs |
| Load and stress | `loadtest.py` |
| DAST | only a local server probed through TestClient and a browser; no scanner such as ZAP |
| End-to-end browser | production build probed with Chromium; Playwright suite not run |
| Mutation testing | **not run** |
| Memory profiling | peak resident size measured for hostile PDFs by the ingest agent; no profiler run |
| Compatibility | Python 3.12 only; Chromium only |
| Database integrity | SQLite only; PostgreSQL not available |
