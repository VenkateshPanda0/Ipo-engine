# Roadmap

Status key: done / partial / not started. The numbers behind "partial" live in `status.md`.
Updated 2026-10-24.

## Foundation (M0): done
Fetcher with integrity checks, page-tagged parser, tables, units, CLI, CI, decision log.

## Extraction (M1)
| Item | State |
|---|---|
| Parser quality on real filings | partial: nine filings, 0 error pages; unit missing on ~60% of tables |
| Period parsing | done (fiscal labels, "As at" mislabels, reversed years) |
| Financial statement extractor with citations | partial: seven concepts plus borrowings/net worth (unreliable) |
| Label-free checks (citation re-read, footing, cross-table consensus, column trust) | done |
| Issue facts and objects (amounts, GCP, unidentified acquisitions, monitoring agency) | done for stated amounts; placeholders never read |
| Sector detection (lender, real estate) | done, calibrated on nine filings |
| Segmenter (map pages to ICDR sections) | not started |
| LLM layer | removed on the owner's instruction (D-042): the software is deterministic and runs offline |
| Labels, validator, eval harness with dev and held-out splits | done; 133 fields on nine filings |
| OCR for scanned pages | not started; no scanned test document yet |

## Red flags (M2)
| Item | State |
|---|---|
| Rule specs (TOML), engine, audit, validity windows, sector exclusions | done |
| Shipped rules | twelve (nine regulatory with clause and date, three heuristic) |
| One-page HTML report per filing, figures linked to PDF pages | done (`ipo report`) |
| Further rules: related-party, concentration, pledges, auditor, litigation, valuation | not started |
| Prompt-injection red-team set (hostile PDFs through parse and extract) | started: four end-to-end cases in `tests/test_redteam.py` plus hidden-text tests; no corpus of real attack PDFs |

## Next, in order
Done 2026-11-13 (D-059, release 0.3.0): `ipo run`, the home page, the related-party check in the brief and report, the reader inside the web app. Now, in order: (a) labels, then code, for related-party tables that print percentages without a % sign (Runwal, Tonbo, Nityas); (b) the next text check, outstanding litigation, labels first; (c) Phase 5 M1, one figure family of the screening app moved onto the reader, scored on the screening benchmark; (d) a new held-out set for the core extractor.
The full plan, with gates and what each phase needs, is `docs/plan.md` (2026-11-07). The list below is
its Phase 1 and 2 order.
Priority follows the product aim in `CHARTER.md` and D-043 (never silently wrong; least reading time).
1. [first version built 2026-11-07: `ipo brief`, `brief.py`, 8 tests; next: user feedback on the ordering, and the "check this" list with text spans] One-page brief per filing (`ipo brief`): issue, use of proceeds, key financials and trend, flags, what
   could not be checked, ordered by what to read first, every line linked to its PDF page. Then a
   triage table across filings (flag counts, withheld items, one row per filing).
2. [built 2026-11-07, D-047: table rows with pages under each flag and withheld figure; text-sentence spans come with the section map] A "check this" list for every flagged or withheld item: the exact page and the text span.
3. [related-party check v2 2026-11-12, D-057: 0 wrong, 4 of 10 labelled filings resolved, 2 more partial or no-percentage; next: blind labels on unseen filings, then wire into the brief] [segmenter built 2026-11-07, D-048, 29/29 labelled start pages; next: use it in the brief and the first text-level rule] Segmenter (map pages to ICDR sections) and the first text-level rules (related-party transactions,
   promoter pledges, litigation, customer concentration), each with labels committed before they run.
4. Version diff on text (DRHP to RHP: issue wording, objects, risk factors, litigation).
5. An independent human check of a sample of labels (no label has had a second reader), then held-out
   sets 13 onward: an SME prospectus (not a draft) and filings that mix consolidated and standalone
   columns or lose a header cell. Sets 1 to 7 and 9 to 11 are development data; sets 8 and 12 are held out.
6. Red-team PDFs; OCR for scanned filings (no scanned test document yet).
7. Outcome backtest only with written hypotheses and a price source whose terms allow it.

## Issuer-side track (owner request, 2026-11-07): prepare a filing, not only read one
The owner wants a system that also does the work before a filing: due diligence on the company,
drafting the DRHP, and preparing the filing. Same rules as everything else here (offline, no language
model, never silently wrong, page- or source-cited). Three stages, each shipping only after it has
been checked against filings that were actually made:
| Stage | What it does | Input | State |
|---|---|---|---|
| 1. Due-diligence checks | Deterministic checks on the company's own records: ICDR eligibility tests (Reg 6(1) track record, net worth, monetary assets), financial statements foot and reconcile, promoter holding and lock-in arithmetic, litigation and related-party lists complete and consistent, tax and compliance checklists | company records (financial statements, litigation list, shareholding, KMP details) as structured files | not started; design first |
| 2. DRHP builder | Follows the ICDR Schedule VI order; fills the tables and summary figures from the verified data; flags every required disclosure that is missing; cross-checks that a number means the same thing in every section | stage 1's verified data plus text written by the lawyers | not started |
| 3. Filing pack check | A checklist of the documents, certificates and formats a submission needs, validated for completeness and consistency | the draft and its annexures | not started |
Limits that stay: the software prepares and checks; it does not certify. Due-diligence certificates and
the submission are the lead manager's (a SEBI-registered merchant banker) responsibility, and a
prospectus misstatement carries legal liability for the issuer and the signatories, so every output is a
draft for professionals to review. Nothing is submitted to SEBI, the exchanges or the RoC automatically.

## Version diff (M3)
| Item | State |
|---|---|
| Figure-level diff between versions (`ipo diff`), restatements and issue-size changes | done; two pairs exercised (Indiqube DRHP to RHP: issue cut from 8,500 to 7,000 million; Vishal UDRHP-I to RHP: nothing moved) |
| Text-level diff (risk factors, objects wording, litigation) | not started; needs the segmenter |
| Abridged-prospectus consistency | not started; count post-March-2026 filings first |

## Outcomes (M4)
Not started; see above.
