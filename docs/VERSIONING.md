# Versioning

IPO Engine has **one package version** and several **independent output versions**. Mixing them up
is the usual source of "which version is this?" questions, so each has one home and one rule.

| Axis | Where it is written | Shown by | Bump when |
|---|---|---|---|
| **Package** (SemVer) | `pyproject.toml` `[project] version`, nowhere else | `ipo --version`, `ipo_engine.__version__`, `/api/v1/system/health` `package_version`, wheel metadata, Docker tag | a release is cut (see `RELEASING.md`). MAJOR: a breaking change to the CLI, the API contract or stored data you must migrate. MINOR: a new feature or check. PATCH: fixes only |
| **HTTP API** | `API_VERSION` in `src/ipo_engine/screening/core/constants.py` | `/api/v1/system/health` `api_version` (and the older `version` field, same value), `/api/v1/system/capabilities` | the request/response contract of `/api/v1` changes. Additive fields do not need a bump; removed or renamed fields, or changed meaning, do |
| **Ruleset** | `CURRENT_RULESET_VERSION` in `screening/regulatory/registry.py` and the ruleset files | `ruleset_version` in health, reports and decisions | any rule, threshold or regulatory reference changes. Record the clause and the date the primary text was checked |
| **Analysis** | `ANALYSIS_VERSION` in `src/ipo_engine/analyze.py` | `analysis_version` in health and in every stored analysis | anything that changes the *meaning or shape* of extracted output. Stored output with another number is refused with a message, never silently reused |
| **Parser** | `PARSER_VERSION` in `src/ipo_engine/parse/models.py` | stored parse output | parsing output changes. Cached parses with another number are re-parsed |
| **Screening pipeline** | `PIPELINE_VERSION` in `screening/intelligence/__init__.py` | `/api/v1/system/capabilities` | the screening app's own document pipeline changes |

Rules that follow:

- A change that alters extracted output, a rule outcome or a threshold needs the matching bump,
  a `docs/decisions.md` entry (the next D-number) and a CHANGELOG line. A change that does not alter
  output must not bump any of them.
- The benchmark (`ipo eval`) numbers and `tools/lit_score.py` are measured per analysis version. If a
  bump is not meant to change them, they must come out identical; the record is in `docs/status.md`.
- The package version is *not* tied to the others. A release can contain several analysis bumps.
- `frontend/package.json` carries the same number as the package, so a release is one number. A test
  (`tests/test_versions.py`) fails if the Python package, the CLI and the frontend disagree.

## The `v1.0.0` tag

The only tag on the repository is `v1.0.0`, from 2026-07-09 ("implement IPO Due Diligence Engine
MVP"). It points to a commit that is **not in `main`'s history** (the project was later reorganised
into one package), and at that commit `pyproject.toml` said `0.1.0`. It marks the first MVP of the
screening engine, not a release of the current package. It has been left untouched.

Choosing the next release number is the maintainer's decision. Two honest options:

- **`v0.4.0`** continues from the current 0.3.0 and treats `v1.0.0` as a historical marker. This is
  the simplest and does not claim stability the project has not yet had a person verify.
- **`v1.1.0`** continues from the existing tag, which makes numbers monotonic but tells readers the
  project is past 1.0, with the stability promise that implies, while the benchmark answer keys are
  still unreviewed by a person (see `roadmap.md`, "Needs a person").

Recommendation: `v0.4.0`, and cut `v1.0.0` (a new, annotated tag on `main`, after the old one is
retired or renamed by the maintainer) only once the label audit and the legal review are done.
