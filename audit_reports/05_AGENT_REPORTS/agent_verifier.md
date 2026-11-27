# Independent verification of the fixed findings

Verifier: independent agent. It did not implement any fix and did not write the original findings.
Baseline is commit f970795 (throwaway worktree, removed afterwards). Fixed is the checked-out
branch audit/remediation-2026-11. Scripts are in /tmp/verify_*.py. They are adapted copies of the
originals in /tmp/agent_* (the originals insert the repo `src` into `sys.path`, which would defeat
`PYTHONPATH`; scripts that import the app were run from a scratch cwd so the module-level
`create_app()` did not touch `./data`). No tracked file was modified and nothing was committed.
The full test suite on the fixed code: 1271 passed, 8 skipped.

## Results

| Finding | Baseline | Fixed | Verdict |
|---|---|---|---|
| F-21 erase failure leaves triggers dropped | after failed erase 2 of 8 triggers remain; `UPDATE case_data_versions` succeeds (rowcount 1) | 8 of 8 triggers remain; the UPDATE fails with "case_data_versions is append-only". Also held after a prior SELECT, after an INSERT, after an IntegrityError in the section, and inside a savepoint | PASS |
| F-01 deflate bomb | 200 KB, 1 MB and 30x shared 200 MB streams all accepted | all three rejected `too_large_decoded` in 0.1-0.2 s, RSS about 49 MB. Real corpus: 41 PDFs in data/raw (441 MB) plus tests PDFs, 0 false rejections, slowest 1.1 s | PASS for single-FlateDecode streams. Residual bypass, see N-1 |
| F-02 quadratic regex, digits with no unit | `detect_unit('1'*N)`: 0.22 s at 2k, 3.4 s at 8k, 22 s at 20k digits (also with a trailing x, commas, caption form) | 0.004 s at 20k digits; `related_party._FIGURE` also linear | PASS |
| F-03 sole admin self-demotes via POST /org/members | 201, org left with 0 admins | 422 "must keep at least one admin" | PASS |
| F-04 non-owner admin removes the owner | 204 | 403 | PASS |
| F-06 child token survives parent revocation | child token still returns 200 | child returns 401. Also checked on a DB created by baseline code and migrated to 0007: old token still authenticates, child revoked with parent | PASS |
| F-07 share link after org delete | public link still serves the report | link no longer serves | PASS |
| F-08 NAT64 / ::127.0.0.1 target | `[64:ff9b::7f00:1]`, `[::127.0.0.1]` allowed; POST /webhooks returned 201 for `[64:ff9b::a9fe:a9fe]` | both blocked (422 "non-public address") | PASS |
| F-09a port 99999 gives 500 | 500 INTERNAL_ERROR for `:99999` and `:abc`; `:0` accepted | 422 "invalid port" for all three | PASS |
| F-09b slow-drip receiver | body drip (1 byte per 0.5 s): call blocked 50.0 s; header drip 63 s | header drip cut at 20.0 s. Body drip: still 50.0 s when the server is HTTP/1.0 or sends `Connection: close`. Cut at 20.0 s only for an HTTP/1.1 keep-alive response | FAIL (partial), see N-2 |
| F-10 backup verify | `../../secret.txt`, absolute and `documents/../..` names, an unlisted pdf and an unlisted symlink: verify OK, restore copied the symlink target ("TOPSECRET") | all refused (outside the backup / not listed); a listed symlink is refused; a manifest without `files` gives BackupError (was KeyError); a clean backup still verifies and restores | PASS |
| F-11 60 wrong bearer keys, limit 5 | 60 x 401, never 429 | 5 x 401 then 55 x 429; the right key still returns 200 right after; a valid key is still limited at 5 per minute as before | PASS |
| F-13 CORS_ORIGINS=* | accepted (`['*']`, also `a,*`) | ValidationError for `*` and for `a,*`; a plain origin and an empty value accepted | PASS |
| F-20 Q1 FY2025 as full year / 15-month keyed FY | `Q1/H1/9M FY2025` all produce fact FY2025 (full year); 15-month header gives FY2023 | the three labels produce no fact; 15 months gives key `15M-2023-03-31`; `April 1, 2023 to March 31, 2024` now FY2024 (was `?-2023-04-01`) | PASS |
| F-32 8 concurrent first sign-ins give IntegrityError | 1 ok, 7 IntegrityError (`users.email`); 6 rounds x 8: 11 ok, 37 errors | 1 ok, 7 IntegrityError at `services/accounts.py:603` (`sign_in`: `s.add(user); s.flush()`); 6 rounds: 7 ok, 41 errors | FAIL, see N-3 |
| F-35 rate limiter keeps 50,000 keys | 50,000 keys, and still 50,003 after 120 s and further calls | 50,000 keys immediately after the burst (no cap); after 120 s and 2048 further calls: 3 keys | PASS (stale keys are freed; growth within one minute is unbounded) |
| F-36 US$ in million scaled as rupees | `detect_unit` returns MILLION, so a rupee fact of 12,500,000 | returns None, no fact | PASS, with a false-abstain side effect, see N-4 |
| F-37 25.4% printed as 25% against 25% | "25% against a limit of 25%; the figure is above it" | "25.4% against a limit of 25.0%"; 25.01% against 25.00%; 24.95% against 25.00%; a non-consecutive FY2021/2023/2024 series gives `missing_inputs` instead of "3 of the last 3 years" | PASS |

Counts: 15 PASS, 2 FAIL (F-09b slow-drip, F-32), 0 UNABLE. F-01 is PASS with a bypass
(N-1); F-09 is split: the port part passes and the slow-drip part fails.

## New problems found

| ID | Where | Reproduction | Severity |
|---|---|---|---|
| N-2 | `src/ipo_engine/screening/network/webhook_http.py` `_cut_off` / `PinnedSender.send` (about lines 119-156) | `/tmp/verify_drip.py`: a receiver that sends `HTTP/1.0 200` (or `Connection: close`) with `Content-Length: 100000`, then 1 byte every 0.5 s. `getresponse()` calls `conn.close()` for a response that will close, which sets `conn.sock = None`. `_cut_off` then finds no socket and does nothing, so the 20 s guard never fires. Delivery returned `200` after 50.0 s on the fixed code (same as baseline). With HTTP/1.1 keep-alive the guard works (20.0 s). The drip can be 1 byte per 9 s for as long as the attacker likes. The fix needs to keep a reference to the socket (or the response `fp`) before `getresponse()`. | P3 (the original severity; the shared dispatcher can still be stalled) |
| N-3 | `src/ipo_engine/screening/services/accounts.py:603` (`AccountService.sign_in`) | `/tmp/verify_f32.py`: 8 threads call `sign_in(...)` for the same new verified email: 7 raise IntegrityError (a 500 on the OIDC callback). The savepoint fix was applied to `get_or_create_user` only. That function did not fail in my race either on baseline (8 of 8 ok), so the new test `test_many_first_sign_ins_for_one_new_email_all_succeed` exercises the wrong function. `sign_in` still creates the `UserRow` and the `IdentityRow` without handling the unique-violation. | P2 as originally rated |
| N-1 | `src/ipo_engine/screening/intelligence/ingest.py` `_is_flate_only` / `_check_decoded_size` | `/tmp/verify_f01c.py`: a 300 MB bomb with `/Filter [/FlateDecode /FlateDecode]` (file 1 KB) or `[/ASCIIHexDecode /FlateDecode]` (file 597 KB) is ACCEPTED; single flate, `[/FlateDecode]` and flate with a PNG predictor are rejected. Only streams whose filter list is exactly one FlateDecode are measured. Baseline accepted all of them, so this is an incomplete fix, not a regression. I did not check what the later extraction stage does with such a stream. | P3 |
| N-4 | `src/ipo_engine/parse/units.py:66-87` `_FOREIGN_CURRENCY` | A rupee caption now abstains if any foreign-currency token is in the same text: `'(₹ in million) Note: US$ 1 = ₹ 83.20'`, `'Rs. in Lakhs (Dollar loans in USD shown separately)'`, `'(₹ in million) EUR hedges'` all give None (baseline: the right unit). `parse/pdf.py:388` applies `detect_unit` to prose within 90 points above a table. Real data: `data/raw/sahajanand_medical_rhp_2026.pdf` pages 200-420, baseline vs fixed per table: page 321 table (caption "(in ₹ million)", the paragraph above says "commission of USD 50,000 per annum") went from million to None; page 402 tables captioned "Amounts in INR million" with USD/EUR row labels went to None or lost the direct caption. 3 of about 295 tables in that range lost the unit; the other PDFs tried (Aadhar, Neev, Laxmi, same page ranges) were identical. Abstaining is the safe direction, but it drops coverage on legitimate rupee tables. A narrower rule (a currency token directly in the unit phrase, or a rupee marker wins) would avoid it. | P3 (data coverage, no wrong number) |
| N-5 | `src/ipo_engine/parse/units.py` two-unit rule | `'(Amounts in Rs. Lakhs, unless stated, except Rs. in Crore)'` and `'(Rs in Lakhs / Rs in Crores)'` now give None (baseline Lakh). First-unit-wins was wrong in some cases but these captions state a primary unit. The same abstain-on-ambiguity trade-off. | P4 |
| N-6 | `src/ipo_engine/extract/periods.py:112-115` | A fiscal header that mentions a quarter or half only in a side note now returns None where baseline correctly gave FY: `'FY2022-23 (including Q4 adjustments)'`, `'Fiscal 2024 (see H1 note)'`. No false parse is produced (the period is dropped), so the effect is lost facts. Unchanged and correct: `Three months ended June 30, 2024`, `Year ended March 31, 2024`, `FY 2022-23`, `As at March 31, 2024` (instant), `April 1, 2023 to March 31, 2024`, `1 April 2023 – 31 March 2024`, and about 100 other headers (I diffed baseline against fixed on the whole original /tmp/agent_logic table plus 45 more). | P4 |
| N-7 | `src/ipo_engine/screening/core/security.py` `_throttle_failed_credentials` | Every 401 counts, including requests with no credentials at all: with API_RATE_LIMIT_PER_MINUTE=5, ten unauthenticated GETs to a protected route give 5 x 401 then 5 x 429; a valid key still gets 200. The key is the socket peer address, so behind a reverse proxy all clients share one counter (and `unknown` when there is no peer). A signed-out browser polling a protected route can see 429 instead of 401. Off by default. | P4 |
| N-8 | `webhook_http._TRANSITIONAL` | Rejects the whole 64:ff9b::/96 and `::/96`. A deployment on an IPv6-only network that reaches IPv4 webhook hosts through DNS64/NAT64 will have every such webhook refused. I did not test a real DNS64 resolver; this is from reading the ranges. | P4 |
| N-9 | `api/routers/accounts.py` `_protect_owner` | An API-key admin (`Principal.user_id` is the key's label, not a member) is never an owner, so it can no longer change or remove an owner through the API; only the CLI can. I did not test this against a deployment with accounts enabled and key-only admins; from reading `is_owner`. Likely intended. | P4 (behaviour note) |
| N-10 | `core/security.py` `safe_equals` | `safe_equals('\ud800', 'x')` raises UnicodeEncodeError (lone surrogate). Not reachable from the call sites I read (headers and query values are decoded without surrogates). | P4 (theoretical) |

Other things I tried that held up: `append_only_lifted` / `_open_sqlite_transaction` (above, 7
scenarios); migration 0007 upgrade on a 0006 database with data; `_check_decoded_size` on all
real PDFs and test fixtures (no false rejection, the whole corpus checked in about 20 s, RSS 221 MB
peak for the whole run); `RateLimiter._prune` (3 keys left after expiry; prune runs under the lock
and only every 1024 calls, so a burst followed by silence keeps its keys until the next 1024
calls); token expiry capping (a child never outlives its parent); backup verify and restore on a
clean backup.

## Limitations

- F-09b and F-32 were not re-run through a live network or a production database: the
  slow-drip receiver is a local Python HTTP server and the sign-in race is SQLite with 8 threads.
- F-35 was checked with a simulated clock (patching `time.monotonic` in `services/documents`).
- N-4 comes from one real document (3 PDFs compared, one with differences) and a page range per
  PDF, not the whole corpus.
- Postgres paths (`append_only_lifted`, savepoints) were not exercised; only SQLite.
- The behaviour of the extraction stage on multi-filter bomb streams (N-1) was not tested.
- N-8, N-9 and N-10 are from reading code, not from a run against a real deployment.
