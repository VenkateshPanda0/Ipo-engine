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
| One-page HTML report per filing, figures linked to PDF pages | done (`rh report`) |
| Further rules: related-party, concentration, pledges, auditor, litigation, valuation | not started |
| Prompt-injection red-team set (hostile PDFs through parse and extract) | started: four end-to-end cases in `tests/test_redteam.py` plus hidden-text tests; no corpus of real attack PDFs |

## Next, in order
Priority follows the product aim in `CHARTER.md` and D-043 (never silently wrong; least reading time).
1. One-page brief per filing (`rh brief`): issue, use of proceeds, key financials and trend, flags, what
   could not be checked, ordered by what to read first, every line linked to its PDF page. Then a
   triage table across filings (flag counts, withheld items, one row per filing).
2. A "check this" list for every flagged or withheld item: the exact page and the text span.
3. Segmenter (map pages to ICDR sections) and the first text-level rules (related-party transactions,
   promoter pledges, litigation, customer concentration), each with labels committed before they run.
4. Version diff on text (DRHP to RHP: issue wording, objects, risk factors, litigation).
5. An independent human check of a sample of labels (no label has had a second reader), then held-out
   sets 13 onward: an SME prospectus (not a draft) and filings that mix consolidated and standalone
   columns or lose a header cell. Sets 1 to 7 and 9 to 11 are development data; sets 8 and 12 are held out.
6. Red-team PDFs; OCR for scanned filings (no scanned test document yet).
7. Outcome backtest only with written hypotheses and a price source whose terms allow it.

## Version diff (M3)
| Item | State |
|---|---|
| Figure-level diff between versions (`rh diff`), restatements and issue-size changes | done; two pairs exercised (Indiqube DRHP to RHP: issue cut from 8,500 to 7,000 million; Vishal UDRHP-I to RHP: nothing moved) |
| Text-level diff (risk factors, objects wording, litigation) | not started; needs the segmenter |
| Abridged-prospectus consistency | not started; count post-March-2026 filings first |

## Outcomes (M4)
Not started; see above.
