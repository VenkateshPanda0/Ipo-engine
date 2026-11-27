# Security audit (SEC-001 to SEC-100)

Every entry below was assessed one of these ways, and the CSV (`11_AUDIT_CHECKLIST.csv`) holds all 13 requested fields per entry. A **Tested — Not Found** means a named test, probe or review looked for the problem and did not find it; it does not mean the problem cannot exist. **Inconclusive** means it was not exercised here, and says so. The 100 entries are the issue types judged relevant to this project; they were chosen from the codebase's own surface (see `12_RESEARCH_SOURCES.md`), not generated to a quota.

| Status | Count |
|---|---:|
| Fixed — Verified | 26 |
| Tested — Not Found | 62 |
| Not Applicable | 2 |
| Confirmed | 10 |

## Confirmed and fixed or open

| ID | Issue | Severity | Status | Ledger | Fix |
|---|---|---|---|---|---|
| SEC-005 | Path traversal through a backup manifest | P2 | Fixed — Verified | F-10 | f23ac18 |
| SEC-007 | Symlink following when adding a local file | P4 | Fixed — Verified | F-17 | 4ee4603 |
| SEC-008 | Symlink following in backup restore | P3 | Fixed — Verified | F-10 | f23ac18 |
| SEC-015 | Unvalidated server-supplied links navigate off-site | P4 | Confirmed | F-30 | — |
| SEC-017 | CSRF check crashes on non-ASCII header | P4 | Fixed — Verified | F-12 | 64b8ba6 |
| SEC-018 | CORS wildcard combined with credentials | P3 | Fixed — Verified | F-13 | 64b8ba6 |
| SEC-021 | SSRF through NAT64 / 6to4 / IPv4-compatible IPv6 | P3 | Fixed — Verified | F-08 | 64b8ba6 |
| SEC-024 | OIDC client follows redirects despite its documentation | P4 | Fixed — Verified | F-24 | 32a3179 |
| SEC-026 | Source fetcher opens file: / ftp: URLs | P4 | Fixed — Verified | F-16 | b7545c5 |
| SEC-033 | OIDC token with NaN expiry accepted | P4 | Fixed — Verified | F-23 | 32a3179 |
| SEC-035 | Email allow-list bypass with lookalike Unicode domain | P4 | Confirmed | F-25 | — |
| SEC-041 | Credential guessing is not throttled | P3 | Fixed — Verified | F-11 | 64b8ba6 |
| SEC-046 | Empty API_KEYS silently disables API_KEYS_FILE | P3 | Fixed — Verified | F-14 | 64b8ba6 |
| SEC-050 | Static demo has no Content-Security-Policy | P4 | Confirmed | F-33 | — |
| SEC-055 | Member escalates own role through POST /org/members | P3 | Fixed — Verified | F-03 | 64fdb6d |
| SEC-056 | Sole admin leaves organisation with no admin | P3 | Fixed — Verified | F-03 | 64fdb6d |
| SEC-057 | Non-owner admin removes or demotes the owner | P3 | Fixed — Verified | F-04 | 64fdb6d |
| SEC-058 | Token minted with no expiry | P4 | Fixed — Verified | F-05 | 64fdb6d |
| SEC-059 | Revoking a token leaves tokens it minted valid | P3 | Fixed — Verified | F-06 | 64fdb6d |
| SEC-060 | Share links keep serving after the organisation is deleted | P2 | Fixed — Verified | F-07 | 64fdb6d |
| SEC-064 | Sign-off reviewer name is free text and can impersonate | P4 | Confirmed | F-26 | — |
| SEC-069 | Webhook port parsing crashes the API (500) | P3 | Fixed — Verified | F-09 | 64b8ba6, 8055b5e |
| SEC-070 | Slow-drip webhook receiver stalls the shared dispatcher | P3 | Fixed — Verified | F-09 | 64b8ba6, 8055b5e |
| SEC-073 | S3 digest regex accepts a trailing newline | P4 | Fixed — Verified | F-15 | 64b8ba6 |
| SEC-077 | Export corrupts negative numbers ('-5) | P4 | Fixed — Verified | F-15 | 64b8ba6 |
| SEC-078 | Decompression bomb in an uploaded PDF | P2 | Fixed — Verified | F-01 | 4ee4603, 8055b5e |
| SEC-079 | Quadratic regex (ReDoS) in unit detection | P2 | Fixed — Verified | F-02 | 4ee4603 |
| SEC-083 | CLI path has no page, size or time cap | P3 | Confirmed | F-18 | — |
| SEC-089 | CI checkouts keep credentials (persist-credentials) | P4 | Confirmed | F-29 | — |
| SEC-090 | Release job installs npm tooling unlocked | P3 | Confirmed | F-28 | — |
| SEC-092 | Database image not digest-pinned | P3 | Confirmed | F-27 | — |
| SEC-093 | Secret files not ignored by git / docker | P3 | Fixed — Verified | F-19 | b7545c5 |
| SEC-095 | Business logic: decision on a quarterly figure as annual | P2 | Fixed — Verified | F-20 | 394ff28 |
| SEC-096 | Audit trail can be altered (append-only bypass) | P1 | Fixed — Verified | F-21 | b7545c5 |
| SEC-097 | Audit table rewritten with INSERT OR REPLACE (SQLite) | P3 | Confirmed | F-22 | — |
| SEC-098 | Migration downgrade drops audit_events triggers | P2 | Confirmed | F-31 | — |

## Full checklist

| ID | Issue type | Status | Evidence |
|---|---|---|---|
| SEC-001 | SQL injection (ORM queries and the f-string DDL helper, whose table names are constants) | Tested — Not Found | sast;agent:db;own:read maintenance.py |
| SEC-002 | Injection through saved searches and list filters | Tested — Not Found | agent:authz (read; parameters bound by the ORM) |
| SEC-003 | OS command injection (subprocess) | Tested — Not Found | sast;own:read backup.py (fixed argv, no shell) |
| SEC-004 | Path traversal in uploaded file names | Tested — Not Found | agent:ingest |
| SEC-005 | Path traversal through a backup manifest | Fixed — Verified | agent:network;agent:db;own:test_backup.py |
| SEC-006 | Zip-slip / tar-slip on restore | Not Applicable | na (no archive reader in src) |
| SEC-007 | Symlink following when adding a local file | Fixed — Verified | agent:ingest;own:test_cli.py |
| SEC-008 | Symlink following in backup restore | Fixed — Verified | agent:network;own:test_backup.py |
| SEC-009 | Insecure deserialisation (pickle, yaml.load) | Tested — Not Found | sast |
| SEC-010 | XML external entity processing | Not Applicable | na (XLSX is written, never parsed; bandit B406 is an escape helper) |
| SEC-011 | Stored XSS through document text in the HTML report | Tested — Not Found | exist:tests/test_report_html.py;exist:tests/test_redteam.py;agent:ingest (static) |
| SEC-012 | Reflected XSS in API error bodies | Tested — Not Found | agent:frontend;agent:auth |
| SEC-013 | DOM XSS in the web UI | Tested — Not Found | agent:frontend |
| SEC-014 | javascript: URLs from server data | Tested — Not Found | agent:frontend (React 19 neutralises them) |
| SEC-015 | Unvalidated server-supplied links navigate off-site | Confirmed | agent:frontend |
| SEC-016 | Cross-site request forgery on cookie sessions (missing, null, subdomain Origin) | Tested — Not Found | agent:auth;exist:test_signin.py |
| SEC-017 | CSRF check crashes on non-ASCII header | Fixed — Verified | agent:auth;own:test_audit_hardening.py |
| SEC-018 | CORS wildcard combined with credentials | Fixed — Verified | agent:auth;own:test_audit_hardening.py |
| SEC-019 | SSRF through webhook URL (decimal/hex/octal IPs, link-local, CGNAT, 0.0.0.0) | Tested — Not Found | agent:network |
| SEC-020 | SSRF through IPv4-mapped IPv6 (::ffff:127.0.0.1) | Tested — Not Found | agent:network |
| SEC-021 | SSRF through NAT64 / 6to4 / IPv4-compatible IPv6 | Fixed — Verified | agent:network;own:test_audit_hardening.py |
| SEC-022 | SSRF through DNS rebinding between check and connect | Tested — Not Found | agent:network (connection pinned to the checked IP) |
| SEC-023 | SSRF through redirects | Tested — Not Found | agent:network (webhook client); own:test (OIDC client) |
| SEC-024 | OIDC client follows redirects despite its documentation | Fixed — Verified | agent:network;own:test_audit_hardening.py |
| SEC-025 | SSRF through userinfo / trailing-dot / unicode host tricks | Tested — Not Found | agent:network |
| SEC-026 | Source fetcher opens file: / ftp: URLs | Fixed — Verified | agent:supply-chain;own:test_fetch.py |
| SEC-027 | Open redirect through next= after sign-in | Tested — Not Found | agent:auth;agent:frontend |
| SEC-028 | OIDC state reuse / fixation | Tested — Not Found | agent:auth;exist:test_signin.py |
| SEC-029 | OIDC nonce reuse / mismatch | Tested — Not Found | agent:auth;exist:test_oidc_signature.py |
| SEC-030 | OIDC PKCE downgrade | Tested — Not Found | agent:auth |
| SEC-031 | OIDC algorithm confusion (none, HS256 with the public key) | Tested — Not Found | agent:auth;exist:test_oidc_signature.py |
| SEC-032 | OIDC audience / issuer / expiry checks bypassed | Tested — Not Found | agent:auth |
| SEC-033 | OIDC token with NaN expiry accepted | Fixed — Verified | agent:auth;own:test_oidc_signature.py |
| SEC-034 | OIDC unverified email accepted | Tested — Not Found | agent:auth |
| SEC-035 | Email allow-list bypass with lookalike Unicode domain | Confirmed | agent:auth (Kelvin sign U+212A) |
| SEC-036 | Session fixation | Tested — Not Found | agent:auth |
| SEC-037 | Logout does not revoke the session | Tested — Not Found | agent:auth |
| SEC-038 | Session / token entropy too low | Tested — Not Found | agent:auth (secrets.token_urlsafe(32)) |
| SEC-039 | Secrets stored in plaintext (tokens, sessions, share links) | Tested — Not Found | agent:auth;agent:authz (SHA-256 only) |
| SEC-040 | Timing-unsafe secret comparison | Tested — Not Found | agent:auth |
| SEC-041 | Credential guessing is not throttled | Fixed — Verified | agent:auth;own:test_audit_hardening.py |
| SEC-042 | Account enumeration through response differences | Tested — Not Found | agent:auth |
| SEC-043 | Rate-limit bypass through X-Forwarded-For | Tested — Not Found | agent:auth |
| SEC-044 | Hard-coded credentials in source or history | Tested — Not Found | agent:supply-chain (tree and 105 commits scanned) |
| SEC-045 | Secrets in logs or error bodies | Tested — Not Found | agent:auth |
| SEC-046 | Empty API_KEYS silently disables API_KEYS_FILE | Fixed — Verified | agent:auth;own:test_audit_hardening.py |
| SEC-047 | Insecure defaults reach production | Tested — Not Found | agent:auth (production refuses to start unauthenticated) |
| SEC-048 | Cookie flags (HttpOnly, SameSite, Secure) | Tested — Not Found | agent:auth |
| SEC-049 | HSTS, CSP, nosniff, Referrer-Policy present | Tested — Not Found | exist:test_security_defaults.py;agent:frontend |
| SEC-050 | Static demo has no Content-Security-Policy | Confirmed | agent:frontend |
| SEC-051 | Cross-organisation read (IDOR) on cases, documents, reports; 404 identical to unknown id | Tested — Not Found | agent:authz;exist:test_tenant_isolation.py |
| SEC-052 | Cross-organisation write | Tested — Not Found | agent:authz;exist:test_tenant_isolation.py |
| SEC-053 | Mass assignment of org_id / role in request bodies | Tested — Not Found | agent:authz |
| SEC-054 | Viewer performs a write or admin action | Tested — Not Found | agent:authz (14 routes) |
| SEC-055 | Member escalates own role through POST /org/members | Fixed — Verified | agent:authz;own:test_accounts.py |
| SEC-056 | Sole admin leaves organisation with no admin | Fixed — Verified | agent:authz;own:test_accounts.py |
| SEC-057 | Non-owner admin removes or demotes the owner | Fixed — Verified | agent:authz;own:test_accounts.py |
| SEC-058 | Token minted with no expiry | Fixed — Verified | agent:authz;own:test_accounts.py |
| SEC-059 | Revoking a token leaves tokens it minted valid | Fixed — Verified | agent:authz;own:test_accounts.py;migration 0007 |
| SEC-060 | Share links keep serving after the organisation is deleted | Fixed — Verified | agent:authz;own:test_lifecycle.py |
| SEC-061 | Token of a suspended / removed user still works | Tested — Not Found | agent:authz;exist:test_accounts.py |
| SEC-062 | Invitation reuse or use by a different email | Tested — Not Found | agent:authz (service layer only) |
| SEC-063 | Four-eyes bypass (same person signs own report) | Tested — Not Found | agent:authz |
| SEC-064 | Sign-off reviewer name is free text and can impersonate | Confirmed | agent:authz |
| SEC-065 | Share-token enumeration or weak entropy | Tested — Not Found | agent:network |
| SEC-066 | Webhook HMAC construction, replay window, timing | Tested — Not Found | agent:network |
| SEC-067 | Webhook secret leaks through list or audit endpoints | Tested — Not Found | agent:network |
| SEC-068 | Webhook CRLF header injection | Tested — Not Found | agent:network |
| SEC-069 | Webhook port parsing crashes the API (500) | Fixed — Verified | agent:network;own:test_audit_hardening.py |
| SEC-070 | Slow-drip webhook receiver stalls the shared dispatcher | Fixed — Verified | agent:network;own:test_audit_hardening.py |
| SEC-071 | Unbounded webhook response read | Tested — Not Found | agent:network (read capped at 4096) |
| SEC-072 | S3 key traversal / injection | Tested — Not Found | agent:network |
| SEC-073 | S3 digest regex accepts a trailing newline | Fixed — Verified | agent:network;own:test_audit_hardening.py |
| SEC-074 | SigV4 signing mistakes | Tested — Not Found | agent:network (read only; no real S3) |
| SEC-075 | SMTP header injection through names or subjects | Tested — Not Found | agent:network (by reading) |
| SEC-076 | CSV / XLSX formula injection | Tested — Not Found | agent:network |
| SEC-077 | Export corrupts negative numbers ('-5) | Fixed — Verified | agent:network;own:test_audit_hardening.py |
| SEC-078 | Decompression bomb in an uploaded PDF | Fixed — Verified | agent:ingest;own:test_ingest_and_pipeline.py |
| SEC-079 | Quadratic regex (ReDoS) in unit detection | Fixed — Verified | agent:ingest;own:test_ingest_and_pipeline.py |
| SEC-080 | Encrypted, truncated, looping, deeply nested PDFs | Tested — Not Found | agent:ingest (measured) |
| SEC-081 | Huge page count / MediaBox | Tested — Not Found | agent:ingest (1500-page cap rejects in 0.49 s) |
| SEC-082 | Content-type spoofing | Tested — Not Found | agent:ingest (type comes from the bytes) |
| SEC-083 | CLI path has no page, size or time cap | Confirmed | agent:ingest (read, not run) |
| SEC-084 | Dependency with a known vulnerability (Python) | Tested — Not Found | sast (pip-audit, project venv: none) |
| SEC-085 | Dependency with a known vulnerability (npm) | Tested — Not Found | agent:supply-chain;agent:frontend (npm audit: 0) |
| SEC-086 | Typosquatted or abandoned dependency | Tested — Not Found | agent:supply-chain |
| SEC-087 | GitHub Actions: unpinned third-party actions | Tested — Not Found | agent:supply-chain |
| SEC-088 | GitHub Actions: pull_request_target / script injection | Tested — Not Found | agent:supply-chain |
| SEC-089 | CI checkouts keep credentials (persist-credentials) | Confirmed | agent:supply-chain (1 of 15 set) |
| SEC-090 | Release job installs npm tooling unlocked | Confirmed | agent:supply-chain |
| SEC-091 | Container runs as root / secrets in image | Tested — Not Found | agent:supply-chain (USER 10001, digest-pinned bases) |
| SEC-092 | Database image not digest-pinned | Confirmed | agent:supply-chain |
| SEC-093 | Secret files not ignored by git / docker | Fixed — Verified | agent:supply-chain;own:git check-ignore |
| SEC-094 | Offline guarantee broken by a network import in the reader | Tested — Not Found | exist:tests/test_offline.py;exist:tests/test_network_boundary.py;agent:supply-chain |
| SEC-095 | Business logic: decision on a quarterly figure as annual | Fixed — Verified | agent:logic;own:test_periods.py |
| SEC-096 | Audit trail can be altered (append-only bypass) | Fixed — Verified | agent:db;own:test_lifecycle.py |
| SEC-097 | Audit table rewritten with INSERT OR REPLACE (SQLite) | Confirmed | agent:db |
| SEC-098 | Migration downgrade drops audit_events triggers | Confirmed | agent:db |
| SEC-099 | Weak cryptographic primitives (random, md5, sha1) in security code | Tested — Not Found | sast |
| SEC-100 | TLS verification disabled | Tested — Not Found | sast (no verify=False) |
