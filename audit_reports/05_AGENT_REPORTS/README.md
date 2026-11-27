# Agent reports: what was real and what was not

**You asked for 50 independent agents. I did not run 50.** What ran:

| Kind | Count | Notes |
|---|---:|---|
| Real subagents, started with the Agent tool, each with its own scope and instructions to run real code | **9** | listed below |
| Structured role passes by the lead auditor (static scans, own tests, reproduction of each reported finding, adversarial diff review) | 1 pass, not 41 | the other roles in your table were not simulated agent by agent; I did not invent reports for them |

The eight finders were told not to modify tracked files and to report only reproduced facts. All eight hit the account's 5-hour usage limit mid-run and were resumed once the limit reset, which is why some probes are thinner than planned (see each report's limitations). The ninth, a verifier that did not write any fix, re-ran the original reproductions against the fixed code.

| Report | Scope | Roles from your table it stands in for |
|---|---|---|
| `agent_authz.md` | access control, tenant isolation, business-logic abuse | security (part), functional |
| `agent_auth.md` | sessions, CSRF, CORS, OIDC, secrets | security (part) |
| `agent_network.md` | SSRF, webhooks, S3/SMTP, exports, backup | security (part), integration |
| `agent_ingest.md` | hostile files, resource exhaustion, ReDoS | security (part), edge-case, performance |
| `agent_logic.md` | number, unit and period logic, rule boundaries | functional, edge-case |
| `agent_db.md` | transactions, queue, lifecycle, migrations, backup | reliability, integration |
| `agent_frontend.md` | DOM safety, accessibility, hydration, viewport | usability and accessibility, security (part) |
| `agent_supply_chain.md` | dependencies, CI, Docker, secrets, offline guarantee | dependency and supply chain |
| `agent_verifier.md` | independent re-verification of the fixes | regression and independent verification |

The reports are kept as the agents wrote them. They name some files that do not exist (for example `.env.production`, to show it is not ignored) and cite `file:line`, so `tests/test_docs.py` skips this folder.

Roles not covered by any agent: dedicated performance, architecture review, compatibility (only Python 3.12 and Chromium were available), and a second reliability pass. These are listed as gaps in `10_FINAL_VERIFICATION.md`, not counted as done.
