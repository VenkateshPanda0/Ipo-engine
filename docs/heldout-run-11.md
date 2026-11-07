# Held-out run 11 (2026-11-02): a lender, and a new document type

Procedure as before (D-021, D-034, D-037, D-038). SEBI's current listings still had no lender, and
for the lenders the web search found (Truhome, InCred) no primary PDF could be retrieved. HDB
Financial Services' abridged prospectus (12 pages, dated by its cover to the RHP of 19 June 2025,
hosted by a book running lead manager) was available, a document type no earlier set used. Its 9
labels were committed (`b9b2d13`) and only then was the extractor run. An abridged prospectus
carries the issue size, objects and a three-year summary; it has no balance sheet or cash-flow
statement, so only the issue amounts and two income-statement lines are labelled (the
objects amount is [●] and there is no general-corporate-purposes line).

| | held-out set 11, first run |
|---|---|
| labelled fields | 9 (7 present, 2 absent) |
| value accuracy | 4/7 (57%) |
| citation accuracy of correct values | 4/4 |
| abstained | 3/7 |
| wrong value | 0/7 |
| hallucinated (value for an absent field) | 0/2 |

This is a single short document, so the percentage is noisy: the miss is all three issue amounts.

## Cause and fix

The document prints the rupee sign as a backtick ("aggregating to `100,000.0 million"), which the
issue-amount patterns did not accept (the unit parser already did). All three issue amounts
(fresh 25,000.0, offer for sale 100,000.0, total 125,000.0 million) were withheld; the profit
after tax figures from the KPI table were read correctly. Fix: the backtick is a currency sign in the
fresh issue, offer for sale and total patterns, with a test that fails without it. After the fix the
set reads 7/7 and the 36 earlier filings did not change (504/508 over all 37). Set 11 is development
data; set 8 still reads 46/46 and remains the held-out set.

Not tested by this set: a full lender RHP with a balance sheet and loan-book disclosures after set
9's two lenders. SME prospectuses (as distinct from SME drafts) are also still untested since set 2.
