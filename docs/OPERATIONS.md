# Operating IPO Engine for several organisations

For the person who runs the service. What the accounts features are is in [ACCOUNTS.md](ACCOUNTS.md); this
page is what to do to run them: deploy, secure, upgrade, back up, watch, and respond. Nothing here needs a
cloud service; where one helps (a database host, object storage, e-mail, monitoring) it is optional and
named.

## 1. Deploy

`deploy/compose.accounts.yaml` is a working layout on one machine: PostgreSQL, the API (requests only), one
or more document workers, and the web app. Read its header, then:

```bash
cp deploy/env.example deploy/.env        # set PUBLIC_BASE_URL and PUBLIC_API_URL
mkdir -p deploy/secrets
openssl rand -hex 24 > deploy/secrets/postgres_password
printf 'postgresql://ipo:%s@postgres/ipo' "$(cat deploy/secrets/postgres_password)" > deploy/secrets/database_url
openssl rand -hex 32 > deploy/secrets/webhook_signing_key
: > deploy/secrets/google_client_secret   # or the real secret (and GOOGLE_CLIENT_ID in .env)
docker compose -f deploy/compose.accounts.yaml --env-file deploy/.env up --build -d
docker compose -f deploy/compose.accounts.yaml exec api ipo accounts create-org "Your company"
docker compose -f deploy/compose.accounts.yaml exec api ipo accounts add-member <org-id> you@company.com --role admin
```

Secrets are files, read through `NAME_FILE` variables (`DATABASE_URL_FILE`, `GOOGLE_CLIENT_SECRET_FILE`,
`WEBHOOK_SIGNING_KEY_FILE`, `S3_SECRET_ACCESS_KEY_FILE`, `SMTP_PASSWORD_FILE`, `API_KEYS_FILE`), so they are not in
the environment. A value set directly wins over its file.

**In front of it** put a reverse proxy with a TLS certificate. Per-address limits (the public share route, and
the sign-in start and invitation preview routes) use the client address uvicorn reports, so set
`FORWARDED_ALLOW_IPS` to your proxy's address (uvicorn then trusts its `X-Forwarded-For`); otherwise everyone
shares the proxy's address and its one limit. Serve the web app and the API under one site so
the session cookie is same-site, and forward `X-Forwarded-*`. The containers bind to 127.0.0.1 only.

**Where documents live.** The default is a volume shared by API and workers. For several machines use an
S3-compatible bucket instead: `STORAGE_BACKEND=s3`, `S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY_ID`,
`S3_SECRET_ACCESS_KEY`, and `S3_ENDPOINT` for MinIO or R2. Objects are content-addressed, so uploads are idempotent.
(`ipo backup` copies the local folder only; a bucket is backed up with the provider's own versioning or replication.)

**E-mail** is optional: with `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` (and
`SMTP_SECURITY=starttls|ssl|none`) an invitation is also sent to the invited address. Without it, the admin copies
the link. A failed send never loses the invitation.

## 2. Security checklist before real users

- [ ] TLS in front; `TRUST_HTTPS=true` (the compose file sets it); `APP_ENV=production` (it refuses to start with no
      authentication).
- [ ] `SIGNUP_MODE=invite` unless you mean open sign-up; consider `ALLOWED_EMAIL_DOMAINS`.
- [ ] Google OAuth client has only your redirect URI `<PUBLIC_BASE_URL>/api/v1/auth/callback/google`.
- [ ] Secrets are files with mode 0600, owned by the deploy user, not in git (`deploy/secrets/` is ignored).
- [ ] Database not reachable from outside the compose network; its volume is backed up (section 4).
- [ ] `/metrics` scraped with an admin token only; `/docs` is off in production.
- [ ] At least two admins per organisation (the service refuses to remove the last one).
- [ ] You have restored a backup into a scratch environment once.
- [ ] GitHub settings in [REPO_SETTINGS.md](REPO_SETTINGS.md) applied, if you publish images.

Not covered by this repository: an external penetration test, your terms of use and privacy notice, and a data
processing agreement. Get those before you take other people's confidential documents.

## 3. Upgrade

1. Read the changelog entry for the version, and `docs/VERSIONING.md` if the API version changed.
2. `ipo backup create --out /backups` (or `pg_dump`). Verify it.
3. Pull or build the new images; `docker compose up -d`. The API runs the database migrations on start; workers
   started before it keep working with the old schema only until the API has migrated, so restart them together.
4. Check `GET /api/v1/system/health` (versions) and the dashboard; run one screening.
5. To go back: stop, restore the backup (`ipo backup restore`), start the previous images. Migrations are forward
   only in production; the backup is the way back.

## 4. Back up and restore

```bash
ipo backup create --out /backups        # SQLite file or pg_dump, every PDF, checksums, verified on writing
ipo backup verify /backups/backup-<stamp>
ipo backup restore /backups/backup-<stamp> --force   # into the configured DATABASE_URL / DATA_DIR
```

Schedule it (cron or a systemd timer) at least daily, keep several, and copy them off the machine. A restore needs an
empty database for PostgreSQL (or `--force`, which drops what is there). The audit trail is part of the backup.

## 5. Watch it

Set `METRICS_ENABLED=true` and scrape `/metrics` with an admin token. Besides request counts and latency it reports
what is waiting and failing: `ipo_jobs_waiting`, `ipo_jobs_running`, `ipo_jobs_failed`,
`ipo_webhook_deliveries_pending|failed`, `ipo_organisations`, `ipo_users_active`, `ipo_sessions_live`, and
`ipo_state_scrape_ok` (0 when the database cannot be read). `deploy/prometheus-alerts.yml` has ready alert rules; a
test keeps them in step with the metrics. Logs are JSON, one line per request with `request_id`, `principal`,
`route`, status and duration (`LOG_FORMAT=text` for people).

**Per organisation usage** for your own accounting: an admin sees `GET /api/v1/org/usage`; you see them all with
`ipo accounts usage --days 30` (cases, documents, pages processed, screenings and members for every organisation).

## 6. When something is wrong

| Sign | Look at | Usually |
|---|---|---|
| Documents stay "uploaded" | `ipo_jobs_waiting`, `docker compose ps worker` | no worker running, or it cannot reach the database |
| Documents stuck "extracting" | `ipo_jobs_running`; they return after `JOB_LEASE_SECONDS` | a worker died mid-job; it is handed back, or failed after `JOB_MAX_ATTEMPTS` |
| Everyone gets 401 | system clock, `DATABASE_URL`, session cookie `Secure` behind plain http | `TRUST_HTTPS` set but the proxy serves http |
| Sign-in loops back to /login | redirect URI, `PUBLIC_BASE_URL`, cookies blocked across sites | app and API on different sites |
| 429 everywhere | `API_RATE_LIMIT_PER_MINUTE`, `RATE_LIMIT_STORE` | a script polling; raise or fix it |
| Webhooks not arriving | `GET /api/v1/webhooks/{id}/deliveries`, `ipo_webhook_deliveries_failed` | the endpoint is down, or its address is not public |
| "append-only" error | someone ran SQL against an audit table | do not; use the erase endpoints |

**A person's account is compromised:** `ipo accounts suspend <email>` (ends their sessions and tokens at once),
review their activity in the export, then reinstate after they have reset their Google credentials.
**A token leaked:** its owner revokes it on "My account"; an admin removing the member revokes all of theirs.
**The webhook signing key leaked:** change `WEBHOOK_SIGNING_KEY` and restart; every endpoint's secret changes, so
rotate and redistribute them (`POST /webhooks/{id}/rotate` shows each new one).
**Data erasure requests:** the case erase and organisation delete in [ACCOUNTS.md](ACCOUNTS.md); they leave an
identifier-only audit record by design.

## 7. Load

`tools/loadtest.py` drives a running server with a realistic mix (reads, comments, exports, case creation) from
several organisations at once and prints requests per second and the 50th, 95th and 99th percentile latency per
route, and fails if any response is a server error or any organisation sees another's data.
Run it against a staging copy before you promise anyone a number; the results in `docs/status.md` are from one
small machine and say what that machine did, not what yours will.
