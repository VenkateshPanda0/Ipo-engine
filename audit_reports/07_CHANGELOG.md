# Changelog of the audit branch

Branch `audit/remediation-2026-11`, from `f970795` (the state of `main` when the audit began; `main` was not touched). 49 files changed, 1,034 insertions, 58 deletions outside `audit_reports/`. Every product-code change below is paired with a regression test; see `10_FINAL_VERIFICATION.md` for the verification record.

| File | Issue | What changed and why | Verification |
|---|---|---|---|
| `.dockerignore` | F-19 | Keep env files, keys, backups and secrets out of the image build context | git check-ignore / read |
| `.gitignore` | F-19 | Ignore .env.*, credentials, keys, backups and dumps | git check-ignore confirms the names listed in the finding are now ignored |
| `deploy/compose.accounts.yaml` | F-41 | Disable the inherited API healthcheck on the worker service | Edited only; Docker was not available, so not run (Fixed — Verification Pending) |
| `docs/RELEASING.md` | F-43 | State that the release workflow already builds the web image | release.yml checked for the web image job |
| `docs/security.md` | F-43 | Describe the optional network code accurately (D-068, D-069) | read against tests/test_network_boundary.py |
| `frontend/src/pages/organisation.tsx` | F-42 | Remove a render-time timestamp that caused a hydration mismatch | Production build + Chromium probe: 0 hydration errors; vitest 49/49; tsc clean |
| `pyproject.toml` | - | Ruff skips audit_reports/raw (the audit's own data and builder scripts) | ruff clean |
| `src/ipo_engine/checks/related_party.py` | F-02 | Lookbehind makes figure counting linear | test_a_long_run_of_digits...; 0.99 s -> 0.000 s on 20,000 digits |
| `src/ipo_engine/extract/periods.py` | F-20 | Abstain on part-year labels; own length for odd periods; end of a from-to range | tests/test_periods.py (red on baseline source, green now) |
| `src/ipo_engine/flags/engine.py` | F-37 | Percent wording tells breach from limit apart; persistent_below needs consecutive years | tests/test_flags.py (red on baseline source) |
| `src/ipo_engine/ingest/fetch.py` | F-16 | Allow http/https sources only | tests/test_fetch.py (5 cases, red on baseline source) |
| `src/ipo_engine/ingest/local.py` | F-17 | Refuse a symlink destination | tests/test_cli.py (red on baseline source) |
| `src/ipo_engine/parse/units.py` | F-36 | Abstain on foreign currency and on two different units | tests/test_units.py (6 cases red on baseline source) |
| `src/ipo_engine/screening/api/middleware.py` | F-24 | Request-id regex anchored with \Z | test_security_defaults.py |
| `src/ipo_engine/screening/api/routers/accounts.py` | F-03, F-04, F-05, F-06 | Owner protection, own-role guard on add, mandatory token lifetime, parent token on mint | test_accounts.py (3 red-before tests + 2 token tests) |
| `src/ipo_engine/screening/core/config.py` | F-13, F-14 | Refuse CORS *; empty value is not a choice for *_FILE secrets | test_audit_hardening.py |
| `src/ipo_engine/screening/core/security.py` | F-11, F-12 | Throttle failed credentials; safe_equals for non-ASCII | test_audit_hardening.py |
| `src/ipo_engine/screening/db/maintenance.py` | F-21 | Open the transaction before the trigger DDL | test_lifecycle.py: triggers 8 -> 2 on baseline, 8 -> 8 now |
| `src/ipo_engine/screening/db/migrations/versions/0007_token_parent.py` | F-06 | Add api_tokens.parent_token_id (nullable, indexed); reversible | migration chain exercised by the whole suite |
| `src/ipo_engine/screening/db/models.py` | F-06 | Model column for parent_token_id | suite |
| `src/ipo_engine/screening/intelligence/ingest.py` | F-01 | Count decoded size of deflate streams (128 MB each, 2 GB total) | two tests red on baseline source; bomb refused in 0.14 s |
| `src/ipo_engine/screening/intelligence/numbers.py` | F-02 | Lookbehind makes the amount-phrase regex linear | detect_unit on 20,000 digits: 22.78 s -> 0.005 s |
| `src/ipo_engine/screening/network/http.py` | F-24 | No-redirect opener for the OIDC client | test_audit_hardening.py |
| `src/ipo_engine/screening/network/oidc.py` | F-23 | Reject non-finite exp; compare nonce as bytes | test_oidc_signature.py |
| `src/ipo_engine/screening/network/s3.py` | F-15 | fullmatch with \Z for the digest | test_audit_hardening.py |
| `src/ipo_engine/screening/network/webhook_http.py` | F-08, F-09 | Refuse transitional IPv6, bad ports; whole-exchange timer | test_audit_hardening.py incl. a real slow-drip server |
| `src/ipo_engine/screening/services/accounts.py` | F-03, F-04, F-06, F-32 | Last-admin guard in the service; token parent and cascade revoke; savepoint on user create | test_accounts.py, test_concurrency_and_properties.py |
| `src/ipo_engine/screening/services/backup.py` | F-10 | Strict manifest: safe names, no links, no unlisted files; restore only listed files | test_backup.py (2 new tests) |
| `src/ipo_engine/screening/services/documents.py` | F-35 | RateLimiter forgets idle keys | test_rate_limiter_memory.py |
| `src/ipo_engine/screening/services/lifecycle.py` | F-07 | Revoke the organisation's share links on delete | test_lifecycle.py |
| `src/ipo_engine/screening/services/shares.py` | F-07 | open() refuses a switched-off organisation | test_lifecycle.py |
| `src/ipo_engine/screening/services/signin.py` | F-12 | safe_equals for OAuth state | test_audit_hardening.py |
| `src/ipo_engine/screening/services/tabular.py` | F-15 | Real numbers are not prefixed by the formula guard | test_audit_hardening.py |
| `src/ipo_engine/screening/services/webhooks.py` | F-15 | Signature compare on bytes | test_audit_hardening.py |

Tests added or changed (each pairs with the issues above):

- `tests/screening/integration/api/test_accounts.py`
- `tests/screening/integration/api/test_lifecycle.py`
- `tests/screening/integration/api/test_oidc_signature.py`
- `tests/screening/integration/api/test_security_defaults.py`
- `tests/screening/integration/test_backup.py`
- `tests/screening/stress/test_concurrency_and_properties.py`
- `tests/screening/unit/intelligence/test_ingest_and_pipeline.py`
- `tests/screening/unit/test_audit_hardening.py`
- `tests/screening/unit/test_rate_limiter_memory.py`
- `tests/test_cli.py`
- `tests/test_docs.py`
- `tests/test_fetch.py`
- `tests/test_flags.py`
- `tests/test_periods.py`
- `tests/test_units.py`

## Commits

```
a887418 audit: reports so far, checklist data, ruff skips the audit's own scripts; the digit-run test now covers the slow case
32a3179 fix: refuse redirects in the OIDC client, NaN token expiry, request-id trailing newline; docs match the network code
5cb0cd5 fix(frontend): drop a render-time timestamp that caused a hydration mismatch on /organisation
011b9de fix: a breach is never printed equal to its limit; persistent-below needs consecutive fiscal years
64b8ba6 fix: webhook port and IPv6 transitional targets, total delivery deadline, throttled failed credentials, no wildcard CORS, numbers stay numbers in exports, non-ASCII credential comparisons
f23ac18 fix: backups reject unlisted, outside and linked files; rate limiter forgets idle keys; concurrent first sign-ins share one user
394ff28 fix: abstain on quarter labels, foreign currencies and mixed units; keep 15-month periods and from-to ranges honest
4ee4603 fix: refuse deflate bombs by decoded size; linear unit and figure regexes; local add refuses a symlink target
64fdb6d fix: owner and last-admin guards on member changes; tokens always expire and are revoked with their parent; a deleted organisation's share links stop working
b7545c5 fix: erase keeps the append-only triggers on failure; fetcher refuses non-http(s) sources; ignore more secret files; worker has no API healthcheck
b489246 audit: full baseline test run with coverage (1212 passed, 93% lines)
e160fa2 audit: baseline scan outputs (bandit, load test, pytest) as a checkpoint
```
