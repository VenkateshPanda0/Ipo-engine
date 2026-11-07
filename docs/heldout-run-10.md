# Held-out run 10 (2026-11-01): three unseen sectors, one disputed label

Procedure as before (D-021, D-034, D-037, D-038). Paramotor Digital Technology UDRHP-I (an updated
draft whose columns mix consolidated and standalone statements), Bombay Coated and Special Steels
RHP and SFC Environmental Technologies RHP were taken from SEBI's current listings (still no
lender there; a lender found through search had no retrievable primary PDF). Their 52 labels were
committed (`9a29e5d`) and only then was the extractor run, with the code as it stood after run 9.
Every "absent" label was audited against all matching lines first. Paramotor's profit lines were
not labelled (continuing and total results differ and its cash-flow statement was not found in the
text), so its 12 labels cover the issue and three balance and income figures.

| | held-out set 10, first run |
|---|---|
| labelled fields | 52 (41 present, 11 absent) |
| value accuracy | 39/41 (95%) |
| citation accuracy of correct values | 31/39 (79%) |
| abstained | 2/41 |
| wrong value | 0/41 |
| hallucinated (value for an absent field) | 1/11 (disputed, below) |

First runs so far: 76%, 76%, 97%, 54%, 87%, 87%, 100%, 100%, 89%, 95%.

## The disputed "invention"

Bombay Coated's cover table puts "aggregating up to ₹1,830.57 million" in the row headed Fresh Issue,
but its page 3 says "FRESH ISSUE OF UP TO [●] EQUITY SHARES AGGREGATING UP TO ₹[●] MILLION"
while giving the whole issue as ₹1,830.57 million. The whole issue is fresh (the offer for sale is
"Not Applicable"), so the fresh issue equals the total in substance, but no fresh-issue amount is
printed. I labelled the fresh issue absent before the run, noting the ambiguity; the extractor read
the cover table's amount as the fresh issue. I kept the label as committed rather than change it to
match the tool, so the first-run figures above count this as an invention. Read the other way it
is a correct reading, and the set would be 39/41 with 0 invented.

## Cause of the two abstentions and the fix

Paramotor's FY2025 and FY2024 statements are standalone (the company only consolidated from FY2026),
so every FY2025 column is headed "(Standalone)". The consensus gave such columns weight zero (a
standalone figure beside a consolidated one is another entity's, D-033), which left the Previous-GAAP
restatement (1,122.40, not qualified) as the only weighty reading; revenue and total income for FY2025
were withheld. Fix: the qualifier discount applies only where some reading of the figure carries no
qualifier, and "Previous GAAP" now counts as a qualifier; a test reproduces it and fails without the
fix. After the fix: 41/41 correct (100%), 0 wrong, 1 disputed. The 30 development filings did not
change (410/414). Set 10 is now development data; set 8 still reads 46/46 and stays held out.

SEBI's current listings continue to have no lender, so the lender gap (set 9 was the last) is still
open.
