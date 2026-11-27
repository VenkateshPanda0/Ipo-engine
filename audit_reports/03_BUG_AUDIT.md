# Software error audit (BUG-001 to BUG-100)

Every entry below was assessed one of these ways, and the CSV (`11_AUDIT_CHECKLIST.csv`) holds all 13 requested fields per entry. A **Tested — Not Found** means a named test, probe or review looked for the problem and did not find it; it does not mean the problem cannot exist. **Inconclusive** means it was not exercised here, and says so. The 100 entries are the issue types judged relevant to this project; they were chosen from the codebase's own surface (see `12_RESEARCH_SOURCES.md`), not generated to a quota.

| Status | Count |
|---|---:|
| Fixed — Verified | 19 |
| Tested — Not Found | 40 |
| Inconclusive | 27 |
| Confirmed | 9 |
| Fixed — Verification Pending | 1 |
| Blocked | 4 |

## Confirmed and fixed or open

| ID | Issue | Severity | Status | Ledger | Fix |
|---|---|---|---|---|---|
| BUG-001 | Erase failure leaves append-only triggers dropped | P1 | Fixed — Verified | F-21 | b7545c5 |
| BUG-002 | Concurrent first sign-ins raise IntegrityError (500) | P2 | Fixed — Verified | F-32 | f23ac18, 8055b5e |
| BUG-003 | Concurrent sign-offs on one report raise IntegrityError | P2 | Confirmed | F-34 | — |
| BUG-004 | In-process rate limiter never frees keys | P2 | Fixed — Verified | F-35 | f23ac18 |
| BUG-005 | Quarter / half / nine-month label read as a full year | P2 | Fixed — Verified | F-20 | 394ff28 |
| BUG-006 | Fifteen-month period keyed as a fiscal year | P2 | Fixed — Verified | F-20 | 394ff28 |
| BUG-007 | Dollar tables scaled as rupees | P2 | Fixed — Verified | F-36 | 394ff28 |
| BUG-008 | Two units in one caption: first wins | P3 | Fixed — Verified | F-36 | 394ff28 |
| BUG-009 | 'from X to Y' header uses the start date as period end | P3 | Fixed — Verified | F-20 | 394ff28 |
| BUG-010 | Breach text rounds the figure to equal its limit | P3 | Fixed — Verified | F-37 | 011b9de |
| BUG-011 | persistent_below counts across a missing year | P3 | Fixed — Verified | F-37 | 011b9de |
| BUG-012 | 'rs' matched inside words in unit detection | P4 | Confirmed | F-38 | — |
| BUG-013 | parse_amount accepts bad digit grouping ('12,50') | P4 | Confirmed | F-38 | — |
| BUG-014 | numfmt raises on NaN/Inf/huge values | P4 | Confirmed | F-38 | — |
| BUG-015 | Chosen citation page depends on input order | P4 | Confirmed | F-38 | — |
| BUG-016 | Worker that lost its lease still extends the new owner's | P3 | Confirmed | F-39 | — |
| BUG-017 | Manual retry does not reset attempts | P3 | Confirmed | F-39 | — |
| BUG-018 | Job with NULL lease is never requeued | P3 | Confirmed | F-39 | — |
| BUG-019 | Local-mode startup fails jobs of other replicas | P3 | Confirmed | F-40 | — |
| BUG-022 | Backup verify accepts files the manifest does not list | P2 | Fixed — Verified | F-10 | f23ac18 |
| BUG-033 | Worker container reported unhealthy by the API probe | P3 | Fixed — Verification Pending | F-41 | b7545c5 |
| BUG-045 | Unhandled exception in unauthenticated callback route | P4 | Fixed — Verified | F-12 | 64b8ba6 |
| BUG-046 | Non-ASCII signature header raises TypeError | P4 | Fixed — Verified | F-15 | 64b8ba6 |
| BUG-047 | Non-ASCII OIDC nonce raises TypeError | P4 | Fixed — Verified | F-23 | 32a3179 |
| BUG-048 | Request id with trailing newline reflected | P4 | Fixed — Verified | F-24 | 32a3179 |
| BUG-049 | Hydration mismatch on /organisation | P3 | Fixed — Verified | F-42 | 5cb0cd5 |
| BUG-066 | Documentation claims network use is limited to ipo ingest | P4 | Fixed — Verified | F-43 | 32a3179 |
| BUG-067 | Documentation says the web image is not yet built | P4 | Fixed — Verified | F-43 | 32a3179 |
| BUG-079 | Token table lacks the parent link (schema gap) | P3 | Fixed — Verified | F-06 | 64fdb6d |

## Full checklist

| ID | Issue type | Status | Evidence |
|---|---|---|---|
| BUG-001 | Erase failure leaves append-only triggers dropped | Fixed — Verified | agent:db;own:test_lifecycle.py |
| BUG-002 | Concurrent first sign-ins raise IntegrityError (500) | Fixed — Verified | agent:db;own:test_concurrency_and_properties.py |
| BUG-003 | Concurrent sign-offs on one report raise IntegrityError | Confirmed | agent:db |
| BUG-004 | In-process rate limiter never frees keys | Fixed — Verified | agent:db;own:test_rate_limiter_memory.py |
| BUG-005 | Quarter / half / nine-month label read as a full year | Fixed — Verified | agent:logic;own:test_periods.py |
| BUG-006 | Fifteen-month period keyed as a fiscal year | Fixed — Verified | agent:logic;own:test_periods.py |
| BUG-007 | Dollar tables scaled as rupees | Fixed — Verified | agent:logic;own:test_units.py |
| BUG-008 | Two units in one caption: first wins | Fixed — Verified | agent:logic;own:test_units.py |
| BUG-009 | 'from X to Y' header uses the start date as period end | Fixed — Verified | agent:logic;own:test_periods.py |
| BUG-010 | Breach text rounds the figure to equal its limit | Fixed — Verified | agent:logic;own:test_flags.py |
| BUG-011 | persistent_below counts across a missing year | Fixed — Verified | agent:logic;own:test_flags.py |
| BUG-012 | 'rs' matched inside words in unit detection | Confirmed | agent:logic |
| BUG-013 | parse_amount accepts bad digit grouping ('12,50') | Confirmed | agent:logic |
| BUG-014 | numfmt raises on NaN/Inf/huge values | Confirmed | agent:logic |
| BUG-015 | Chosen citation page depends on input order | Confirmed | agent:logic |
| BUG-016 | Worker that lost its lease still extends the new owner's | Confirmed | agent:db |
| BUG-017 | Manual retry does not reset attempts | Confirmed | agent:db |
| BUG-018 | Job with NULL lease is never requeued | Confirmed | agent:db |
| BUG-019 | Local-mode startup fails jobs of other replicas | Confirmed | agent:db (read only) |
| BUG-020 | Double claim of a queued job | Tested — Not Found | agent:db (16 threads, 40 jobs, 40 unique claims) |
| BUG-021 | Poison job retried for ever | Tested — Not Found | agent:db |
| BUG-022 | Backup verify accepts files the manifest does not list | Fixed — Verified | agent:db;agent:network;own:test_backup.py |
| BUG-023 | Backup restore of a truncated database | Tested — Not Found | agent:db (rejected by checksum) |
| BUG-024 | Restore into an existing database without --force | Tested — Not Found | agent:db |
| BUG-025 | Failed erase leaves partial deletions | Tested — Not Found | exist:test_lifecycle.py |
| BUG-026 | Foreign keys not enforced on SQLite | Inconclusive | agent:db (pragma is on; a rejected FK insert was not demonstrated) |
| BUG-027 | Migration chain up/down/up on empty database | Tested — Not Found | agent:db;exist:test_database_backends.py |
| BUG-028 | Migration on a populated database | Inconclusive | nt |
| BUG-029 | Timezone-naive vs aware datetime comparison | Inconclusive | agent:db (worked in tests, not stress-tested) |
| BUG-030 | SQLite 'database is locked' under concurrent writers | Tested — Not Found | agent:db (busy_timeout 30 s) |
| BUG-031 | Duplicate upload race | Inconclusive | nt |
| BUG-032 | Webhook outbox loses an event on a swallowed error | Tested — Not Found | exist:test_webhooks.py |
| BUG-033 | Worker container reported unhealthy by the API probe | Fixed — Verification Pending | agent:supply-chain;own:compose edited (not run: no Docker) |
| BUG-034 | Fetcher accepts a non-PDF or truncated download | Tested — Not Found | exist:tests/test_fetch.py |
| BUG-035 | Fetcher resumes after cut-off correctly | Tested — Not Found | exist:tests/test_fetch.py |
| BUG-036 | Number parsing nan / inf / 1e999 returns a value | Tested — Not Found | agent:ingest |
| BUG-037 | Indian number round trip (indian() / parse_amount) | Tested — Not Found | agent:logic (Hypothesis, 3000 cases) |
| BUG-038 | Percent sign handling, ratio boundaries, required_if | Tested — Not Found | agent:logic |
| BUG-039 | growth_gap boundary and consecutiveness | Tested — Not Found | agent:logic |
| BUG-040 | Diff of identical, reordered and empty documents | Tested — Not Found | agent:logic |
| BUG-041 | Consensus choice depends on input order | Tested — Not Found | agent:logic (chosen value stable) |
| BUG-042 | Full-pipeline determinism across hash seeds / TZ / LANG | Inconclusive | nt |
| BUG-043 | Type errors in source | Tested — Not Found | sast (mypy: no issues in 267 files) |
| BUG-044 | Lint errors | Tested — Not Found | sast (ruff clean) |
| BUG-045 | Unhandled exception in unauthenticated callback route | Fixed — Verified | agent:auth;own:test_audit_hardening.py |
| BUG-046 | Non-ASCII signature header raises TypeError | Fixed — Verified | agent:network;own:test_audit_hardening.py |
| BUG-047 | Non-ASCII OIDC nonce raises TypeError | Fixed — Verified | agent:auth;own:test_oidc_signature.py |
| BUG-048 | Request id with trailing newline reflected | Fixed — Verified | agent:auth;own:test_security_defaults.py |
| BUG-049 | Hydration mismatch on /organisation | Fixed — Verified | agent:frontend;own:production build + Chromium probe |
| BUG-050 | Memory growth from unbounded caches elsewhere | Inconclusive | nt |
| BUG-051 | File handle / connection leaks | Inconclusive | nt |
| BUG-052 | Memory leak in long-running worker | Inconclusive | nt |
| BUG-053 | Deadlock between worker threads and DB | Tested — Not Found | agent:db (no deadlock observed in claim tests) |
| BUG-054 | Off-by-one in pagination / limits | Inconclusive | nt |
| BUG-055 | Incorrect HTTP status codes on error | Tested — Not Found | exist:test_api_doc.py;agent:authz |
| BUG-056 | API contract drift from documentation | Tested — Not Found | exist:tests/test_api_doc.py |
| BUG-057 | Incorrect CSV export content | Tested — Not Found | exist:test_exports_and_shares.py |
| BUG-058 | XLSX produced is invalid | Tested — Not Found | exist:test_concurrency_and_properties.py (parsed with ElementTree) |
| BUG-059 | Build breaks on a clean checkout | Tested — Not Found | own:full gate and production frontend build |
| BUG-060 | Docker image does not build | Blocked | nt (no Docker in sandbox) |
| BUG-061 | Compose stack does not start | Blocked | nt (no Docker in sandbox) |
| BUG-062 | PostgreSQL-specific SQL differs from SQLite | Blocked | nt (no PostgreSQL server in sandbox; tests skip) |
| BUG-063 | Tesseract / OCR path | Blocked | nt (binary not installed; 8 tests skipped) |
| BUG-064 | Python 3.13 compatibility | Inconclusive | nt |
| BUG-065 | Dependency conflict on a clean install | Tested — Not Found | own:uv lock honoured by the venv |
| BUG-066 | Documentation claims network use is limited to ipo ingest | Fixed — Verified | agent:supply-chain;own:docs/security.md |
| BUG-067 | Documentation says the web image is not yet built | Fixed — Verified | agent:supply-chain;own:release.yml checked |
| BUG-068 | Dead code / unused imports | Tested — Not Found | sast (ruff) |
| BUG-069 | Float used for money | Tested — Not Found | agent:logic (Decimal throughout) |
| BUG-070 | Division by zero in ratios | Tested — Not Found | agent:logic |
| BUG-071 | Rounding mode / half-even surprises | Inconclusive | nt |
| BUG-072 | Locale-dependent formatting | Inconclusive | nt |
| BUG-073 | Hidden-text rule flip | Tested — Not Found | exist:tests/test_hidden_text.py |
| BUG-074 | Unit mismatch across tables of one document | Tested — Not Found | exist:test_units.py |
| BUG-075 | Cited number not on the cited page | Tested — Not Found | exist:tests/test_verify.py |
| BUG-076 | Stale manifest entry after file corruption | Tested — Not Found | exist:tests/test_fetch.py |
| BUG-077 | Race in manifest append | Inconclusive | nt |
| BUG-078 | Alembic head differs from models | Inconclusive | nt |
| BUG-079 | Token table lacks the parent link (schema gap) | Fixed — Verified | own:migration 0007 upgrade/downgrade in the suite |
| BUG-080 | Webhook retry storm after receiver outage | Tested — Not Found | exist:test_webhooks.py (backoff) |
| BUG-081 | Audit event missing for a security-relevant action | Inconclusive | nt |
| BUG-082 | Case data versions overwritten | Tested — Not Found | exist:test_lifecycle.py (triggers) |
| BUG-083 | Collaboration notification sent to wrong user | Inconclusive | nt |
| BUG-084 | Saved-search injection into queries | Tested — Not Found | agent:authz (read) |
| BUG-085 | Clock skew breaks token / signature checks | Tested — Not Found | exist:test_webhooks.py;exist:test_oidc_signature.py (leeway) |
| BUG-086 | Config validation accepts nonsense values | Inconclusive | nt |
| BUG-087 | Startup with missing secret file | Tested — Not Found | own:read config.py (raises a configuration error) |
| BUG-088 | Shutdown with an in-flight job | Inconclusive | nt |
| BUG-089 | kill -9 of a worker mid-job | Inconclusive | nt (lease expiry reviewed, not exercised) |
| BUG-090 | Large JSON body accepted | Tested — Not Found | exist:test_body_limit.py |
| BUG-091 | Pagination of audit trail loads everything | Inconclusive | nt |
| BUG-092 | Mutation testing | Inconclusive | nt (not run; see limitations) |
| BUG-093 | N+1 queries on list endpoints | Inconclusive | nt |
| BUG-094 | Webhook dispatcher thread dies on an unexpected exception | Inconclusive | nt |
| BUG-095 | HTTP connection not closed on error | Tested — Not Found | own:read webhook_http.py (closed in finally) |
| BUG-096 | Month-end and leap-day handling in period dates | Inconclusive | nt |
| BUG-097 | Duplicate users through email case or plus-addressing | Inconclusive | nt |
| BUG-098 | Bad encoding in robots.txt or response headers crashes the fetcher | Tested — Not Found | own:read fetch.py (errors=replace) |
| BUG-099 | Inconsistent document status after a partial pipeline failure | Inconclusive | nt |
| BUG-100 | Webhooks of a deleted organisation keep delivering | Inconclusive | nt |
