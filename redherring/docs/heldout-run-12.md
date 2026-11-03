# Held-out run 12 (2026-11-03): a full lender draft, extractor unchanged

Procedure as before (D-021, D-034, D-037, D-038). The roadmap asked for a lender with a balance
sheet. SEBI's current listings had none, but BSE hosts Bajaj Housing Finance's DRHP (7 June 2024,
474 pages): a large mainboard lender with an interest-income P&L, a balance sheet in ₹ million
and a cash-flow statement that begins "Net cash (used in) operating activities (I)". Its 20 labels
were committed (`c392233`) and only then was the extractor run, with the code exactly as it stood
after run 11. Every "absent" label was audited against all matching lines first (the monitoring
agency is "will appoint" throughout; the only object is Tier I capital, with no general corporate
purposes line).

| | held-out set 12, first run |
|---|---|
| labelled fields | 20 (17 present, 3 absent) |
| value accuracy | 17/17 (100%) |
| citation accuracy of correct values | 17/17 |
| abstained | 0/17 |
| wrong value | 0/17 |
| hallucinated (value for an absent field) | 0/3 |

First runs so far: 76%, 76%, 97%, 54%, 87%, 87%, 100%, 100%, 89%, 95%, 57% (a one-page-type
abridged prospectus), 100%.

## What this shows and does not show

No extractor change was made, so set 12 is **still held out** (D-037), alongside set 8: the two
held-out sets together read 63/63. This is the first full lender filing since set 9 (Aadhar Housing
and Neev Credit) and it was read without a miss, including a lender's unusual cash-flow label and
interest-income revenue breakdown. It is one filing with three fiscal-year columns and no
standalone/consolidated mix, so it does not test the cases that cost accuracy earlier (lost header
cells, unitless tables, a restated column set). SME prospectuses (as distinct from drafts) are still
untested since set 2; none was found in public listings today.
