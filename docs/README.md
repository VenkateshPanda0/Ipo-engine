# Documentation index

One index for the whole project, the reader (command line) and the screening app (web). Every document
under `docs/` is linked from here; a test fails if one is not.

## Start here

| You want to | Read |
|---|---|
| Understand the aim and the fixed rules | [CHARTER.md](CHARTER.md) |
| See how the parts fit together | [ARCHITECTURE.md](ARCHITECTURE.md) (one diagram for both halves) |
| Know what to work on next | [roadmap.md](roadmap.md) (the ordered TODO), then [plan.md](plan.md) (phases and gates) |
| See today's numbers and known defects | [status.md](status.md) |
| Find why something is built the way it is | [decisions.md](decisions.md) (D-001 onward) |
| Set up, run, contribute | the repository [README](../README.md) and [CONTRIBUTING](../CONTRIBUTING.md) |

## Running and releasing it

| Document | What it covers |
|---|---|
| [VERSIONING.md](VERSIONING.md) | The package version and the independent API, ruleset, analysis and parser versions; the old `v1.0.0` tag |
| [RELEASING.md](RELEASING.md) | How a release is cut and verified (tag, changelog, wheel, images, SBOMs, provenance) |
| [REPO_SETTINGS.md](REPO_SETTINGS.md) | GitHub settings applied by hand: branch rules, security features, Pages, packages |
| [security.md](security.md) | Threat model for hostile PDFs; the API's authentication, headers and key rotation. Reporting a vulnerability: [SECURITY.md](../SECURITY.md) |

## The reader (command line)

| Document | What it covers |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Packages, what each does and never does, data on disk |
| [decisions.md](decisions.md) | The decision log, with the numbers behind each change |
| [status.md](status.md) | Every computed number, latest first |
| [plan.md](plan.md), [roadmap.md](roadmap.md) | Where it is going |

### Held-out runs

Each held-out set is run once, with the first-run numbers, the causes of every miss and what was
fixed, kept as a record (a set stays held out unless a defect it exposed is fixed, D-037).

| Run | Notes |
|---|---|
| [1](history/heldout-run-1.md) | First contact with three unseen filings |
| [2](history/heldout-run-2.md) | Three more, after the run-1 fixes |
| [3](history/heldout-run-3.md) | Powerica, SRIT India, Veritas Finance |
| [4](history/heldout-run-4.md) | Three large unseen filings |
| [5](history/heldout-run-5.md), [6](history/heldout-run-6.md), [7](history/heldout-run-7.md) | Three more each, after the previous fixes |
| [8](history/heldout-run-8.md) | Three draft documents, extractor unchanged |
| [9](history/heldout-run-9.md) | Two lenders and two SME drafts |
| [10](history/heldout-run-10.md) | Three unseen sectors, one disputed label |
| [11](history/heldout-run-11.md) | A lender, and a new document type |
| [12](history/heldout-run-12.md) | A full lender draft, extractor unchanged |
| [m0 report](history/m0-report.md) | The first milestone report (historical; its paths predate the merge) |

## The screening app (web)

Where these disagree with [ARCHITECTURE.md](ARCHITECTURE.md) or [status.md](status.md), those win.

| Document | What it covers |
|---|---|
| [screening/ARCHITECTURE.md](screening/ARCHITECTURE.md) | Layers, import boundaries, rules, persistence |
| [screening/DEVELOPER_GUIDE.md](screening/DEVELOPER_GUIDE.md) | Working on the app: adding a rule, an extraction label |
| [screening/DOCUMENT_INTELLIGENCE.md](screening/DOCUMENT_INTELLIGENCE.md) | The app's own PDF pipeline, OCR, candidates |
| [screening/HUMAN_REVIEW_WORKFLOW.md](screening/HUMAN_REVIEW_WORKFLOW.md) | Review queue, confirm or correct, sign-off, audit |
| [screening/REGULATIONS.md](screening/REGULATIONS.md) | The 19 eligibility rules, clause by clause |
| [screening/REGULATORY_VALIDATION.md](screening/REGULATORY_VALIDATION.md) | Why the ruleset is not yet legally reviewed |
| [screening/BENCHMARK.md](screening/BENCHMARK.md), [BENCHMARK_RESULTS.md](screening/BENCHMARK_RESULTS.md) | The extraction benchmark: method and results |
| [screening/TECH_DEBT.md](screening/TECH_DEBT.md) | Known debt, by severity |
| [screening/CHANGELOG.md](screening/CHANGELOG.md) | The app's history before it joined this package (to 2.0.1) |
| [screening/audit/BASELINE.md](screening/audit/BASELINE.md) | The audit of the first engine (historical) |

### Architecture decision records

| ADR | Decision |
|---|---|
| [0001](screening/adr/0001-deterministic-rules-engine.md) | A deterministic rules engine |
| [0002](screening/adr/0002-no-readiness-score.md) | No blended readiness score |
| [0003](screening/adr/0003-manual-regulation-updates.md) | Regulation updates are manual |
| [0004](screening/adr/0004-company-data-canonical-schema.md) | `CompanyData` is the canonical schema |
| [0005](screening/adr/0005-local-extraction-no-llm.md) | Local, deterministic extraction, no LLM |
| [0006](screening/adr/0006-sqlite-append-only-audit.md) | SQLite with an append-only audit |
| [0007](screening/adr/0007-outcome-wording.md) | Screening outcomes, not eligibility verdicts |

## Following the steps

1. Set up and run: [README](../README.md), "How to use it".
2. Change something: [CONTRIBUTING](../CONTRIBUTING.md) (gate, tests, labels first, the behaviour-freeze rule).
3. Pick work: the first unchecked item in [roadmap.md](roadmap.md).
4. Finish: update `CHANGELOG.md`, [status.md](status.md) (computed numbers only) and
   [decisions.md](decisions.md); run `tools/gate.sh; echo rc=$?`; push.
