# Supply chain, build, deployment and configuration audit

Branch: audit/remediation-2026-11. Auditor: agent_supply_chain. Date: 2026-11-27.
No tracked file was modified and nothing was committed by this agent. Scratch: /tmp/agent_supply/.

## Scope

pyproject.toml, uv.lock, frontend/package.json and package-lock.json, .github/workflows/*.yml, .github/dependabot.yml,
CODEOWNERS, Dockerfile, frontend/Dockerfile, compose.yaml, deploy/*, both .dockerignore files, .gitignore,
.pre-commit-config.yaml, committed secrets (tree and full history), sample_data/data/labels/benchmark, SECURITY.md,
docs/security.md, docs/RELEASING.md, site/, and the offline guarantee (src imports, tests/test_offline.py,
tests/test_network_boundary.py).

## Method

Static reading of every workflow and Dockerfile. `bandit -r src -ll` plus a full JSON listing. `pip-audit` on the venv and on
`uv export --frozen` output. `npm audit` (full and --omit-dev). Python script over package-lock.json (registry URLs,
integrity, install scripts, licences). `uv lock --check`. Regex scans of `git ls-files` and of `git log --all -p` for key
patterns (AKIA, ghp_, github_pat_, xox, sk-, AIza, PRIVATE KEY, glpat, JWT, literal password/secret/token assignments).
`git check-ignore` probes. AST/grep scan of src for network imports. Ran the two offline test files (10 passed).

## Checks and results

| # | Check | Result |
|---|---|---|
| 1 | Third-party actions not pinned to a SHA | Not Found. Every live `uses:` is a 40-hex SHA with a version comment. The one unpinned reference is a commented-out PyPI job (release.yml:248, already annotated "pin to a SHA when enabling") |
| 2 | `pull_request_target` / `workflow_run` | Not Found |
| 3 | Script injection via `${{ github.event.* }}` in `run:` | Not Found as exploitable. Only two `${{ }}` in run: docker.yml:49 (`matrix.name`, constant) and release.yml:92 (`needs.gate.outputs.base`). The latter is reached only after the gate step proves base == pyproject version. `GITHUB_REF_NAME` is used as a shell env var, not interpolated. Hardening note in F6 |
| 4 | Over-broad `permissions` | Not Found. Top-level `contents: read` everywhere (scorecard `read-all`); write scopes only on jobs that need them (release `contents: write` job has no checkout) |
| 5 | Secrets exposure in workflows | Not Found. Only `GITHUB_TOKEN` is used |
| 6 | Cache poisoning | Inconclusive / P4 (F7) |
| 7 | Python deps: typosquats, abandoned, licence | Not Found. 94 locked packages, all registry sources, no git/path/url sources, 1818 sha256 entries. `uv lock --check` passes. Direct deps are lower-bound ranges but `uv sync --frozen` is used in CI and Docker. Licences: MPL-2.0 (pikepdf, certifi, hypothesis dev), LGPL-3.0 (psycopg and psycopg-binary, optional extra, dynamically linked). Compatible with an MIT project; not in NOTICE (unchecked) |
| 8 | pip-audit | Not Found. "No known vulnerabilities" on the venv and on the uv.lock export (`--no-deps`). Local ipo-engine skipped as expected. Snapshot as of today |
| 9 | npm: lockfile integrity, install scripts, licences, audit | Not Found. 213 packages, all `registry.npmjs.org`, all with integrity. Only install scripts: `fsevents` (macOS only). `npm audit` and `npm audit --omit-dev`: 0 vulnerabilities. Licences: 10+ libvips builds are LGPL-3.0-or-later (sharp optional binaries, from Next), CC-BY-4.0 x1 (data package). No GPL/AGPL/unlicensed. `package.json` uses caret ranges but `npm ci` is used everywhere |
| 10 | bandit -ll | 1 Medium, 0 High. Full list: 19 B101, 2 B105, 2 B603, 1 B404, 1 B406, 1 B310. Reviewed below |
| 11 | Dockerfiles: root user, latest tag, secrets | Not Found. Both run as uid 10001, base images pinned by digest, multi-stage, no secrets, HEALTHCHECKs present, `.env*` excluded in the frontend context, API Dockerfile copies explicit paths only |
| 12 | compose.yaml, deploy/compose.accounts.yaml hardening | Mostly OK. 127.0.0.1-only ports, `read_only`, `cap_drop: ALL`, `no-new-privileges`, secrets as files, no DB port published. Findings F2 and F3 |
| 13 | Committed secrets, tree | Not Found. Hits were test fixtures like `API_KEYS="ann|admin|k"` and `.env.example` placeholders |
| 14 | Committed secrets, history (105 commits, all refs) | Not Found for the patterns above. No deleted env/pem/key/db/credential files. No PDF/xlsx/csv/db/zip ever tracked. Limitation: pattern-based, no entropy scanner installed (gitleaks/trufflehog absent); the repo does run gitleaks in CI (secrets.yml) |
| 15 | sample_data / data / labels / benchmark PII | Not Found. Contents are manifest, TOML sources, labels of public filings, and synthetic sample companies (2.9 MB total). Emails in tree are `*.example` placeholders plus the maintainer's public address and noreply address. No PAN/Aadhaar/phone patterns in labels or ground_truth |
| 16 | .gitignore gaps | Confirmed, F1 |
| 17 | site/ static demo | Not Found. Only same-origin `style.css`/`app.js`/`briefs.json`; the external URLs are `<a href>` navigation (GitHub, uv docs). No third-party script/CSS/font, no innerHTML/eval in app.js. No CSP meta tag (low value for a static page; not a finding) |
| 18 | Offline guarantee | Holds, with one documented exception. Tests pass (10). Network library imports in src exist only in `ingest/fetch.py` (the sole permitted downloader per CHARTER and test_offline.py) and `screening/network/*` (opt-in, lazily imported, enforced by test_network_boundary.py). `urllib.parse` imports elsewhere are pure. `tools/loadtest.py` and `tools/screening/benchmark_extraction.py` use urllib/socket but are outside src. No LLM SDK imports. Doc inconsistency F5 |
| 19 | pre-commit config | OK, no secret hook but gitleaks runs in CI. `rev: v4.6.0` is a tag, not a SHA (P4, low) |
| 20 | CODEOWNERS / dependabot | Present. Dependabot covers uv, npm, both docker dirs, github-actions |
| 21 | SECURITY.md accuracy | Not Found for what is checkable (image defaults to production and refuses to start without keys: Dockerfile:41; headers in frontend/next.config.js match docs/security.md). Private vulnerability reporting being enabled on GitHub is Inconclusive (not checkable offline) |

### Bandit findings reviewed

- B310 `src/ipo_engine/screening/network/http.py:46` `urlopen`: not exploitable for file:/ or custom schemes. `_open` calls `require_https` (line 44) first, which allows only https (or http to loopback). Remaining weak spots: it does not block private or link-local hosts (SSRF to internal addresses), but the URLs come from operator configuration (OIDC discovery), not user input. The webhook path has a separate `validate_target` / `PinnedSender`, not reviewed in depth. False positive in practice. P4.
- B105 `models/enums.py:60` ('pass') and `services/accounts.py:36` ('ipo_' token prefix): false positives.
- B404/B603 `services/backup.py:18,71,145`: argv list, no shell, executable resolved by `shutil.which` for fixed names (pg_dump, pg_restore). Arguments come from the DATABASE_URL setting (operator). Not exploitable by a remote user. Operator-controlled values could inject extra options starting with `-`, but not shell commands. P4 at most.
- B406 `services/tabular.py:18`: it is `xml.sax.saxutils.escape` (output escaping), not XML parsing. False positive.
- B101 x19 (asserts): not security relevant unless run under `-O`; not individually reviewed beyond count. Inconclusive for the individual sites.

## Confirmed findings

### F1. .gitignore misses common secret/backup filenames (P3)
- File: /home/user/ipo-due-diligence-engine/.gitignore ("Environment / secrets" block ignores only `.env`, `.env.local`, `.env.*.local`, `*.pem`, `*.key`).
- Evidence (`git check-ignore`): NOT ignored: `.env.production`, `frontend/.env.production` (Next.js convention), `frontend/.env.staging`, `credentials.json`, `service-account.json`, and `backup-<stamp>/database.pgdump` (the directory the backup tool in services/backup.py:~64 creates, containing a full DB dump and documents when `out_dir` is inside the repo). Ignored: `.env`, `deploy/.env`, `deploy/secrets/`, `frontend/.env.local`, `*.db`.
- Root cause: allow-list-style patterns instead of `.env.*` with `!.env.example`; no entry for backup output.
- Fix: add `.env.*`, `!.env.example`, `*.pgdump`, `backup-*/`, `credentials*.json`, `*service-account*.json`, `*.p12`, `*.pfx`.

### F2. Image HEALTHCHECK makes the `worker` service report unhealthy (P3, static analysis; not run)
- Files: Dockerfile:62-63 (HEALTHCHECK GETs 127.0.0.1:8000/api/v1/system/health); deploy/compose.accounts.yaml:70-86 (`worker` reuses `ipo-engine-api:accounts`, `command: ["ipo","worker",...]`, no `healthcheck:` override).
- Evidence: services/worker.py contains no HTTP listener (grep for http/listen/port/health returns nothing; it only imports logging/os/platform/threading/time), so nothing listens on 8000 in the worker container and Docker inherits the image HEALTHCHECK. Expected result: the worker is marked `unhealthy` indefinitely, which defeats monitoring and any `condition: service_healthy` dependents. Docker daemon was not available here to confirm at runtime.
- Fix: add `healthcheck: {disable: true}` or a real worker liveness check (for example a heartbeat file or DB row) to the worker service.

### F3. Unpinned PostgreSQL image in the multi-tenant deployment (P3)
- File: deploy/compose.accounts.yaml:33 `image: postgres:16`.
- Evidence: floating major tag, while every other base image in the repo is digest-pinned (Dockerfile:16-18, frontend/Dockerfile:12). Dependabot's docker ecosystem does not cover compose files here.
- Root cause: omission. Impact: non-reproducible, silently changing database image on pull (including minor upgrades) in the one component holding tenant data.
- Fix: pin `postgres:16.x@sha256:...` and add `/deploy` to dependabot docker updates.

### F4. Release build job runs an un-locked npx download with `id-token: write` and `attestations: write` (P3)
- File: .github/workflows/release.yml:69-73 (job permissions) and :90 `npx --yes @cyclonedx/cyclonedx-npm@7.0.1 ...`.
- Evidence: the top-level package is version-pinned but its transitive dependencies are resolved from the registry at release time, with no lockfile or integrity pin, in the same job that then attests `dist/*` and both SBOMs (`attest-build-provenance`, line after). A compromised transitive dependency could tamper with the attested artefacts or abuse the OIDC token.
- Fix: vendor the tool as a devDependency in a lockfile (`npm ci --ignore-scripts` then `npx --no-install`) or move SBOM generation into a job without `id-token`/`attestations` permissions and attest afterwards.

### F5. Documentation drift (P4)
- docs/RELEASING.md:64 says "The web (Next.js) image is added with the container work" and lines 3-6 describe only the API image, but release.yml:165 defines a `web-image` job that builds and publishes it. Operators following the verify checklist never verify the web image.
- docs/security.md:18 says "no command makes a network call except `ipo ingest`". The screening app has optional OIDC, webhook, SMTP and S3 code (screening/network/*), described correctly in docs/CHARTER.md and tests/test_network_boundary.py. The table row overstates.
- Fix: update both statements.

### F6. Minor CI hardening gaps (P4)
- `actions/checkout` lacks `persist-credentials: false` in 14 of 15 uses (only scorecard.yml:24 sets it). Token is read-only (`contents: read`), so impact is low, but later third-party steps can read it from .git/config.
- release.yml:92 interpolates `${{ needs.gate.outputs.base }}` directly into a shell line. Not exploitable now (value is gated equal to the repo's own version string); pass via `env:` to remove the pattern.
- Root .dockerignore (used for the API image and the docker.yml/compose context `.`) does not list `.env`, so a developer's `.env` is sent in the build context. It is never COPYd (Dockerfile copies explicit paths), so it does not reach the image. Add `.env*`, `.hypothesis`, `audit_reports`, `deploy/secrets` for context hygiene.
- `.pre-commit-config.yaml` pins `pre-commit-hooks` by tag (`v4.6.0`), not SHA.

### F7. Cache usage in privileged workflows (P4, Inconclusive)
- release.yml gate/build jobs use `setup-uv` with `enable-cache: true` and `setup-node` `cache: npm`; images use `cache-to: type=gha,mode=max`. Caches restored into a release job can in principle be seeded from default-branch runs. Mitigations observed: uv and npm caches are content-addressed with hashes from the lockfiles, and Docker layer cache is keyed by instruction content. I did not demonstrate a poisoning path. Consider disabling caches in the release workflow.

### F8. `ipo ingest` has no URL scheme allow-list (P4, impact unverified)
- src/ipo_engine/ingest/fetch.py uses `urllib.request.build_opener()` (default handlers include file: and ftp:); grep finds no scheme check in ingest/*.py. Source URLs come from an operator-supplied sources TOML, and the result must pass a %PDF magic and %%EOF check, so exposure is limited to a malicious sources file. I did not execute this to see how a `file://` URL is handled. Fix: require https (or http) in `SourceSpec` validation.

## Also observed (not findings)

- `audit_reports/raw/baseline_pytest.txt` shows as modified in `git status` (a tracked file under audit_reports). It was not touched by this agent; it is presumably from another audit agent or the coordinator.
- Trivy scanning, Scorecard, CodeQL, gitleaks and dependabot are all configured. Releases attest provenance and produce SBOMs.

## Limitations

- No runtime check of the Docker images or compose stacks (no daemon use); F2 is based on static reading.
- Secret scan is regex-based over `git log --all -p` and the tracked tree; no entropy-based scanner was available. Lock files and `*.jsonl` and `labels` were excluded from the history password-assignment grep (but not from the key-pattern grep except the two lock files).
- `pip-audit`/`npm audit` results depend on advisory databases reachable today via the proxy and are a point-in-time snapshot. The Python audit of uv.lock used `--no-deps` on the uv export.
- Licence analysis uses declared metadata only; two Python packages (numpy, pypdfium2) report no licence field in the venv metadata and were not investigated further.
- GitHub-side settings (branch protection, private vulnerability reporting, Pages, package visibility) are not verifiable from the checkout. docs/REPO_SETTINGS.md was not compared with the live settings.
- Only the 19 B101 bandit asserts were counted, not individually reviewed. `webhook_http.py` SSRF controls and `oidc.py` were out of this role's depth and not audited.

## Severity summary

P3: F1, F2, F3, F4. P4: F5, F6, F7, F8. No P0-P2 found.
