# Final verification

## How the fixes were checked

1. **Red before, green after.** For each fix I wrote a regression test, confirmed it fails on the code without the fix (by stashing the fix, or by running the test against a git worktree of `f970795`), and confirmed it passes with it. Against the baseline source, 25 of the first-round tests failed; the second-round tests were each shown failing before their fix.
2. **Gate.** `tools/gate.sh` (format, ruff, mypy, full pytest) reports `GATE OK` on the final commit. Final suite: 1283 passed, 8 skipped, 0 failed (baseline 1212 passed, 8 skipped).
3. **Independent verification.** A ninth subagent, which wrote no finding and no fix, re-ran the original reproductions against the baseline and the fixed branch (`05_AGENT_REPORTS/agent_verifier.md`).

## What the independent verifier found

On the first-round fixes it checked 18 rows: **16 PASS** (F-21, F-01, F-02, F-03, F-04, F-06, F-07, F-08, F-09 port part, F-10, F-11, F-13, F-20, F-35, F-36, F-37) and **2 FAIL** (F-09 slow-drip, F-32). Its own summary counts 15 PASS of 17; the table is the record. It also found six side effects of my fixes.

| Verifier finding | Verdict | What I did | Re-verified by |
|---|---|---|---|
| F-32 sign-in race still crashed: my fix and my test were on `get_or_create_user`, the race is in `sign_in` | my fix was wrong | savepoints in `sign_in`; new test on the real function | my test (red before, green after); **not re-run by the verifier** |
| F-09 drip not cut off when the reply says `Connection: close` | my fix was incomplete | keep our own socket reference; new bounded test | my test; not re-run by the verifier |
| F-01 stacked or ASCII-armoured deflate bombs still accepted | my fix was incomplete | refuse two deflate steps, decode ASCIIHex/85 first; test builds the file so the writer cannot re-encode it (my first test did not, and passed without the fix: caught and corrected) | my test; not re-run by the verifier |
| F-47 rupee captions with a USD/EUR note lost their unit (3 of ~295 real tables) | my fix over-reached | foreign currency counts only directly before the unit phrase | 4 new tests; not re-run on the real PDFs |
| F-48 fiscal year with a quarter side note dropped | my fix over-reached | part-year label must sit next to the fiscal label | 2 new tests |
| F-49 throttle counted requests with no credential | my fix over-reached | only requests carrying `Authorization` | new test |
| F-53 `safe_equals` on a lone surrogate | not reachable | `surrogatepass` | new test |
| F-50, F-51, F-52 | trade-offs or notes | not changed; listed in `09_UNRESOLVED_ISSUES.md` | n/a |

So the verification record is: **14 fixes passed the verifier cleanly on the first try; 3 first-round fixes failed or were incomplete under independent review and were redone; the redone fixes are verified by tests I wrote, not by a second independent pass.** A second verifier round was not run.

## Status of all 33 fixed findings

- 31: regression test or measurement, red before and green after, full gate green.
- F-41 (worker healthcheck in `compose.accounts.yaml`): edited, **not run**, no Docker in the sandbox. Status: Fixed — Verification Pending.
- F-43 (two documentation statements): corrected by reading against the code and `release.yml`; no test.

## Measured before and after

See `08_PERFORMANCE_REPORT.md`: unit detection on 20,000 digits 22.78 s to 0.005 s; a 199 KB deflate bomb accepted before, refused in 0.14 s now; no request-throughput change (81, 82 req/s before; 81, 78 after, within noise).

## Other checks

- Dependency rescan: not repeated after the fixes; no dependency changed (`uv.lock` and `package-lock.json` untouched), so the earlier clean `pip-audit` and `npm audit` results stand.
- Build: production frontend build succeeded and was served; the Docker image build was not run.
- Compatibility: Python 3.12 and Chromium only.
- Real data: the verifier ran the deflate check over the 41 real PDFs in `data/raw` plus test fixtures: 0 false rejections (slowest 1.1 s).

## Gaps in this verification

- No second independent pass after the second round of fixes.
- PostgreSQL paths (`append_only_lifted` on PostgreSQL, savepoints) were not executed.
- The checklist's 73 Inconclusive and 7 Blocked entries (`11_AUDIT_CHECKLIST.csv`) were not re-assessed because they were never exercised; they are the work remaining.
- Agent roles for performance, architecture review and compatibility were not run (`05_AGENT_REPORTS/README.md`).
