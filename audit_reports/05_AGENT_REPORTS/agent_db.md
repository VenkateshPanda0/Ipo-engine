# Agent report: database consistency, jobs, lifecycle (agent_db)

Branch audit/remediation-2026-11. Date 2026-11-27. No tracked file was modified. Scripts are in /tmp/agent_db/ (harness.py, mig.py, trig.py, t_claim.py, t_lease.py, t_misc.py, t_erase.py).

## Scope and method
Read: db/{base,maintenance,migrate,models,repositories}.py, migrations 0001-0004, services/{worker,lifecycle,backup,tenancy,documents,accounts,review_service}.py, parts of cases.py and collab.py, core/config.py, api/dependencies.py, cli.py (accounts/worker commands).
Ran real code against SQLite files (WAL, foreign_keys=ON) built via Container.build and the Alembic chain.
PostgreSQL: `which pg_ctl postgres` found nothing. Every Postgres path (pg_dump/pg_restore, trigger DDL in 0003, DISABLE TRIGGER USER, READ COMMITTED races) is code-reviewed only, not executed.
Effort was cut short by a rate-limit stop. Several requested checks were not run (see "Not run").

## Confirmed findings

### F1 (P1) Failed erase leaves append-only triggers permanently dropped on SQLite
- Code: db/maintenance.py:35-36 (DROP TRIGGER) and :37-46 (re-create in `finally`). Called from services/lifecycle.py:281. The module docstring (maintenance.py:6-9) claims the DDL is part of the transaction and rolls back.
- Root cause: with the default pysqlite transaction handling no BEGIN is issued before DDL or SELECT. The DROP TRIGGER statements autocommit immediately. Only the later DELETEs and the re-creation run in a transaction. If the session then rolls back, the deletes are undone, the re-creation is undone, and the drops stay committed.
- Reproduction (/tmp/agent_db/t_erase.py): build a Container, create a case, wrap `lifecycle._erase` so it raises after running, call `erase_case`. Triggers before: 8. After the failed erase: 2, only audit_events_no_update and audit_events_no_delete. `UPDATE case_data_versions SET reason='TAMPERED'` then succeeds (rowcount 1). case_data_versions, review_item_events and human_review_events lose their protection until a later successful erase re-creates them or the DB is rebuilt.
- Caveat: my injected failure was raised after `_erase` returned. Failures inside the lifted block would behave the same way by the mechanism above, but I did not reproduce that variant. Any failure after the DROP (a DB error, an exception in `audit()`, a process crash between the DROP and the commit) leaves the same state.
- Impact: silent loss of the tamper-evidence guarantee on the version and review history, and the app does not notice.
- Fix: run the DROP/CREATE inside an explicit transaction (`BEGIN IMMEDIATE` before the DDL, or set `isolation_level=None` plus manual BEGIN via an engine "begin" event). Alternatively replace the drop/re-create with a flag table that the triggers consult. Add a startup check that asserts all 8 triggers exist, with a test.

### F2 (P2) Alembic downgrade 0002 to 0001 drops the audit_events triggers; upgrading again does not restore them (SQLite)
- Code: migrations/versions/0002_accounts.py:150-153 (`batch_alter_table("audit_events")` with `drop_column`), env.py `render_as_batch=True`. 0001's `_append_only_triggers` runs only in 0001's upgrade.
- Root cause: dropping a column in SQLite batch mode recreates the table. The recreate drops the table's triggers.
- Reproduction (/tmp/agent_db/trig.py): upgrade to head (8 triggers). Downgrade to 0001: audit triggers 0. Upgrade to head: audit triggers still 0. `UPDATE audit_events` and `DELETE FROM audit_events` both succeed. A full chain head to base to head restores all 8, because 0001 recreates them (/tmp/agent_db/mig.py).
- The downgrade chain 0006 to base and back to head ran without error on an empty DB. I did not test it on a populated DB.
- Severity reasoning: operational path only (a rollback and re-deploy).
- Fix: re-create the triggers in 0002's downgrade/upgrade after batch ops, or add a later migration that idempotently ensures triggers (CREATE TRIGGER IF NOT EXISTS).

### F3 (P3) SQLite append-only triggers bypassed by INSERT OR REPLACE
- Code: migrations/versions/0001_initial_schema.py:27-37 (only BEFORE UPDATE and BEFORE DELETE).
- Root cause: REPLACE conflict resolution deletes rows without firing delete triggers unless `recursive_triggers` is on (PRAGMA reads 0).
- Reproduction (trig.py): `INSERT OR REPLACE INTO audit_events(id,...) VALUES(1,'forged',...)` returns rowcount 1 and the stored actor becomes 'forged'. Plain UPDATE and DELETE are blocked.
- Needs raw SQL access, not reachable through app code I read. Postgres is not affected by this mechanism (not run).
- Fix: `PRAGMA recursive_triggers=ON` in the connect hook (base.py:52-58), or add a BEFORE INSERT trigger that aborts when the id exists.

### F4 (P2) Concurrent first-time sign-in and concurrent sign-off surface raw IntegrityError (likely HTTP 500)
- Sign-in race: accounts.py:519-560 (select-then-insert on users.email unique, no retry). 8 threads calling `sign_in` with the same new email and signup_open=True: 1 ok, 7 `IntegrityError: UNIQUE constraint failed: users.email`. No duplicate user was created; the failure is an unhandled exception. `get_or_create_user` (accounts.py:129-138) has the same pattern (not run).
- Sign-off race: review_service.py:29-45 (`open_review` get-then-create) and repositories.py `SqlReviewStorage.save` (decision-exists check is an app-side SELECT). 8 threads doing open_review plus complete_review on one report: 1 ok, 7 IntegrityError on human_reviews.report_id unique. One decision event only. The DB constraint holds, but callers see an unhandled error rather than 409.
- Postgres: not run. Under READ COMMITTED the unique(report_id) on human_reviews still prevents duplicate reviews. There is no unique index on (review_id, event_type='decision') in human_review_events, so two concurrent `complete_review` calls on the same existing review can each pass the SELECT check and both append a "decision" event. This is code-review only (unverified). SQLite serialised the writers in my run, so I could not reproduce it.
- The four-eyes check (api/routers/v1.py:777-785) is a pre-check outside the transaction (unverified for races).
- Fix: catch IntegrityError and re-read or return 409. Add a partial unique index on human_review_events(review_id) WHERE event_type='decision'. Use INSERT ... ON CONFLICT.

### F5 (P2) Backup verify and restore trust files that are not in the manifest
- Code: backup.py:107-119 (verify iterates only manifest["files"]); backup.py:169-170 (restore copies every `*.pdf` in documents/ with copy2).
- Reproduction (t_misc.py): add `documents/bbbb...pdf` containing b"evil" to a backup. `verify` passes. Restore copied an unlisted `cccc...pdf` into the target documents dir. The store is content-addressed (name = sha256), but restore never checks that the content hashes to its filename.
- Related, verified: a truncated DB is rejected by checksum. A restore into an existing DB is refused without force. With the manifest `files` emptied and a garbage DB, verify raises `DatabaseError: file is not a database` (not a BackupError). So the manifest can be edited together with the file; the manifest has no signature.
- Not reproduced: restore is a plain `shutil.copy2` over the target DB (backup.py:166), not atomic, so a crash mid-copy leaves a truncated DB (code-review only).
- Fix: verify that the set of files equals the manifest, check pdf name equals sha256 of content on restore, restore via temp file plus os.replace, and optionally sign the manifest.

### F6 (P2) In-memory RateLimiter never evicts keys
- Code: documents.py:92-110 (`defaultdict(deque)`, keys never deleted). Neither `RateLimiter` nor the public limiter has `sweep` (the worker's sweeper only calls `sweep` if present, worker.py:80-82).
- Reproduction (t_misc.py): 50,000 distinct keys, one hit each, no sweep: 50,000 entries retained. Growth is unbounded in the number of distinct clients over process lifetime.
- What I did not check: which value is used as the key in public routes (per-address key) and whether it is spoofable via X-Forwarded-For. This determines whether an unauthenticated client can drive growth.
- Fix: delete the key when its deque empties, or add a periodic sweep; cap the key count.

### F7 (P3) Job lease and retry weaknesses (confirmed on SQLite, queue mode)
Reproduction in /tmp/agent_db/t_lease.py.
- No double-claim: 16 threads x 40 jobs gave 40 claims, 40 unique, 0 errors in 0.33 s (documents.py:478-515).
- Poison limit works: with JOB_MAX_ATTEMPTS=3 the job goes uploaded, extracting, uploaded, extracting, uploaded, extracting and then failed/INTERRUPTED at attempts=3 (documents.py:517-559).
- Retry does not reset `attempts` (documents.py:349-380). After a manual retry the next lease expiry fails the job immediately (observed: attempts 4 followed by failed on the first expiry).
- Zombie heartbeat: `_progress` (documents.py:561-578) updates the row by id without checking `claimed_by`. Worker A, whose lease expired and whose job was re-claimed by B, extended B's lease and overwrote the stage (observed `claimed_by` B, stage 'zombie', lease extended). Likewise `_persist` and the failure path write without checking ownership. Only the status transition guards the zombie, and only by accident.
- Orphan state: a row in `extracting` with NULL `lease_expires_at` is never requeued (`requeue_expired` requires a non-null lease; observed (0,0) and the row stayed extracting). Queue-mode `startup` does not call `recover_interrupted`.
- Fix: include `claimed_by == worker` in heartbeat, persist and fail updates and abort when rowcount is 0; reset attempts on manual retry; also sweep extracting rows with NULL lease.

### F8 (P3, code-review only, not run) Local mode `recover_interrupted` fails every in-flight job
- Code: dependencies.py:172 calls `recover_interrupted` in local mode, documents.py:445-465 fails all rows in `uploaded` or `extracting`. With several API replicas on one shared (Postgres) DB in local mode, restarting one replica marks the other replicas' running jobs failed. Single-process SQLite is not affected. Not reproduced.

## Checks with results

| Check | Result |
|---|---|
| Concurrent `claim_next`, double claim | Not Found (40/40 unique) |
| Lease expiry, requeue, max attempts | Confirmed working, with weaknesses F7 |
| Worker crash mid-job (lease lapse) | Covered by the requeue test; no real process kill was done. Inconclusive for kill -9 |
| Migration chain 0006 to base to head (empty DB) | Not Found (no error), but F2 trigger loss at 0001 |
| Migration on populated DB | Inconclusive (not run) |
| Append-only UPDATE/DELETE blocked at head | Not Found (blocked) |
| Append-only bypass | Confirmed F1, F2, F3 |
| FK enforced on SQLite | Not Found as a defect: `PRAGMA foreign_keys`=1 on pooled connections. My FK-violation insert failed first on NOT NULL, so FK rejection itself was not demonstrated. Inconclusive |
| Unique race: sign-in same email | Confirmed (F4, error not corruption) |
| Four-eyes / sign-off concurrent | Confirmed IntegrityError (F4); duplicate decisions not reproduced |
| Erase partial failure rollback | Confirmed defect F1 (rows roll back, triggers do not) |
| Backup to restore round trip, tampered/truncated | Truncated rejected; unlisted-file gap Confirmed (F5) |
| Restore into non-empty DB | Not Found (refused without force) |
| Rate limiter memory growth | Confirmed F6 |
| Graceful shutdown with in-flight job | Not run. Code: `QueueWorker.stop` joins threads for 5 s each, daemon threads, in-flight job is abandoned and recovered by lease expiry |
| Idempotency of retried upload | Code-review only: same sha256 per case returns the existing doc (documents.py upload); the (case_id, sha256) unique constraint backs it. A concurrent duplicate upload would raise IntegrityError (not run) |
| Timezone naive vs aware | Inconclusive: SQLite round-trips naive values; `purge_expired` handles naive created_at (documents.py:424-426); the lease comparison worked in my tests. Not stress-tested |
| Insecure startup settings | Not run. config.py defaults: `allow_unauthenticated` False but "no keys means every caller is admin" outside production; app_env default "development"; read_secret_files OK. Not verified against main.py |
| SQLite busy/locked under concurrent writers | Not Found in my runs (timeout 30 s plus busy_timeout 30000 in base.py:44,57; no "database is locked" seen in the 16-thread claim test) |

## Not run (due to the stop)
Populated-DB downgrade, kill -9 of a worker, real graceful-shutdown test, concurrent duplicate upload, concurrent four-eyes approvals via HTTP, API-level idempotency, rate-limit key derivation, startup insecure-config review, org purge rollback, erase versus in-flight extraction, S3 store backup (the backup only copies local `*.pdf`, so S3 documents are not included; code-review only).

## Limitations
SQLite only. PostgreSQL behaviour (trigger DDL being transactional there, which would make F1 SQLite-specific; row locking; READ COMMITTED lost updates) was not executed. Findings are from a single run each; the injected erase failure is synthetic. No tracked files changed.
