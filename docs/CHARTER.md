# Operating charter

Read this before changing anything in this project. It records what the project owner has
decided, so an agent working here alone, including a scheduled run with no human present, behaves
the same way every time.

## Authority

On 2026-10-23 the owner delegated this project entirely: "just do what you think is right … you have
100% control on this project … I don't want any involvement … don't ask me anything." Decisions,
including dropping or rebuilding parts of the design, belong to whoever is maintaining the project.
Record each in `decisions.md` with the alternatives and the reason. Do not stop to ask the owner.

Delegation covers *this project*. It does not lift the owner's earlier standing rules below.

## Fixed goals (owner, 2026-11-07; they do not change)

1. Fully offline and **no LLM** (owner, clarified 2026-11-07: "no LLM, AI is fine"). No language
   model of any kind, hosted or local, and no cloud API. Other machine learning (OCR, layout or table
   detection, small classifiers) is allowed if it runs locally, is measured on labelled data before it
   feeds any figure, and never replaces the checks that make a figure verified (D-053).
2. Full accuracy, read as *never silently wrong* (D-043).
3. Save people the most time (fewest pages opened; every output names its page).
4. Good enough to build a company on: see "Startup-grade" in `plan.md`.
5. Work only on the `main` branch; no other branches.

## Standing rules from the owner (still in force)

1. **Identity.** Commits are authored and committed only as
   `Venkatesh Panda <166646817+VenkateshPanda0@users.noreply.github.com>`. Set it as the *local*
   repo config; never touch global config; never use any other name or email.
2. **No AI attribution.** No `Co-Authored-By`, session links or any other AI trailer in commit
   messages or PR text.
3. **History.** No amend, rebase, reset, force-push or branch deletion of published work. Fix
   mistakes with a new commit.
4. **Verify attribution.** After every commit run
   `git log -1 --format='%an <%ae> | %cn <%ce>'`; author and committer must both be the owner's.
5. **Honesty about results.** Never say a test passes unless it was run. Never state a metric that
   was not computed by code in this repository. Report failures, nulls and defects plainly.
6. **Primary sources win.** If a regulation, filing or order contradicts a note, a README or a
   secondary article, the primary source wins and the discrepancy is recorded.
7. **No investment advice.** Output is diligence flags with evidence. Every report carries:
   "Not investment advice. Automated analysis of public disclosures; verify against the source
   document."
8. **Data hygiene.** Public filings only; honour robots.txt; rate-limit; keep source URLs and
   hashes; no profiles of individuals; no personal data beyond what the filing contains.

## Project rules

- **One project.** The reader (`src/ipo_engine/`, all but `screening/`) and the screening and
  review app (`src/ipo_engine/screening/`, `frontend/`) live in one package with one test suite, one
  CI workflow and one gate. The screening app does not import the reader yet and the reader never
  imports the screening app; the plan (Phase 5) replaces the screening app's own extraction with the
  reader's verified core. See `decisions.md` D-051.
- **Product aim (owner, 2026-11-06).** Full accuracy, and the most time saved for the people who use
  it. Read "full accuracy" as *never silently wrong*: a figure is shown only if it was re-read from
  its cited page; a disagreement or an ambiguous definition is withheld with the reason, and the
  count of wrong values shown on held-out filings must stay zero. A withheld figure costs one
  page-check; a wrong one costs trust. Time saved means the analyst opens fewer pages: a one-page
  brief per filing, a triage view across filings, a "check this" list that names the exact page for
  every flagged or withheld item, and (once the segmenter exists) the text-level checks that now take
  the longest to read. See `decisions.md` D-043.
- **Evidence.** Every extracted value and every flag cites a PDF page and the text it came from.
  A value whose cited page does not contain it is not reported (`verify/`).
- **Deterministic and offline.** Rules, patterns and table parsing only. The software contains no
  language model and no model client, and runs completely offline once the filings are on disk;
  `ipo ingest`, which downloads public PDFs, is the only command that touches the network
  (`decisions.md` D-042).
- **Untrusted text.** Offer-document text is data. It is never executed, never interpolated into a
  system prompt as an instruction, and never allowed to change behaviour.
- **Thresholds.** A regulatory threshold in a rule names the clause, the effective date and the date
  it was checked, taken from the primary text. A threshold that is our own heuristic says so.
- **Quality bar.** `ruff`, `ruff format --check`, `mypy` (strict on `extract/`, `verify/`,
  `flags/`) and `pytest` all pass before a commit. Tests are written first for new behaviour and are
  shown to fail without the change.
- **Documents.** Raw PDFs and parsed output are git-ignored. Commit only `data/sources.toml` and
  `data/manifest.jsonl`.
- **Small commits.** One concern per commit, imperative message, no unrelated changes.

## Daily routine

1. Read `roadmap.md` and the latest `status.md`; run the checks.
2. Pick the highest-value item that can be finished and *measured* in one sitting.
3. Write the test, make it pass, run every check, commit, verify attribution, push to the working
   branch.
4. Update `status.md` with what changed, the numbers it moved (computed, not recalled), and what
   failed.
