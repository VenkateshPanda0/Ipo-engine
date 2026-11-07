# IPO Engine: the plan (2026-11-07)

## The goal, in the owner's words

1. **Full accuracy.** Read as *never silently wrong*: a figure is shown only when it was re-read
   from its cited page; anything ambiguous or disputed is withheld with the reason and the page to
   check. The count of wrong values shown on held-out filings must stay at zero.
2. **Save people the most time.** Measured in pages a person has to open. Every output names the
   exact page; nothing asks the reader to search.
3. **Do the work of an IPO due-diligence team**, both sides of it: read a filed DRHP/RHP for an
   investor or analyst, and help prepare one for an issuer and its bankers (D-045).
4. **Offline, no language model** (D-042). Deterministic rules, patterns and table parsing.

## Startup-grade: what that requires (owner goal, 2026-11-07)

Offline and no language model is the product's edge: bankers, issuers and funds can run it on
confidential drafts without sending a page off the machine. To be a company and not a project it
must also be:

| Need | Why a customer asks for it | State |
|---|---|---|
| **Proven accuracy by a stranger** | "Who checked your labels?" | AI-written labels only; a person must audit about 100 (2.1). Biggest gap. |
| **Legal review of the rules** | A bank will not rely on unreviewed regulation | SCRR and exchange rules marked unverified; no lawyer yet |
| **Issuer-side value** | The paying customer is the lead manager and issuer, not the casual reader | Preparer not started (Phase 3) |
| **One install, one command** | Pilots die at installation | `pip` build works; `ipo run FILE.pdf` and an offline home page not built (4.1 to 4.3) |
| **Confidential-data handling** | Drafts are price-sensitive | Offline by design; needs a written data-handling statement and tests that prove no network use (exists for the reader) |
| **Source terms** | Data from SEBI, BSE and NSE | Terms-of-use review still open (D-010); fetcher is polite and optional |
| **Support and trust signals** | Banks buy from vendors who answer | Versioned rules with dates, a public accuracy page, a changelog; no support process |
| **Clear commercial position** | Licence and who pays | MIT today; a decision on open core versus paid support is needed before selling |

Order of work, by what unlocks a first paying pilot: (1) text-level checks that save the most reading
(Phase 1.3), (2) `ipo run` and the home page (4.1, 4.2), (3) the issuer-side checks that bankers use
(3.1 to 3.3), (4) the label audit and a lawyer's review of the rules. The first three can be built here;
the audit and the review need people (listed below).

## Where we are (computed, not estimated)

- Reader: parse, extract, verify, cross-check, 12 red-flag rules, HTML report, version diff on
  figures, one-page brief and triage table (`ipo brief`).
- Benchmark: 647 labelled fields over 38 filings, 521/525 present fields correct (99%), 0 wrong,
  4 withheld; held-out sets 8 and 12 read 63/63. First runs on unseen sets: 76% to 100%.
- 849 tests (reader and screening app); CI green; analysis of 40 filings in about 51 s; parsing about 0.65 s per dense page.
- Gaps: only 13 field types are read; no section map; no text-level checks (related parties,
  pledges, litigation, concentration); no issuer-side tools; labels have no second human reader.

## One idea that holds the plan together

Both products sit on the same **verified-data core**: every number and every passage carries its
source (page or input file) and passes a check before it is used. The reader builds that core from
a PDF. The preparer builds it from the company's records. Then the same checks (footing,
cross-table agreement, rule engine, brief) run on either. A draft DRHP produced by the preparer can
be read back by the reader as a final check.

```
           PDF (filed DRHP/RHP)                 company records (CSV/JSON)
                    │                                       │
           parse → extract → verify                 load → validate
                    └──────────────┬────────────────────────┘
                         verified-data core (every item sourced)
                                   │
        ┌──────────────┬───────────┼─────────────┬─────────────────┐
     section map    rules       brief/triage   version diff    DRHP builder
                  (numbers +                                   + filing check
                   text evidence)
```

## Phases, in order

Each item ships only when its **gate** is met. A gate always includes: tests that fail without the
change, `tools/gate.sh` green, no regression on the benchmark, and zero wrong values on a held-out
set where accuracy is measurable.

### Phase 1: Reader that saves an analyst's day (first)

| # | Deliverable | What it gives the reader | Gate |
|---|---|---|---|
| 1.1 | **Check-this list with text spans** | each flagged or withheld item shows the sentence or table row it came from, next to the page link | every span re-found on its page by the verifier |
| 1.2 | **Section map (segmenter)** | pages mapped to the SEBI ICDR Schedule VI sections (risk factors, objects, financial statements, litigation, related parties, promoter group ...) from the table of contents and headings | labelled section start pages on 10 filings; 0 wrong section for a cited page on a held-out set |
| 1.3 | **Text-level evidence checks**, one at a time: related-party transactions as a share of revenue; promoter shares pledged; outstanding litigation (counts and amounts by type); customer and supplier concentration; contingent liabilities; auditor qualifications and emphasis of matter | the reading that takes longest, reduced to numbers and quotes with pages | labels committed before each check runs; zero wrong values on a held-out set; output is evidence plus figures, never a verdict |
| 1.4 | **Brief v2** | the brief gains a section summary and the 1.3 evidence, ranked | restates only verified items (as D-044) |
| 1.5 | **Text diff, DRHP to RHP** | what changed in issue terms, objects, risk factors and litigation, with both pages | changes found on 3 labelled version pairs, none invented |

### Phase 2: Trust (alongside Phase 1)

| # | Deliverable | Why | Needs |
|---|---|---|---|
| 2.1 | **Independent label audit** | every label so far was written by an AI; four labelling errors have been found | a person checks a random sample of about 100 labels; **the owner arranges this** |
| 2.2 | **Held-out set every week** | a one-time measurement per set; keeps the first-run number honest | new public filings (SME prospectus, lenders, unusual layouts first) |
| 2.3 | **Red-team corpus** | hostile PDFs (hidden text, fake tables, conflicting figures) must not produce a wrong value | built here |
| 2.4 | **Scanned filings (OCR)** | some SME filings are scans; today they are reported as unreadable | an offline OCR engine, measured on labelled scanned pages before use |

### Phase 3: Preparer (issuer side, after 1.2 and 1.3 exist)

| # | Deliverable | What it does | Gate |
|---|---|---|---|
| 3.1 | **Input format and loader** | a documented set of CSV/JSON templates for the company's records: restated financials, shareholding and promoter group, litigation list, related-party list, KMP details, objects and costs | every field validated; a missing or inconsistent field is reported with its file and row |
| 3.2 | **Eligibility and arithmetic checks** | ICDR eligibility (mainboard Reg 6(1)/6(2), SME route), minimum promoter contribution and lock-in arithmetic, objects caps (general corporate purposes, unidentified acquisitions), monitoring agency threshold | each clause checked against SEBI's consolidated text before coding, with its effective date (as the existing rules do); tested on published DRHPs whose figures are known |
| 3.3 | **Consistency checker for a draft** | reads a draft DRHP (PDF or DOCX exported to PDF) with the reader and reports numbers that disagree between sections, totals that do not foot, and required disclosures that are missing | zero wrong findings on 5 published DRHPs with planted errors |
| 3.4 | **DRHP builder** | a skeleton in Schedule VI order; tables and summary figures filled from the verified data; every place a lawyer must write is a marked gap | rebuilds the financial tables of 3 published DRHPs from their own statements with every figure matching |
| 3.5 | **Filing-pack checklist** | documents, certificates and formats a submission needs, checked for completeness | reviewed against SEBI's current checklist |

Limits that do not change: the software prepares and checks, it never certifies or files. The lead
manager (a SEBI-registered merchant banker) certifies due diligence and files; misstatement carries
legal liability for the issuer and the signatories. Every preparer output is a draft for
professionals.

### Phase 5: Merge the earlier engine into this product (D-050)

| # | Deliverable | Gate |
|---|---|---|
| M1 | Port the 19 eligibility rules to the TOML engine, each with clause and effective date | same outcome as the engine on its 13 benchmark documents, none declared "eligible" |
| M2 | Review layer: confirm, correct or reject a withheld or flagged item, with a reason and an audit trail | a person's value is never overwritten by a later run |
| M3 | OCR for scanned pages (same as 2.4) | measured on labelled scanned pages first |
| M4 | One front end over the core | no feature lost against the old web app |

Also added to 1.3: a **tax-liabilities** check (disputed tax demands, outstanding amounts), same
rules as the other text checks: labels first, evidence not verdict.

### Phase 4: Make it easy to use

| # | Deliverable |
|---|---|
| 4.1 | One command for the whole reader pipeline (`ipo run FILE.pdf`) that takes a local PDF, no manifest editing |
| 4.2 | A local, offline home page linking every brief, report and diff |
| 4.3 | Install with one command (`pip install` or a single binary); a short guide for analysts |
| 4.4 | A small trial with 2 or 3 analysts on real filings; record which items they used and which they ignored, and re-rank the brief from that |

## What I need from the owner (nothing else blocks the plan)

1. A person to audit about 100 labels (2.1). Without it, "full accuracy" cannot be claimed.
2. For the preparer (Phase 3): sample company records, even anonymised or made up from a published
   DRHP, to test the input format; and if possible a banker or lawyer to review the checklists.
3. Two or three people to try the reader (4.4).

## How progress is reported

- Every change: tests, gate, benchmark unchanged or better; recorded in `docs/decisions.md`.
- Every held-out set: a `docs/heldout-run-N.md` with the first-run numbers, causes and fixes.
- `docs/status.md` and the README carry only numbers computed by `ipo eval`.
- The headline measure stays **wrong values shown on held-out filings: 0**.

## Risks and how they are handled

| Risk | Handling |
|---|---|
| Text-level checks are harder than numbers and could be silently wrong | evidence, not verdicts; labels first; zero-wrong gate on held-out sets; withhold when unsure |
| The benchmark flatters a tool tuned on it | weekly held-out sets; sets that drive no fix stay held out (D-037) |
| AI-written labels hide errors | the human audit (2.1); `--audit-absent` on every absent label |
| Regulations change | every threshold names its clause, effective date and check date; rules expire and are re-checked |
| Preparer outputs mistaken for certified work | every output marked as a draft; no submission features |
| Scope grows faster than accuracy | one deliverable at a time; nothing ships before its gate |
