# Running the web app for several organisations

This is the operator's guide to **accounts mode**: people sign in, belong to organisations, and see only
their own organisation's cases. It is off by default. With it off, the app behaves exactly as before
(one local user, or the keys in `API_KEYS`), and the reader on the command line is unaffected.

The reasoning and the one change to the charter's offline rule are in `decisions.md` D-068. Every route
is listed in [API.md](API.md).

## The three ways to run it

| Mode | Set | Who can do what |
|---|---|---|
| Local | nothing | one admin, `local-user`; development only (production refuses to start this way) |
| Key file | `API_KEYS="ann\|reviewer\|<key or sha256=…>,…"` | fixed users and roles from the environment; all in one organisation |
| Accounts | `ACCOUNTS_ENABLED=true` | people, organisations, per-organisation roles, sessions, tokens |

In accounts mode a request with no valid credential is refused (there is no local admin), the old
unversioned routes (`/screen`, `/reports`, `/reviews`) are not served, and keys in `API_KEYS` still work
as members of the default organisation.

## First start

```bash
export ACCOUNTS_ENABLED=true DATABASE_URL=postgresql://user:pass@host/db   # or leave the SQLite default
ipo accounts create-org "Acme Capital"                       # prints the organisation id
ipo accounts add-member <org-id> you@acme.com --role admin   # the first admin (owner)
ipo accounts create-token <org-id> you@acme.com --name first # prints a token, once
```

Use the token as `Authorization: Bearer ipo_…`, or set up Google sign-in and use the web app. From
there an admin invites everyone else.

## Sign-in with Google (optional)

1. In the Google Cloud console create an **OAuth client ID** of type *Web application*.
2. Add the authorised redirect URI `<PUBLIC_BASE_URL>/api/v1/auth/callback/google`.
3. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` and `PUBLIC_BASE_URL` (the address people type).

The flow is authorization code with PKCE, a single-use state bound to the browser, a nonce, the ID token's
RS256 signature checked against the provider's published keys, and checks of issuer, audience, expiry and a
verified email. Any OpenID Connect provider works if you set `OIDC_ISSUER`.

| Setting | Default | Meaning |
|---|---|---|
| `SIGNUP_MODE` | `invite` | `invite`: only invited or already-added people can sign in. `open`: anyone with a verified address gets an account and an organisation of their own |
| `ALLOWED_EMAIL_DOMAINS` | empty | comma list, e.g. `acme.com`; empty allows any |
| `OIDC_VERIFY_SIGNATURE` | true | check the ID token's signature against the provider's keys; turn off only for a provider that publishes none |
| `SESSION_DAYS`, `SESSION_IDLE_HOURS` | 14, 72 | absolute and idle session limits |
| `INVITATION_DAYS` | 7 | how long an invitation link lives |
| `TRUST_HTTPS` | false | set behind a TLS-terminating proxy: Secure cookies and HSTS (always on in production) |

Cookie sessions are HttpOnly, SameSite=Lax, stored only as a hash; every change made with a cookie needs the
session's `X-CSRF-Token` (get it from `GET /api/v1/auth/csrf`) and an allowed `Origin`. Serve the web app and
the API on the same site (a reverse proxy or the Next.js rewrite), or list the web origin in `CORS_ORIGINS`.

## Roles and what separates organisations

Roles, per organisation: viewer (read), analyst (create cases, upload, screen, comment, assign),
reviewer (resolve review items, sign off, share links, members list), admin (members, tokens of others,
settings, webhooks, export, erase). An organisation always keeps at least one admin; only an owner can delete it.

Separation is enforced in one place: a check before every route that takes an id answers **404** for an
id owned by another organisation, exactly as for an id that does not exist, and the list queries filter by
the caller's organisation. A test reads every `/api/v1` route from the OpenAPI schema, calls each with another
organisation's ids and demands 404; another test breaks the check on purpose and demands the walker notice.
A new route with an id nobody wrote a rule for fails that test.

## Tokens, invitations, kill switch

* **Personal tokens** (`ipo_…`): shown once, stored as a SHA-256, 90 days by default, revocable, never above
  the owner's current role. Removing a member or suspending the account ends their tokens and sessions at once.
* **Invitations**: an admin creates one (`POST /api/v1/org/invitations`) and sends the returned link; it is
  bound to the invited address, expires, can be revoked, and works once. The app does not send e-mail.
* **Suspend**: `ipo accounts suspend <email>` blocks a person everywhere; `reinstate` undoes it.

## Several processes, and PostgreSQL

* `DATABASE_URL=postgresql://…` (install the `postgres` extra; the container image has it). The database
  must be UTF-8. The whole test suite runs against PostgreSQL 16 in CI.
* `JOB_MODE=queue`: uploaded documents wait in the database; any process claims them (`ipo worker`, or the API
  with `WORKER_THREADS>0`). A worker that dies loses its lease after `JOB_LEASE_SECONDS`; a job is failed after
  `JOB_MAX_ATTEMPTS`. Run API processes with `WORKER_THREADS=0` and workers separately to scale independently.
* `RATE_LIMIT_STORE=database` makes the upload limit one limit across processes; `API_RATE_LIMIT_PER_MINUTE`
  limits each signed-in user's requests (429 with `Retry-After`).

## Webhooks

Set `WEBHOOK_SIGNING_KEY` (a long random string; keep it like any secret). An admin then registers endpoints
(`POST /api/v1/webhooks`). Each delivery is a JSON POST with `X-IPO-Event`, `X-IPO-Delivery` and
`X-IPO-Signature: t=<unix>,v1=<hex>` where `v1` is HMAC-SHA256 of `"<t>.<raw body>"` with the endpoint's secret
(returned once at creation and on rotation). Reject a signature older than five minutes. Payloads carry
identifiers and names, never extracted figures. Targets must be public https addresses (checked again at send
time, connection pinned, no redirects); `ALLOW_PRIVATE_WEBHOOK_TARGETS=true` relaxes that for development only.

## Data: export, erase, back up

* `GET /api/v1/org/export` (admin): a zip of JSON for the organisation (`?include_files=true` adds the PDFs).
* `GET /api/v1/me/export`: what is held about the signed-in person, without secrets.
* `DELETE /api/v1/cases/{id}?confirm=<exact name>` (admin): permanent erasure of a case, its history and its
  stored PDF (kept if another case holds the identical file). The audit trail keeps an identifier-only record.
* `DELETE /api/v1/org?confirm=<exact name>` (owner) switches an organisation off; `ipo accounts purge-org <id>`
  erases it after your grace period.
* `ipo backup create --out DIR` writes a verified backup (database, PDFs, checksums); `ipo backup verify DIR`;
  `ipo backup restore DIR [--force]`. Test a restore before you need one.

## What this does not do

It does not take payment, host the app, or watch it for you (it exposes metrics and alert rules, see
[OPERATIONS.md](OPERATIONS.md)); it sends e-mail only for invitations and only if you configure SMTP; it has no
password login or multi-factor step of its own (use Google, which has one, or tokens). Those, and legal
documents, are for the operator.
