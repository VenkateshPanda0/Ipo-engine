# Glitch and reliability audit (GLT-001 to GLT-100)

Every entry below was assessed one of these ways, and the CSV (`11_AUDIT_CHECKLIST.csv`) holds all 13 requested fields per entry. A **Tested — Not Found** means a named test, probe or review looked for the problem and did not find it; it does not mean the problem cannot exist. **Inconclusive** means it was not exercised here, and says so. The 100 entries are the issue types judged relevant to this project; they were chosen from the codebase's own surface (see `12_RESEARCH_SOURCES.md`), not generated to a quota.

| Status | Count |
|---|---:|
| Fixed — Verified | 10 |
| Tested — Not Found | 33 |
| Not Applicable | 2 |
| Inconclusive | 46 |
| Confirmed | 5 |
| Fixed — Verification Pending | 1 |
| Blocked | 3 |

## Confirmed and fixed or open

| ID | Issue | Severity | Status | Ledger | Fix |
|---|---|---|---|---|---|
| GLT-001 | React hydration error on a prerendered page | P3 | Fixed — Verified | F-42 | 5cb0cd5 |
| GLT-002 | Horizontal overflow at 320 px on /rules | P3 | Confirmed | F-44 | — |
| GLT-003 | Horizontal overflow at 320 px in the static demo | P3 | Confirmed | F-44 | — |
| GLT-009 | API key kept in sessionStorage readable by scripts | P4 | Confirmed | F-45 | — |
| GLT-021 | Documentation drifts from behaviour | P4 | Fixed — Verified | F-43 | 32a3179 |
| GLT-026 | Memory per uploaded PDF | P2 | Fixed — Verified | F-01 | 4ee4603 |
| GLT-027 | Time to analyse a hostile caption | P2 | Fixed — Verified | F-02 | 4ee4603 |
| GLT-028 | Slow receiver blocks all webhook delivery | P3 | Fixed — Verified | F-09 | 64b8ba6 |
| GLT-029 | Unbounded growth of rate-limit state | P2 | Fixed — Verified | F-35 | f23ac18 |
| GLT-033 | Timeout handling on outbound calls | P3 | Fixed — Verified | F-09 | 64b8ba6 |
| GLT-039 | Worker health in compose | P3 | Fixed — Verification Pending | F-41 | b7545c5 |
| GLT-042 | Scalability: single dispatcher thread for all organisations | P4 | Confirmed | F-46 | — |
| GLT-048 | Inconsistent wording of flags vs numbers | P3 | Fixed — Verified | F-37 | 011b9de |
| GLT-049 | Silent wrong value instead of abstaining | P2 | Fixed — Verified | F-20 | 394ff28 |
| GLT-057 | Output overwritten through a planted link | P4 | Fixed — Verified | F-17 | 4ee4603 |
| GLT-081 | Pre-commit hooks pinned | P4 | Confirmed | F-29 | — |

## Full checklist

| ID | Issue type | Status | Evidence |
|---|---|---|---|
| GLT-001 | React hydration error on a prerendered page | Fixed — Verified | agent:frontend;own:Chromium probe |
| GLT-002 | Horizontal overflow at 320 px on /rules | Confirmed | agent:frontend |
| GLT-003 | Horizontal overflow at 320 px in the static demo | Confirmed | agent:frontend |
| GLT-004 | axe violations on main routes (light and dark) | Tested — Not Found | agent:frontend (0 on 14 routes) |
| GLT-005 | Colour contrast below WCAG AA | Tested — Not Found | exist:a11y.spec.ts (earlier fix) |
| GLT-006 | Modal focus trap and focus return | Tested — Not Found | exist:modal.test.tsx |
| GLT-007 | Keyboard-only walk-through of main flows | Inconclusive | nt (needs a person) |
| GLT-008 | Screen-reader walk-through | Inconclusive | nt (needs a person) |
| GLT-009 | API key kept in sessionStorage readable by scripts | Confirmed | agent:frontend (mitigated by strict script-src) |
| GLT-010 | Stale data after a mutation (React Query) | Inconclusive | nt |
| GLT-011 | Double submit on slow network | Inconclusive | nt |
| GLT-012 | Unhandled promise rejection in UI | Tested — Not Found | agent:frontend (none seen in probes) |
| GLT-013 | Error state shown for failed requests | Tested — Not Found | exist (ErrorState component, e2e) |
| GLT-014 | Loading state flashes / layout shift | Inconclusive | nt |
| GLT-015 | Empty state wording | Inconclusive | nt |
| GLT-016 | Dark mode rendering | Tested — Not Found | agent:frontend (axe only) |
| GLT-017 | Cross-browser: Firefox / WebKit | Blocked | nt (only Chromium installed) |
| GLT-018 | Mobile viewport usability | Inconclusive | agent:frontend (overflow findings only) |
| GLT-019 | Broken navigation / dead links | Tested — Not Found | exist:tests/test_docs.py;exist:tests/test_site.py |
| GLT-020 | Broken internal documentation links | Tested — Not Found | exist:tests/test_docs.py |
| GLT-021 | Documentation drifts from behaviour | Fixed — Verified | agent:supply-chain |
| GLT-022 | Unresponsive UI under a heavy case list | Inconclusive | nt |
| GLT-023 | Request latency under load (load test) | Tested — Not Found | own:tools/loadtest.py 120 req/s, no 5xx, no leaks |
| GLT-024 | Throughput collapse with many organisations | Tested — Not Found | own:tools/loadtest.py (3 organisations) |
| GLT-025 | Tail latency (p99) too high | Inconclusive | own:baseline p99 up to 306 ms while 8 agents shared the machine; not a clean measurement |
| GLT-026 | Memory per uploaded PDF | Fixed — Verified | agent:ingest (bomb 452 MB for 204 KB) |
| GLT-027 | Time to analyse a hostile caption | Fixed — Verified | agent:ingest (22 s per 20k digits) |
| GLT-028 | Slow receiver blocks all webhook delivery | Fixed — Verified | agent:network |
| GLT-029 | Unbounded growth of rate-limit state | Fixed — Verified | agent:db |
| GLT-030 | Duplicate operation on retry (idempotency) | Inconclusive | nt |
| GLT-031 | Webhook duplicate delivery | Tested — Not Found | exist:test_webhooks.py (outbox, attempts) |
| GLT-032 | Network interruption during delivery | Tested — Not Found | exist:test_webhooks.py |
| GLT-033 | Timeout handling on outbound calls | Fixed — Verified | agent:network;own:test_audit_hardening.py |
| GLT-034 | Recovery after worker crash | Inconclusive | nt |
| GLT-035 | Recovery after database restart | Inconclusive | nt |
| GLT-036 | Startup failure on bad configuration | Tested — Not Found | exist:test_deploy_files.py;exist (config validators) |
| GLT-037 | Graceful shutdown | Inconclusive | nt |
| GLT-038 | Health endpoint reports real readiness | Tested — Not Found | exist (ping() check) |
| GLT-039 | Worker health in compose | Fixed — Verification Pending | agent:supply-chain;own:compose edited (not run: no Docker) |
| GLT-040 | Log volume / log injection | Tested — Not Found | agent:auth (request id validated) |
| GLT-041 | Metrics endpoint exposure | Tested — Not Found | exist (admin only, off by default) |
| GLT-042 | Scalability: single dispatcher thread for all organisations | Confirmed | agent:network (design note) |
| GLT-043 | Scalability: in-process limiter per replica | Tested — Not Found | exist (DbRateLimiter option) |
| GLT-044 | Backup while serving traffic | Tested — Not Found | exist:test_backup.py |
| GLT-045 | Restore round trip | Tested — Not Found | exist:test_backup.py |
| GLT-046 | Large export memory use | Inconclusive | nt |
| GLT-047 | Inconsistent output across runs | Inconclusive | nt (hash-seed matrix not run) |
| GLT-048 | Inconsistent wording of flags vs numbers | Fixed — Verified | agent:logic |
| GLT-049 | Silent wrong value instead of abstaining | Fixed — Verified | agent:logic |
| GLT-050 | Notification shown to the wrong person | Inconclusive | nt |
| GLT-051 | Stale share link view counters | Tested — Not Found | exist:test_exports_and_shares.py |
| GLT-052 | Expired invitation still usable | Tested — Not Found | agent:authz |
| GLT-053 | Expired session still usable | Tested — Not Found | exist:test_accounts.py |
| GLT-054 | Clock changes (DST, timezone) alter results | Inconclusive | nt |
| GLT-055 | Unicode digits / RTL text in tables | Tested — Not Found | agent:ingest;agent:logic |
| GLT-056 | Odd file names in the CLI (spaces, directories, missing) | Tested — Not Found | agent:ingest |
| GLT-057 | Output overwritten through a planted link | Fixed — Verified | agent:ingest |
| GLT-058 | Cached truncated file reused | Tested — Not Found | exist:tests/test_fetch.py |
| GLT-059 | Rate limit headers / Retry-After correctness | Tested — Not Found | exist (429 with Retry-After) |
| GLT-060 | Search / filter results inconsistent | Inconclusive | nt |
| GLT-061 | Table extraction misses rows on complex layouts | Inconclusive | nt (needs labelled corpus run: tools/diff_eval.py) |
| GLT-062 | OCR fallback quality | Blocked | nt (Tesseract absent) |
| GLT-063 | Scanned DRHP handled with a clear message | Tested — Not Found | exist (reason codes in validate_pdf tests) |
| GLT-064 | Error messages understandable to users | Inconclusive | nt |
| GLT-065 | Accessibility of PDF/HTML report output | Inconclusive | nt |
| GLT-066 | Print stylesheet / PDF export of report | Inconclusive | nt |
| GLT-067 | Time-zone display of timestamps | Inconclusive | nt |
| GLT-068 | Pagination controls on long lists | Inconclusive | nt |
| GLT-069 | Concurrent edit of the same case (lost update) | Inconclusive | nt |
| GLT-070 | Concurrent comment posting | Tested — Not Found | exist:test_concurrency_and_properties.py |
| GLT-071 | Concurrent share creation | Tested — Not Found | exist:test_concurrency_and_properties.py |
| GLT-072 | Cross-organisation isolation under concurrency | Tested — Not Found | exist:tools/loadtest.py;exist:test_concurrency_and_properties.py |
| GLT-073 | Cold start time | Inconclusive | nt |
| GLT-074 | Image size / layer bloat | Blocked | nt (no Docker) |
| GLT-075 | Healthcheck interval and timeout sanity | Tested — Not Found | agent:supply-chain |
| GLT-076 | Restart policy on repeated failure | Inconclusive | nt |
| GLT-077 | Disk space exhaustion by uploads | Inconclusive | nt |
| GLT-078 | Temporary file cleanup | Inconclusive | nt |
| GLT-079 | Stale lock files after crash (SQLite WAL) | Inconclusive | nt |
| GLT-080 | Dependency update PR breaks build | Tested — Not Found | exist (Dependabot PR #2 fails on its own branch, left unmerged) |
| GLT-081 | Pre-commit hooks pinned | Confirmed | agent:supply-chain (tag, not SHA) |
| GLT-082 | CI cache poisoning path | Inconclusive | agent:supply-chain (not demonstrated) |
| GLT-083 | Release process reproducible | Inconclusive | nt (tag push blocked in this environment) |
| GLT-084 | SBOM generated and accurate | Inconclusive | nt |
| GLT-085 | Licence compatibility of dependencies | Tested — Not Found | agent:frontend (MIT/Apache/BSD; optional LGPL sharp-libvips) |
| GLT-086 | Python dependency licences | Inconclusive | nt |
| GLT-087 | Telemetry or phone-home in dependencies | Inconclusive | nt |
| GLT-088 | Next.js build warnings | Inconclusive | nt |
| GLT-089 | Console errors on every route | Inconclusive | agent:frontend (hydration only) |
| GLT-090 | Favicon / metadata 404s | Inconclusive | nt |
| GLT-091 | Print of long tables truncates | Inconclusive | nt |
| GLT-092 | Behaviour with JavaScript disabled | Not Applicable | na (single-page application by design) |
| GLT-093 | Focus management after a route change / skip link | Inconclusive | nt |
| GLT-094 | Form errors announced to assistive technology | Inconclusive | nt |
| GLT-095 | Browser back / forward restores state | Inconclusive | nt |
| GLT-096 | Pasted API key with stray whitespace | Inconclusive | nt |
| GLT-097 | Offline / slow-network feedback | Inconclusive | nt |
| GLT-098 | Very long company names overflow cards | Inconclusive | nt |
| GLT-099 | In-flight requests cancelled on rapid navigation | Inconclusive | nt |
| GLT-100 | Real-time sync between tabs | Not Applicable | na (no websocket or live sync in this product) |
