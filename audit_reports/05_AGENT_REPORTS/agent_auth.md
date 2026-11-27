# Agent report: authentication, sessions, CSRF, CORS, crypto, secrets

Branch audit/remediation-2026-11. Tester: independent auth agent. No tracked file modified, nothing committed.
Probe scripts (not in repo): /tmp/agent_auth/probe1.py, probe2.py, probe3.py.

## Scope
src/ipo_engine/screening: core/security.py, core/config.py, services/{accounts,sessions,signin}.py,
network/oidc.py, network/http.py, api/routers/auth.py, api/middleware.py, api/dependencies.py, main.py (CORS),
core/logging.py, Dockerfile (uvicorn flags). Not reviewed in depth: share.py links, webhooks, mailer/SMTP, frontend.

## Method
Read all files above, then ran probes through FastAPI TestClient using the repo's own `Site` fixture and `FakeIdp`
(tests/screening/integration/api). IdP-signed tokens with hostile claims were produced via `FakeIdp.override/header`.
Everything marked Confirmed was executed and observed; "by reading" is stated explicitly.

## Checks and results

| Check | Result |
|---|---|
| CSRF: missing token / empty / wrong token (cookie session) | Not Found (all 403) |
| CSRF: Origin null, evil, subdomain, suffix (`localhost:3000.evil.com`), https-vs-http | Not Found (all 403) |
| CSRF: Origin absent | By design: allowed only with a valid token (200 with token). Not Found as a bypass |
| CSRF: text/plain body, no header, evil origin | Not Found (403) |
| CSRF: cookie + junk `Authorization` / empty `Authorization` | Not Found (401 / 403, CSRF still enforced for empty header) |
| CSRF: non-ASCII `X-CSRF-Token` | Confirmed (500), finding F1 |
| CSRF compare timing | Not Found (`hmac.compare_digest`, security.py:213) |
| Logout revokes session | Not Found: replay of old cookie after logout gives 401 |
| Session fixation (pre-set cookie before sign-in) | Not Found: attacker value gets 401 after login; server issues a new random token |
| Session token entropy / storage | Not Found: `token_urlsafe(32)`, only SHA-256 stored (by reading, sessions.py:44,50) |
| OAuth state replay | Not Found: second callback refused (state row deleted, cookie cleared) |
| State used in a different browser (login CSRF) | Not Found: refused, "not started in this browser" |
| PKCE S256 / nonce / state hashed at rest | Not Found (existing test plus reading) |
| `next=` open redirect: `//x`, `/\x`, `/\t/x`, `https://x`, `///x`, `javascript:`, control chars, `/@evil.com`, `/%2F/evil.com`, `/..//evil.com` | Not Found: all land on PUBLIC_BASE_URL host (signin.py `safe_next` plus base concatenation) |
| OIDC alg none / HS256 / empty signature / unknown kid | Not Found (all refused) |
| OIDC wrong aud / aud list without azp / wrong iss / expired / bad nonce | Not Found (all refused) |
| OIDC email_verified false, "false", null | Not Found (refused) |
| OIDC exp = NaN | Confirmed, F4 (needs a validly signed token) |
| OIDC non-ASCII nonce claim | Confirmed 500, F4 (needs a validly signed token) |
| Domain allow-list: case, `+tag`, `korp.com.evil.com`, `evil.korp.com`, zero-width suffix | Not Found (suffix variants refused, case/plus accepted as expected) |
| Domain allow-list: Unicode Kelvin sign (U+212A) in domain | Confirmed, F5 |
| Non-ASCII state / cookie on callback | Confirmed 500, F1 |
| CORS wildcard with credentials | Confirmed as config footgun, F3 |
| Cookie flags | Verified: HttpOnly, SameSite=Lax, Path=/. Secure not set in development, set by reading when production or TRUST_HTTPS (config.py cookie_secure). Not Found |
| HSTS / CSP / nosniff / no-store / Referrer-Policy in production + TRUST_HTTPS | Not Found (all present), /docs 404 in production |
| Production start with no keys | Not Found (InsecureConfiguration raised) |
| Rate limit bypass via X-Forwarded-For | Not Found (headers ignored; limits keyed on user / `client.host`) |
| Throttling of failed credentials | Confirmed, F2 (60 wrong keys: 60x 401, no 429) |
| Account enumeration | Not Found: tokens/sessions/suspended all return the same 401; invitation preview uniform 404. Sign-in errors (no invitation, suspended, domain) are only shown to someone holding a provider-verified email |
| Secrets in logs | Not Found for session token and CSRF token in app logs during a full sign-in. Request log records path only, not query string. By reading: uvicorn's default access log (Dockerfile CMD) would log callback `code` and `state` query values (Inconclusive, not run) |
| Error bodies | Not Found: no traces, SQL or paths in 500 bodies; trace is logged server-side only |
| X-Request-ID header injection | Confirmed minor, F6 |
| `*_FILE` secrets | Confirmed, F7 |
| Token / invitation entropy and hashing | Not Found by reading (`token_urlsafe(32)`, SHA-256 at rest, expiry, revoke, role clamp to member role) |
| Timing-unsafe comparisons | Not Found: API keys compared via digest and `compare_digest` against every entry; DB lookups by hash |
| Password-less accounts | Not Applicable: no password auth exists, sign-in is OIDC only |

## Confirmed findings

### F1. Non-ASCII value in CSRF header or OAuth state/cookie causes unhandled TypeError (HTTP 500)
- Where: core/security.py:213 `hmac.compare_digest(sent, csrf)`; services/signin.py:96 (file line of `secrets.compare_digest(bound_state, state)`, shown as 322 in a concatenated read).
- Root cause: `compare_digest` on `str` raises TypeError if either argument has non-ASCII characters; neither call is guarded.
- Reproduction (session):
  1. Sign in with the test `Site` fixture, then `POST /api/v1/auth/sessions/revoke-others` with headers `X-CSRF-Token: <byte 0xE9>` and `Origin: http://localhost:3000`. Result: 500 `INTERNAL_ERROR`, log shows `TypeError: comparing strings with non-ASCII characters`.
  2. Unauthenticated: `GET /api/v1/auth/callback/google?code=x&state=%C3%A9` with `Cookie: ipo_oauth_state=<bytes c3 a9>`. Result: 500.
- Impact: not an auth bypass (fails closed). Unauthenticated callers can generate error-level log entries with stack traces and 500s at will, which pollutes alerting. The callback route has no `_limit_public`.
- Severity: P4 (P3 if 5xx alerting pages someone).
- Fix: compare bytes (`sent.encode()` vs `csrf.encode()`) or catch TypeError and return 403; same for state. Add rate limit on the callback.

### F2. No throttling of failed credentials
- Where: core/security.py:166-190. `_rate_limit` runs only after `resolve_principal` succeeds; failures raise first. API_RATE_LIMIT_PER_MINUTE is also 0 (off) by default (config.py:149).
- Reproduction: API_KEYS configured, API_RATE_LIMIT_PER_MINUTE=5, send 60 requests with wrong Bearer values to `/api/v1/me`. Result: all 60 are 401, none 429. Valid-key requests do hit 429 after 5.
- Impact: unlimited online guessing of operator-chosen API_KEYS. Personal tokens and sessions have 256-bit entropy so guessing is infeasible; weak hand-written API_KEYS are the risk.
- Severity: P3.
- Fix: count failures per `client.host` (with an explicit trusted-proxy setting) before returning 401; document that API keys must be at least 32 random bytes and refuse short plaintext keys at startup.

### F3. CORS_ORIGINS=`*` with credentials reflects any origin
- Where: main.py:77-84 (`allow_credentials=True` with `allow_origins=settings.cors_origins`); config.py:58 has no validation.
- Reproduction: `CORS_ORIGINS=*`, request with `Origin: https://evil.example` and any Cookie header. Response: `Access-Control-Allow-Origin: https://evil.example`, `Access-Control-Allow-Credentials: true`; preflight 200. With a specific origin list, evil origin gets no ACAO header.
- Mitigations observed: state-changing cookie requests still fail CSRF with evil Origin (403) and cookies are SameSite=Lax, so exploitation is limited to same-site attackers reading GET responses. Default config is safe.
- Severity: P3 (misconfiguration trap).
- Fix: reject `*` in `Settings` validation when credentials are on (or in production).

### F4. OIDC claim handling accepts NaN `exp` and 500s on non-ASCII nonce
- Where: network/oidc.py:221 (`exp + LEEWAY_S < now` is False for NaN, so a token with `exp: NaN` is accepted); network/oidc.py:226 (`hmac.compare_digest(presented, nonce)` TypeError on non-ASCII claim).
- Reproduction: `FakeIdp.override = {"exp": float("nan")}` then sign-in: succeeds. `{"nonce": "é"}`: 500.
- Impact: requires a token validly signed by the configured IdP (or OIDC_VERIFY_SIGNATURE=false, config.py:87), so defense in depth only.
- Severity: P4.
- Fix: require `math.isfinite(exp)`; compare nonce as bytes.

### F5. Unicode case folding lets a look-alike domain pass the allow-list and merge into an ASCII account
- Where: services/accounts.py:55-59 `normalise_email` (`.lower()` then regex accepts any non-space characters), services/signin.py:117 allow-list check using `.lower()`.
- Reproduction: ALLOWED_EMAIL_DOMAINS=korp.com, SIGNUP_MODE=open, IdP asserts verified email `a@Korp.com` (Kelvin sign). Sign-in succeeds, `normalise_email` yields `a@korp.com`, and it resolves to the same user as `a@korp.com`.
- Impact: only exploitable if the IdP issues verified addresses at a non-ASCII domain; Google does not normally do this. Hardening.
- Severity: P4.
- Fix: reject non-ASCII email domains (or IDNA-encode and compare), and use the `hd` claim (parsed at oidc.py:234 but never used) for Google Workspace allow-lists.

### F6. X-Request-ID regex accepts a trailing newline
- Where: api/middleware.py:68, 172 (`re.match` with `$`).
- Reproduction: `X-Request-ID: ok\n` is reflected unchanged as `X-Request-ID: ok\n` in the response (TestClient). Values with embedded CRLF are correctly replaced.
- Impact: Not exploitable over a real HTTP/1.1 connection by reading (parsers split on LF); I did not test against uvicorn.
- Severity: P4.
- Fix: use `fullmatch`.

### F7. An empty `API_KEYS` env var silently disables `API_KEYS_FILE`
- Where: core/config.py:42 (`name in os.environ` skips the file even when the value is empty).
- Reproduction: `API_KEYS_FILE=<file with a key>` and `API_KEYS=""` gives `api_keys=''`, `auth_enabled=False`. In development this means every caller is the local admin; in production startup is refused unless ALLOW_UNAUTHENTICATED is set. Other behavior verified: env wins over file, missing file is a startup error, dotenv value wins over `_FILE`.
- Common trigger: compose `API_KEYS=${API_KEYS:-}` next to a secret file.
- Severity: P3 (fail-open in non-production, silent).
- Fix: treat empty env value as unset, and log a warning when both are present.

## Observations (not confirmed vulnerabilities)
- Public limiter (routers/auth.py:35, `RateLimiter(30)` in dependencies.py:457) is in-memory and keyed on `request.client.host`. The Dockerfile runs uvicorn with default forwarded-allow-ips, so behind a proxy in another container all users share one bucket. By reading, not tested.
- PUBLIC_BASE_URL defaults to `http://localhost:3000` even with APP_ENV=production (config.py:88); no startup check. Misconfiguration would break the redirect URI rather than leak anything.
- Cookie names lack the `__Host-` prefix. A sibling-subdomain attacker could plant `ipo_oauth_state` for login CSRF (theoretical, not tested).
- Suspended-user, removed-member, expired and idle session paths were reviewed by reading (sessions.py:92-106) and look correct; not re-executed here.

## Limitations
No external network; real Google behavior not tested. TestClient does not exercise real HTTP parsing. Share-link, webhook and SMTP code paths, tenant isolation and the frontend were out of scope. Effort capped at about 40 tool calls, so unusual `Authorization` forms and PostgreSQL-specific behavior are unverified.
