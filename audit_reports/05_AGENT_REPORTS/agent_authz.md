# Agent report: authorization / tenant isolation (agent_authz)

Branch: audit/remediation-2026-11. No tracked file modified, nothing committed. Exploit script: /tmp/agent_authz/exploit.py
(run: `. .venv/bin/activate && python /tmp/agent_authz/exploit.py`; builds two orgs via tests' `build_world`, real HTTP via TestClient, accounts mode, SQLite).

## Scope
Routers api/routers/{accounts,auth,v1,share,reports,reviews,screen,rules}.py, api/scope.py, api/dependencies.py, core/security.py,
services/{accounts,collab,shares,sessions,signin,tenancy,webhooks,lifecycle,cases,review_service}.py.

## Method
Read the code, then ran requests/service calls in one script (RESULT = observed behaviour). "Confirmed" = reproduced. Items marked (code-read) were
not exercised at runtime.

## Checks executed
| # | Check | Result |
|---|-------|--------|
| 1 | Org B token GET org A case/document/report/case-data vs a nonexistent id (status and body shape) | Not Found (both 404, identical) |
| 2 | Mass assignment: `org_id` in POST /cases body | Not Found (ignored; case lands in caller's org) |
| 3 | Viewer calling 14 write/admin routes (cases, comments, screening, resolve, share, sign-off, members, settings, erase, members list, usage, webhooks, org export) | Not Found (all refused) |
| 4 | Viewer mints admin token | Not Found (refused) |
| 5 | Cross-org PATCH /org/members/{user_id} | Not Found (404) |
| 6 | Removed owner's token / org-deleted tokens still valid | Not Found (401, correctly revoked) |
| 7 | Suspended user's token still valid | Not Found (401) |
| 8 | Invitation accepted by a different email; accepted invitation reused by a third person; unverified email sign-in | Not Found (all refused by `AccountService.sign_in`) |
| 9 | Four-eyes: report creator signs off own report (v1 sign-off) | Not Found (409) |
| 10 | Path-id scoping design (api/scope.py, tenancy.py), webhook/share/comment/token/filter services (code-read) | Not Found: every service filters by org_id; ids normalised so raw-string mismatch fails closed |
| 11 | Legacy /reports, /reviews, /screen unscoped routes | Not Found in accounts mode: main.py:~90 does not mount them when accounts_enabled (code-read) |
| 12 | Cross-org document dedupe leak (code-read) | Not Found: duplicate lookup is per case_id (documents.py ~309) |
| 13 | Sole admin lowers own role / org left without admin via POST /org/members | CONFIRMED (F1) |
| 14 | Non-owner admin removes owner | CONFIRMED (F2) |
| 15 | Token with `days: null` | CONFIRMED (F3) |
| 16 | Token minted by a token survives parent's revocation | CONFIRMED (F4) |
| 17 | Public share link after organisation deletion | CONFIRMED (F5) |
| 18 | `reviewer_name` in sign-off bound to caller identity | CONFIRMED not bound (F6) |

## Confirmed findings

### F1 (P3) Last-admin and self-demotion guards bypassed through POST /org/members
- api/routers/accounts.py:306 (add_member route) -> services/accounts.py:174 (add_member upserts role, no guard). Guards exist only in change_role (accounts.py:316, "cannot lower your own role") and remove_member (services/accounts.py:221, "keep one admin").
- Repro: sole admin of org B: `POST /api/v1/org/members {"email":"<own email>","role":"viewer"}` -> 201 role viewer; next `GET /api/v1/org/members` -> 403. Org now has zero admins, nobody can administer or delete it without operator DB access. Also reachable by any stolen admin token.
- Fix: move the "keep at least one admin / do not lower own role" check into AccountService.add_member (and change_role path) so every role change goes through one function; make the count check atomic (same transaction, SELECT ... FOR UPDATE on Postgres).

### F2 (P3) Ownership not protected: any admin can remove or demote the owner
- services/accounts.py:221 (remove_member) and :174 (add_member keeps is_owner but lowers role) have no is_owner check; routers accounts.py:331/316 require only admin.
- Repro: org with owner ann and non-owner admin adm2 (is_owner cleared): `DELETE /api/v1/org/members/<ann>` with adm2's token -> 204; ann's token then 401. There is no ownership transfer API, so the org's only holder of `DELETE /org` (accounts.py:90, is_owner) can be removed by a peer.
- Fix: refuse removal/demotion of an owner by a non-owner; add an explicit transfer-ownership operation.

### F3 (P4) API tokens can be created with no expiry
- api/routers/accounts.py:56 (`days: int | None`), services/accounts.py:323 (`if days else None`).
- Repro: `POST /api/v1/tokens {"name":"never","days":null}` -> 201, `expires_at: null`. Bypasses the documented 1..3650-day bound.
- Fix: make `days` non-nullable (or require an admin-set org policy for non-expiring tokens).

### F4 (P3) Token can mint further tokens that outlive it (persistence after revocation)
- api/routers/accounts.py:349 (create_token only needs get_principal + _need_user; no `auth != "token"` restriction).
- Repro: owner mints token P; `POST /tokens` with P -> child K; `DELETE /tokens/<P>`; P -> 401, K -> 200 on GET /api/v1/org. A leaked token therefore cannot be cleaned up by revoking it alone; revocation of tokens is also not available to admins for other users (only via member removal).
- Fix: allow token creation only from interactive sessions (like switch-org), or record `parent_token_id` and revoke children transitively; add an admin "revoke member's tokens" endpoint.

### F5 (P2/P3) Public share links keep serving reports after the organisation is deleted
- services/shares.py:92 (`open`) checks only revoked/expired; api/routers/share.py. lifecycle.delete_org (services/lifecycle.py:316) revokes sessions and tokens but not ShareLinkRow, and the module docstring promises the organisation "stops working immediately".
- Repro: create share link for a report, `DELETE /api/v1/org?confirm=<name>` (204), tokens -> 401, but `GET /api/v1/shared/<token>` still -> 200 with the full report HTML, for up to 90 days / until purge. Same applies to links made by removed or suspended users (code-read, not run).
- Fix: in ShareService.open join case -> organisation and require deleted_at IS NULL and status active; revoke the org's links in delete_org.

### F6 (P4) Sign-off identity (`reviewer_name`) is free text, not tied to the signer
- api/routers/v1.py:128 and :772 (sign_off passes body.reviewer_name to complete_review; actor is stored only in history).
- Repro: adm2 signs a report with `"reviewer_name":"Someone Else Entirely"` -> 200 and the record shows that name. A reviewer can attribute a regulatory sign-off to another person.
- Fix: derive the displayed name from the authenticated user (name/email), keep the field optional or validate it equals the user.

## Observations (code-read, not reproduced)
- Four-eyes is advisory: an admin can set `four_eyes` false, sign, set true again (PATCH /org/settings; only audit-logged). Also check-then-save race in complete_review (review_service.py) between concurrent sign-offs; concurrent mutual demotion of two admins could also leave zero admins (check is not atomic).
- /exports/reports loads up to 5000 rows and /exports/cases up to 10000 for any viewer; GET /documents is unpaginated. Resource-abuse only, same-org data.
- Invitation e-mail has no per-org or per-admin send limit; with SIGNUP_MODE=open any new user is admin of own org and can send invitations carrying an attacker-chosen org name (mail abuse, P4; mailer.py).
- An invitation to an org deleted before acceptance still makes `sign_in` prefer that org id for the session (accounts.py `preferred = invite.org_id`); the session is then unusable (availability only, code-read).

## Limitations / untested
No OIDC callback or cookie-session/CSRF path run (service-level sign_in only); no Postgres run; no concurrency/race execution; webhook SSRF and file-upload issues out of scope; API-key (configured keys, default org) principals not exercised beyond code-read; HTTP-level invitation endpoints not called (service calls only); org settings/four-eyes cross-user race not run.
