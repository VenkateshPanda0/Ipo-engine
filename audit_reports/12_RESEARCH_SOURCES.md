# Research sources

**Honest scope.** I did not run web searches in this audit. The three checklists were compiled from the project's own code, its docs (`docs/CHARTER.md`, `docs/security.md`, `docs/ARCHITECTURE.md`) and the findings of the review agents, and framed with well-known public taxonomies that I know from training. I did not re-fetch those documents during the audit, so I cite them as the frame used, not as pages that were read for this report. Where a finding rests on observed behaviour, the evidence is in `05_AGENT_REPORTS/` and the test names, not in these references.

## Taxonomies used to choose entry types

- OWASP Top 10 (2021) and the OWASP API Security Top 10 (2023): broken access control, injection, SSRF, security misconfiguration, unrestricted resource consumption.
- OWASP Application Security Verification Standard (ASVS): sessions, authentication, file handling.
- CWE entries behind specific findings: CWE-22 (path traversal), CWE-59 (link following), CWE-79 (XSS), CWE-352 (CSRF), CWE-400 / CWE-409 (resource consumption, decompression bomb), CWE-1333 (inefficient regular expression), CWE-918 (SSRF), CWE-862 / CWE-863 (missing and incorrect authorisation), CWE-362 (race condition), CWE-1236 (CSV formula injection).
- CVSS v3.1 as the model for severity; no CVSS vectors were computed (see `02_SECURITY_AUDIT.md`: severities are P0 to P4 by impact).

## Technical behaviour relied on

- Python `sqlite3` (pysqlite) transaction control: a transaction is opened before INSERT/UPDATE/DELETE, not before DDL. This is the mechanism of F-21; I confirmed it by running the code (8 triggers became 2), not by reading documentation.
- SQLite `recursive_triggers` pragma and `INSERT OR REPLACE`: F-22, reproduced by the db agent.
- Python `ipaddress` `is_global` and the IPv6 transition ranges (NAT64 64:ff9b::/96, 6to4 2002::/16, ::/96): F-08, reproduced through the validator.
- `hmac.compare_digest` on `str` accepting ASCII only: F-12, reproduced.
- PDF deflate streams and `zlib.decompressobj` with `max_length`: F-01, reproduced.
- Ruff, mypy, bandit, pip-audit, npm audit, axe-core, Playwright: tools actually run (`06_TEST_RESULTS.md`).

## Internal sources

- `docs/decisions.md` (D-068, D-069), `docs/ACCOUNTS.md`, `docs/OPERATIONS.md`, `SECURITY.md`.
- The eight agent reports in `05_AGENT_REPORTS/`.

## Not done

No search of CVE or GitHub advisory databases for the specific libraries beyond what `pip-audit` and `npm audit` report; no review of other projects' post-mortems.
