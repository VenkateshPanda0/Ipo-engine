# RedHerring

**A forensic reader for Indian IPO offer documents.** Give it a DRHP, RHP or Prospectus; it gives
back the numbers that matter, each tied to the PDF page it came from, and a short list of
diligence flags with the evidence beside them. Where it cannot be sure, it says nothing rather
than guess.

> Not investment advice. This is automated analysis of public filings. Verify every figure
> against the source document; each one links to its page.

---

## Why it exists

An offer document runs to 400 to 1,500 pages. The facts a reader needs (how much is fresh issue
versus offer for sale, how much of the money is "general corporate purposes", whether profits turn
into cash, whether receivables are outrunning sales) are spread across the cover, the summary, the
objects section and the restated financial statements, often printed several times and sometimes
inconsistently. RedHerring reads all the copies, checks them against each other, and shows its
work.

## Runs completely offline

The software contains no language model, no model client and no API key. Parsing, extraction,
verification, the rules, reports and the benchmark all run on the local machine with no network
access. The one exception is `rh ingest`, which downloads public filings listed in
`data/sources.toml`; if you already have the PDFs, place them in `data/raw/` and skip it.
`tests/test_offline.py` fails if any other module imports a network or model library.

## What you get

For each filing, `rh report` writes one self-contained HTML page:

- **Issue and objects**: fresh issue, offer for sale, total size, general corporate purposes,
  unidentified acquisitions, debt repayment, monitoring agency, eligibility route (Reg. 6(1) or
  6(2)).
- **Annual figures in ₹ crore**: revenue, total income, profit before and after tax, total assets,
  operating cash flow. Every number links to the PDF page it was read from.
- **Flags with evidence**: what was tested, the figures used, the threshold, and the clause or
  paper behind the threshold.
- **What could not be checked**: missing inputs, withheld figures, pages with hidden text.

`rh brief` writes a **one-page brief per filing** and a **triage table** across filings. The brief states
the issue and the latest financials, then a ranked "read first" list; every item names the exact PDF
page to open. It lists figures the document's tables disagreed on instead of showing them, groups
the rules that could not run, and counts older-year withheld figures rather than listing them.
`rh brief --text` prints a brief in the terminal. It only restates what the analysis already verified,
so it adds no new way to be wrong.

`rh diff OLD NEW` compares two versions of one offering (for example a DRHP and its RHP) figure by
figure and shows what changed in issue size, restated numbers and flags.

## How it avoids being confidently wrong

| Principle | What it means in practice |
|---|---|
| **Cite or stay silent** | Every extracted value carries a page number and the text span it came from. After extraction the span is re-read from the PDF; a value that cannot be found on its cited page is discarded. |
| **Cross-check the filing against itself** | A total income that appears in four tables must agree across them. Statement columns are tested for footing (assets = equity + liabilities; total income = revenue + other income; profit = PBT − tax). Disagreement is shown, not resolved by guesswork. |
| **Prefer the issuer's own figures** | Subsidiary and peer statements foot just as well as the issuer's. Readings from the front of the document count more; columns headed "excluding", "standalone" or "subsidiary" count for nothing; a subsidiary figure cannot beat a group figure for size measures. |
| **Abstain when definitions conflict** | Where a filing prints owners' profit in one table and total profit including minority interests in another, the tool declines to pick one. |
| **Thresholds say where they come from** | A regulatory threshold names the SEBI ICDR clause, its effective date and the date it was last checked. A heuristic says it is a heuristic. Rules are not applied to a filing the rule was not in force for, nor to sectors where the test means something else (cash-flow tests skip lenders and developers). |
| **Untrusted input, no language model** | Offer documents are treated as hostile text. Text a reader cannot see (tiny, off-page, white on white) is dropped or flagged, and facts resting on it are kept out of the rules. There is no language model anywhere in the software, so there is nothing for injected text to instruct. See `docs/security.md`. |

## Red-flag rules

Twelve rules, each a TOML file in `src/redherring/flags/rules/`:

| Area | Rule | Severity |
|---|---|---|
| Financials | Operating cash flow persistently below reported profit | medium |
| Financials | Trade receivables growing much faster than revenue | medium |
| Objects | No monitoring agency although the issue is above the threshold (mainboard, SME, SME before 8 Mar 2025) | high |
| Objects | General corporate purposes close to the regulatory cap (mainboard, SME, SME before 8 Mar 2025) | medium |
| Objects | General corporate purposes plus unidentified acquisitions close to the combined cap | medium |
| Objects | Unidentified acquisitions close to their own cap | medium |
| Objects | More than half of the fresh issue repays borrowings (heuristic) | low |
| Issue | Offer for sale close to the SME limit | medium |

A flag is a prompt to read the cited pages, not a verdict.

## How well does it work?

Measured, not claimed. `rh eval` scores the extractor against **647 hand-labelled fields (525
present, 122 deliberately absent) across 38 filings**: mainboard RHPs and DRHPs, SME drafts and
prospectuses, lenders, an abridged prospectus. Current results, all computed by `rh eval`:

| | Filings | Present fields read correctly | Wrong | Withheld | Invented (of absent) | Citation on a labelled page |
|---|---|---|---|---|---|---|
| All filings | 38 | 521/525 (99%) | 0 | 4 | 1/122 (disputed, below) | 449/521 (86%) |
| Development (used to fix defects) | 34 | 458/462 (99%) | 0 | 4 | 1/105 | 390/458 (85%) |
| Held out (never used for a fix) | 4 | 63/63 (100%) | 0 | 0 | 0/17 | 59/63 (94%) |

The citation column is a stricter label check: the page the tool cites must be one the labeller
listed for that figure. Every cited figure is also re-read from its page by a second code path
before it is reported, so the misses are mostly pages that print the figure but are not in a label's
page list. The four withheld fields are definitional conflicts (owners' profit against total profit;
continuing against total operations) and one table with no unit; the tool declines to guess.

### The honest number: the first run on filings it had never seen

Development accuracy flatters any tool that has been fixed against its own test set. The number to
trust is the **first run on each new set of filings, with labels committed before the extractor ran**:

| Set | Filings | Correct, first run | Wrong | Invented |
|---|---|---|---|---|
| 1 | Indiqube, Laxmi India Finance, Vishal Mega Mart | 31/41 (76%) | 4 | 0/10 |
| 2 | LEAP India, Shiprocket, Indong Tea | 32/42 (76%) | 2 | 0/7 |
| 3 | Powerica, SRIT India, Veritas Finance | 38/39 (97%) | 0 | 0/11 |
| 4 | Lenskart, Tata Capital, PhysicsWallah | 21/39 (54%) | 3 | 3/12 |
| 5 | Zetwerk, Tonbo Imaging, Paras Healthcare | 33/38 (87%) | 1 | 2/13 |
| 6 | Shah Investor's Home, Orient Cables, Nityas Gems | 40/46 (87%) | 0 | 0/12 |
| 7 | Sahajanand Medical, Fusion CX, Swastika Infra | 49/49 (100%) | 0 | 2/11 |
| 8 | Carlsberg India (UDRHP-I), Inox Air Products, Electromech Infra (drafts) | 45/45 (100%) | 0 | 1/15* |
| 9 | Neev Credit (SME draft, lender), Aadhar Housing (lender), Spinaroo (SME draft) | 42/47 (89%) | 1 | 0/7 |
| 10 | Paramotor Digital (UDRHP-I), Bombay Coated Steels, SFC Environmental | 39/41 (95%) | 0 | 1/11** |
| 11 | HDB Financial Services (lender; abridged prospectus) | 4/7 (57%) | 0 | 0/2 |
| 12 | Bajaj Housing Finance (lender; full DRHP) | 17/17 (100%) | 0 | 0/3 |

\* a labelling error, not an extractor error (`docs/heldout-run-8.md`). \*\* a judgement call on a
cover table, counted as an invention here; read the other way it is correct (`docs/heldout-run-10.md`).

Read it as a trend, not a promise. The early sets, with long filings and many subsidiary statements,
read about three fields in four; the later, mostly clean modern filings read nine in ten or better;
the one-document abridged prospectus (set 11) is too small to mean much. Sets 8 and 12 needed no code
change, so they stay held out and still read 63/63 together.

Caveats you should know about:

- **A set is a one-time measurement.** Once its failures are fixed it becomes development data, so
  twelve sets of one to three filings is a modest, non-random sample.
- **Labels have no second reader.** They were written by an AI reading the PDFs with a different
  tool. Four of the early "invented values" were the labeller's errors, all disclosed (sets 4, 5 and
  8); `tools/label_build.py --audit-absent` now lists every line that could contradict an "absent" label.
- **Hard structures remain the risk:** lost header cells, tables with no unit, mixed consolidated and
  standalone columns. Each has cost accuracy before and has a fix and a test, but the next filing may
  have a new one. Lenders, SME prospectuses (as opposed to drafts) and scanned filings are the least tested.

## Quick start

```bash
cd redherring
uv sync
uv run rh --data-dir data ingest        # fetch the filings listed in data/sources.toml (polite, hashed)
uv run rh --data-dir data parse         # PDF -> page-tagged text and tables
uv run rh --data-dir data analyze       # extract, verify, cross-check, run rules
uv run rh --data-dir data report        # HTML per filing in data/reports/
uv run rh --data-dir data brief         # one-page brief per filing + triage table
uv run rh --data-dir data diff OLD NEW  # compare two versions of an offering
uv run rh --data-dir data eval --labels-dir labels
```

Add a filing by appending a `[[document]]` entry to `data/sources.toml` with its public URL.
Python 3.12, `uv`, Pydantic v2, pdfplumber and pypdfium2 (permissive licences; PyMuPDF is avoided
because it is AGPL).
`tools/gate.sh` runs format, lint, type-check and tests and returns the real exit status;
`tools/README.md` describes the labelling helpers.

## How it works

```
PDF ──► parse ──► extract ──► verify ──► rules ──► report / diff
        │          │           │          │
        │          │           │          └ TOML specs, dated, sector-aware, audited
        │          │           └ re-read cited page; footing identities; cross-table consensus
        │          └ statement lines, issue facts, objects tables, each with page + span
        └ text blocks, ruled and unruled tables, units, column headers, hidden-text defence
```

Source layout: `src/redherring/{ingest,parse,extract,verify,flags,eval}`, with `analyze.py` tying the
stages together and `report_html.py` and `diff.py` producing the outputs.

## Documentation

| | |
|---|---|
| `docs/status.md` | Every current number and known defect |
| `docs/heldout-run-1.md` … `-12.md` | Each held-out run: what failed, why, what changed |
| `docs/decisions.md` | Design decisions and their trade-offs |
| `docs/security.md` | Threat model for untrusted PDFs |
| `docs/roadmap.md` | What is done and what is next |
| `docs/CHARTER.md` | How the project is run |

## Data hygiene

Only public filings are fetched, with robots.txt respected, a per-host rate limit and a descriptive
User-Agent. Source URLs and SHA-256 hashes are recorded. PDFs, parsed outputs, labelling text caches
and the generated report and brief pages are git-ignored: regenerate them with `rh parse`, `rh
analyze`, `rh report` and `rh brief`.

This folder is independent of the rest of the repository (see `docs/decisions.md` for why, and how
to split it out).

## Licence

MIT (see `LICENSE`).
