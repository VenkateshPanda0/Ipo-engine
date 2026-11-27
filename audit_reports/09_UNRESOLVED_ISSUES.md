# Unresolved issues

Everything confirmed and not fixed on this branch, with the reason and what resolving it needs. Fixed items are in `07_CHANGELOG.md`.

| ID | Sev | Issue | Where | Why it remains | To resolve |
|---|---|---|---|---|---|
| F-18 | P3 | CLI/offline path has no page, size or time cap | parse/pdf.py | Needs a product decision on default limits for an operator's own offline files | Not fixed: add --max-pages default, size and time limits to the CLI. |
| F-22 | P3 | INSERT OR REPLACE rewrites an audit_events row on SQLite | db/migrations | Needs a migration (PostgreSQL has no such REPLACE path); SQLite fix is small but touches every environment | Not fixed: enable PRAGMA recursive_triggers or add a BEFORE INSERT guard. |
| F-25 | P4 | Kelvin sign (U+212A) in an email domain passes the allow-list | services/accounts.py | Needs a decision on non-ASCII email domains | Not fixed: NFKC-normalise and require ASCII in the domain. |
| F-26 | P4 | Sign-off reviewer_name is free text | api/routers/v1.py | Changes the sign-off record; needs the owner's decision | Not fixed: take the name from the authenticated user in accounts mode. |
| F-27 | P3 | postgres:16 image not digest-pinned in compose.accounts.yaml | deploy/compose.accounts.yaml | Needs registry access to read the digest | Not fixed: pin by digest and let Dependabot update it. |
| F-28 | P3 | release.yml runs npx @cyclonedx/cyclonedx-npm with unlocked transitive dependencies in a job holding id-token/attestations | .github/workflows/release.yml | Release workflow; cannot be exercised without tag pushes, which this environment blocks | Not fixed: commit a lockfile for the tool or use a pinned action. |
| F-29 | P4 | persist-credentials not disabled on 14 of 15 checkouts; pre-commit rev is a tag | .github/workflows, .pre-commit-config.yaml | CI configuration; not exercised here | Not fixed: persist-credentials: false on every checkout; pin hook revs to SHAs. |
| F-30 | P4 | Server-supplied links rendered without a scheme/host check | frontend/src | Needs a decision on which hosts links may point to | Not fixed: allow same-origin and https links to a small host list. |
| F-31 | P2 | alembic downgrade 0002->0001 drops audit_events triggers and a later upgrade does not restore them | db/migrations/0002 | Migration change; the downgrade path is rarely used | Not fixed: re-create triggers in the downgrade and the next upgrade. |
| F-33 | P4 | Static demo has no CSP | site/ | Static demo; low exposure | Not fixed: add a meta CSP. |
| F-34 | P2 | Concurrent sign-offs on one report: 7 of 8 get IntegrityError (no duplicate rows) | api/routers/v1.py | Same pattern as F-32; not fixed in this pass | Not fixed: catch IntegrityError and return 409. |
| F-38 | P4 | Minor parsing defects: 'rs' inside words, bad grouping, numfmt on NaN, citation page order | parse, numfmt, analyze | Minor; unlikely from the pipeline | Not fixed: see 05_AGENT_REPORTS/agent_logic.md. |
| F-39 | P3 | Queue: zombie worker extends a new owner's lease, retry keeps attempts, NULL lease never requeued | services/documents.py | Requires threading the worker id through the processing pipeline; larger than one safe change | Not fixed: pass the worker id through process() and check it on every lease write. |
| F-40 | P3 | Local mode: startup recovery fails jobs of other replicas sharing one database (read only) | services/documents.py | Local single-process mode only; needs the queue mode to be detected | Not fixed: skip recovery when a shared queue is in use. |
| F-44 | P3 | Horizontal overflow at 320 px on /rules and in the static demo | frontend, site | Visual change that needs a browser review at 320 px | Not fixed: allow wrapping or a focusable scroll region. |
| F-45 | P4 | API key held in sessionStorage | frontend/src/lib/auth.ts | Mitigated by the strict script-src CSP; storage change needs a UX decision | Not fixed: the strict script-src mitigates; consider memory-only keys. |
| F-46 | P4 | One dispatcher thread serves every organisation's webhooks | services/webhooks.py | Design change | Not fixed: a small pool, or per-organisation fairness. |

## Not issues, but untested

- PostgreSQL code paths (no server in the sandbox): reviewed, not executed. One PostgreSQL backup test skips for that reason.
- Docker image build and compose stack: not run (no Docker).
- OCR (7 tests skip: Tesseract not installed).
- Real Google sign-in, S3, SMTP and webhook receivers: tested only against local fakes.
- Keyboard-only and screen-reader walk-throughs: need a person.
- Mutation testing, full-pipeline determinism across hash seeds, kill -9 of a worker, graceful shutdown, migration on a populated database: not run.
- Cross-browser (only Chromium installed).
- An external penetration test and legal review of the ruleset: outside what a code audit can supply.
