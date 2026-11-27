# Agent report: functional / business-logic and edge-case correctness

Branch: audit/remediation-2026-11. Date: 2026-11-27. Tester: independent QA agent (logic).
No tracked file was modified; nothing committed. Throwaway scripts are in /tmp/agent_logic/ (t1..t5.py).

## Scope

Read: src/ipo_engine/numfmt.py, diff.py, analyze.py, extract/{periods,financials,models,consensus}.py,
verify/{footing,cited}.py, flags/{engine,facts,spec}.py and the TOML rules, parse/units.py (unit scaling
and number parsing, which the brief names indirectly via "Rs. in million").

Not read or not exercised (see Limitations): segment.py, brief.py, checks/{litigation,related_party}.py,
extract/issue.py, extract/sector.py, eval/*, screening/{engine,rules,regulatory,reports}.
The effort cap (about 45 tool calls, then a reduced budget after a rate-limit stop) ended the review before them.

## Method

Hand-written probes of the pure functions, a Hypothesis round-trip property (3000 examples) and a
sign property (2000 examples), synthetic `Fact` / `CitedNumber` / `FactRecord` objects pushed through
`evaluate`, `audit`, `build_consensus`, `facts_from` and `diff_reports`, input-permutation checks, and a
PYTHONHASHSEED/TZ/LANG run. No real DRHP PDF was parsed. Defects below were reproduced on the code as
checked out; the "end to end" ones go from header text to the fact key the rules use.

## Checks and results

| # | Check | Result |
|---|-------|--------|
| 1 | `indian()` lakh/crore grouping, negatives, ROUND_HALF_UP, zero places | Not Found (correct for 12345678.5, -0.005, 999999.995 -> 10,00,000.00, 2.5 -> 3, -2.5 -> -3) |
| 2 | `parse_amount(indian(x, p)) == x.quantize(p)` Hypothesis, 3000 cases, values up to 1e15 | Not Found (round-trip holds) |
| 3 | `pct()` sign/rounding, negative zero | Not Found (-0.04 -> "0.0%", never "−0.0%"; Hypothesis passes) |
| 4 | `indian`/`crore`/`pct` with NaN, Infinity, 28+ digit values | Confirmed, minor (F8) |
| 5 | `parse_amount`: parentheses, ASCII/Unicode minus, Rs/INR/₹, Nil/dash/NA, footnote marks, percent, NaN/Infinity text | Not Found for the listed forms. Strings such as "(1,234", "1,234-", "₹(1,234)", "1e5", "NaN" abstain (None). |
| 6 | `parse_amount` digit-group validation | Confirmed (F7) |
| 7 | Unicode digits (Devanagari, Arabic-Indic, full-width) | Not Found: "१२,३४५" parses to 12345, which is the correct value |
| 8 | `detect_unit` common captions (lakhs, Rs. in million, ₹ in 000, INR Mn, crore, lacs, '000) | Not Found (correct) |
| 9 | `detect_unit` currency handling, mixed-unit captions, substring matches | Confirmed (F3, F4, F6) |
| 10 | `parse_period` standard headers (year ended, FY 2023-24, Fiscal 2024, six/nine months, quarter, as at, dd-mm-yyyy, invalid 29 Feb) | Not Found (correct, or abstains with None) |
| 11 | `parse_period` abbreviated and non-standard durations | Confirmed (F1, F2, F5) |
| 12 | Ratio-vs-cap boundaries (exactly at cap, +/-0.01, den 0, den negative, abs_cap, near-cap 0.9) | Not Found for the decision logic: ratio == cap is "close", > cap is "above", den <= 0 abstains as missing_inputs, SME abs_cap of Rs 10 crore applied. Explanation text rounding: Confirmed (F9). |
| 13 | required_if boundary (threshold exactly, +0.01) | Not Found (strict >, equal does not flag) |
| 14 | growth_gap boundaries (gap exactly 20pp flags, 19.99 does not, negative base abstains, non-consecutive years abstain, min_base_ratio) | Not Found |
| 15 | persistent_below with a missing year | Confirmed (F10) |
| 16 | Rule validity windows (`valid_from`, pre-2025-03-08 SME rule) | Not Found: as_of 2025-03-07 gives not_in_force. Without `as_of` the rule set depends on `date.today()` (see Limitations, L3). |
| 17 | diff: identical, reordered, empty vs empty, one side empty, window shift, zero and negative base pct | Not Found for the logic as written: reordered gives 0 moved; zero base gives pct None; negative base uses abs(); a shifted window is period_only, not moved |
| 18 | Consensus input-order independence of the chosen figure | Not Found for the decision (same fact in every permutation); the chosen citation varies (F11) |
| 19 | Consensus ties and chains (100.00 / 200.00 equal weight; 100.00..100.03) | Not Found: no fact is kept when readings split evenly, so the engine abstains |
| 20 | Determinism: same input twice; PYTHONHASHSEED 0 vs 1; TZ/LANG | Inconclusive. The script output differed between seeds only because the script prints a Python set; the engine functions tested are order-stable. Not run on a full PDF. |
| 21 | Floats: money paths | Not Found: Decimal throughout. Rule caps use Decimal(str(float)), so 0.25 is exact. |

## Confirmed findings

### F1 (P2). "Q1/H1/9M FY20xx" headers are read as a full 12-month fiscal year
- File: src/ipo_engine/extract/periods.py:35-38 (`_THREE/_SIX/_NINE/_TWELVE`), :116 (`elif from_fiscal or _TWELVE...`).
- Root cause: only the spelled-out words ("three months", "quarter", "half year", "9 months") set a short duration. Abbreviations "Q1", "H1", "1H", "9M", "6M", "3M" do not match, and the FY token then forces `months = 12`.
- Reproduction (end to end, a one-cell CitedNumber with raw "12.50", unit crore, passed through `build_consensus` and `facts_from`):
  - header "Q1 FY2025" gives period end 2025-03-31, months 12, fiscal_key FY2025, fact `financials.revenue_from_operations.FY2025` = 125000000.00.
  - The same output for "H1 FY2025", "9M FY2025", "Q3 FY 2024-25", "H1 FY 2024-25", "6M FY2025", "3M FY2025", "1H FY2025".
- Expected: months 3/6/9 and key `3M-2024-06-30` etc., or None (abstain). Observed: a part-year figure becomes the FY2025 figure with confidence boosted by `period_has_duration`.
- Impact: a lone quarterly or half-year reading passes `_keep` (total == 1) and feeds growth_gap and persistent_below as a full year. Real issuers print such labels in KPI tables.
- Fix: add `\b(?:q[1-4]|h[12]|[12]h|[369]m)\b` patterns, and where the header names a fiscal year plus an unrecognised short-period token, return months=None (abstain). Also make `fiscal_key` refuse `months=None` for headers that contained any such token.

### F2 (P2). An explicit non-12-month duration ("15 months", "18 months") is ignored and mapped to the fiscal year
- File: src/ipo_engine/extract/periods.py:111-118 and :141 (`fiscal_key` maps months in (None, 12) at 31 March to FY).
- Reproduction: `parse_period("For the 15 months ended March 31, 2023")` gives end 2023-03-31, months None, fiscal_key "FY2023". Also "18 months ended March 31, 2024" gives FY2024, and "Stub period ended March 31, 2024" / "For the period ended March 31, 2025" give FY keys.
- Expected: abstain or key `15M-2023-03-31`. Observed: the 15-month figure is stored as FY2023 revenue and fed to growth rules.
- The docstring says an unknown duration is kept unknown, but `fiscal_key` then promotes it to a full year. That design assumption is only safe for a date-only header, not for one that states another duration. Companies that change fiscal year end do print "15 months".
- Fix: detect `\b\d{1,2}\s*months?\b` with a value other than 12 and set months to that number; treat "period"/"stub" without a duration as months=None and exclude from `fiscal_key` promotion.

### F3 (P2). `detect_unit` ignores the currency, so a USD table is scaled as rupees
- File: src/ipo_engine/parse/units.py:55-62 (pattern 1 has an optional `_CURRENCY`).
- Reproduction: `detect_unit("(US$ in million)")` returns (MILLION, "in million"); `detect_unit("(USD in thousands)")` returns THOUSAND. Fed through facts_from with raw "12.50", this gives 12,500,000 "rupees". "(US$ million)" abstains (None), so the behaviour is inconsistent.
- Expected: None (unknown unit, abstain) for a non-INR caption. Observed: dollar figures enter the rules as rupees (about 83x understated).
- Fix: if the caption holds a non-INR currency token (US$, USD, $, EUR, GBP) return None; or carry currency in `Unit`/`CitedNumber`.

### F4 (P3). A caption declaring two different units silently takes the first
- File: src/ipo_engine/parse/units.py:65-75 (first match wins).
- Reproduction: `detect_unit("(₹ in Crore) (₹ in Lakhs)")` gives CRORE; `detect_unit("(Amounts in Rs. Lakhs, unless stated, except Rs. in Crore)")` gives LAKH. Expected: None (ambiguous) or at minimum a flag. Error factor 100x if the table is in the second unit.
- Fix: collect all matches in the header text; if more than one distinct unit, return None.

### F5 (P3). Date range headers take the start date as the period end
- File: src/ipo_engine/extract/periods.py:99 (earliest date by text position is used as `end`).
- Reproduction: `parse_period("For the period from April 1, 2023 to March 31, 2024")` gives end 2023-04-01, key "?-2023-04-01" (should end 2024-03-31). "Period from July 12, 2022 to March 31, 2023" gives end 2022-07-12. Also "Fiscal 2025 six months ended September 30, 2024" gives end 2025-03-31, months 6, key "6M-2025-03-31" (the real end is 2024-09-30).
- Observed effect: the value falls into a nonsense key and drops out of FY series (data loss, not a wrong number), except where the key collides.
- Fix: for "from X to Y" / "to" ranges take the later date as the end; when two dates appear, prefer the one after "ended"/"to".

### F6 (P4). Unit regex matches "rs" inside ordinary words
- File: src/ipo_engine/parse/units.py:56-62 (pattern 2 has no `\b` before the currency).
- Reproduction: `detect_unit("Particulars cr")` gives CRORE (matched text "rs cr"); "Directors mn" and "Total borrowers million" give MILLION. Requires a word ending in "rs" directly before a unit word, so rare. Fix: add `\b` before `_CURRENCY` in pattern 2.

### F7 (P4). `parse_amount` accepts malformed digit grouping
- File: src/ipo_engine/parse/units.py:113 (`\d{1,3}(?:,\d{2,3})*`).
- Reproduction: "1,234,56" gives 123456; "12,50" gives 1250; "1,23,45,678" gives 12345678 (the last is valid Indian grouping; the first two are not valid in either system). A European-style "12,50" or a dropped digit produces a number 100x off with no abstention.
- Fix: validate either Western (`\d{1,3}(,\d{3})*`) or Indian (`\d{1,2}(,\d{2})*,\d{3}`) grouping, and abstain on mixed.

### F8 (P4). `indian`/`crore`/`pct` raise on NaN, Infinity and values over 28 digits; negative `places` gives a trailing dot
- File: src/ipo_engine/numfmt.py:20-36, 51-54.
- Reproduction: `indian(Decimal("NaN"))`, `indian(Decimal("1e30"))`, `crore(Decimal("1e40"))`, `pct(Decimal("Infinity"))` raise decimal.InvalidOperation; `indian(Decimal("1234567.5"), -2)` returns "12,34,600." . No silent wrong number, but a crash instead of an abstaining dash. Unlikely from the pipeline (values come from parse_amount, which rejects NaN).

### F9 (P3). Explanation text can contradict its own verdict through rounding
- File: src/ipo_engine/flags/engine.py:142 and :149 (`f"{ratio:.0%}"`, Decimal uses half-even).
- Reproduction: GCP 254 of fresh issue 1000 (mainboard) gives "25% against a limit of 25%; the figure is above it." (ratio 25.4%). SME with GCP 100,000,001 of 1,000,000,000 gives "10% against a limit of 10%; the figure is above it." GCP 225/1000 gives "22% against ... close to it" (22.5% rounds to 22).
- Expected: enough precision to show why (for example one decimal, or "25.4%"). The `numbers` dict holds the exact ratio, so only the sentence misleads. A regulator-facing reader sees "25% vs 25%, above it".
- Fix: format with `.1%` (or two decimals when the rounded values are equal).

### F10 (P3). `persistent_below` does not require consecutive years but the text says "last N years"
- File: src/ipo_engine/flags/engine.py:176 (`sorted(set(left) & set(right))[-min_periods:]`) vs :193 (text). `growth_gap` does check consecutiveness (`_consecutive_fiscal_years`); this rule does not.
- Reproduction: FIN-CFO-BELOW-PAT with cash_from_operations and profit_after_tax present for FY2021, FY2023, FY2024 only (CFO 1/5/5 against PAT 8/10/10) raises "below in 3 of the last 3 years (FY2021, FY2023, FY2024)". FY2022 is missing and is described as if absent from the window.
- Expected: abstain (missing_inputs) or word it as "the three latest years with data", as a three-year gap can hide a good year.
- Fix: require consecutive FY keys like `_growth_gap`, or reword the explanation to list the actual years and say the series has a gap.

### F11 (P4). Chosen citation depends on input order among equal readings
- File: src/ipo_engine/extract/consensus.py:205 (`min(best, key=(-exact, step, -confidence))` ties broken by list order).
- Reproduction: three readings of "100.00" on pdf pages 5, 50, 80 plus two of "250.00"; over 200 shuffles of the input list, `chosen.pdf_page` takes all of 5, 50 and 80. The chosen value and verdict never change; only which page the flag cites. Same input twice gives the same output.
- Fix: add `m.pdf_page` as a final tiebreak key (front-most page, or lowest) for a canonical citation.

## Items checked and not defective (to avoid re-testing)
- diff: identical, reordered, empty-vs-empty documents; one-sided (empty) comparison reports all facts as removed and flags as removed. That is literal, but note that a "removed" flag in diff may mean "rule no longer evaluable" rather than "cleared", since diff compares flags, not the rule audit (observation, Inconclusive; not tested on real reports).
- Regulatory boundary semantics: ratio == cap not a breach; Rs 10 crore SME absolute cap applied; denominators <= 0 abstain.

## Limitations
- L1. No real DRHP PDF was processed; parse/pdf.py table and header assembly (including how headers like "Q1 FY2025" reach `parse_period`) were not exercised. F1/F2 are shown from the header string to the fact key; whether a given real PDF produces such headers is unverified.
- L2. Not reviewed within budget: segment.py, brief.py, checks/litigation.py, checks/related_party.py, extract/issue.py (issue-size and objects extraction: unit and "Rs." handling there is unverified), extract/sector.py, eval/*, and all of screening/{engine,rules,regulatory,reports}. Absence of findings there means not examined, not clean.
- L3. `evaluate`/`audit` use `date.today()` when `as_of` is None (engine.py, `day = as_of or date.today()`). analyze_document passes `as_of` through unchanged, so a run without it can change verdict when a rule's window rolls over. Documented in the docstring; not shown to cause a wrong answer. Unverified at CLI level.
- L4. Determinism was checked at function level only. Hash-seed, TZ and LANG runs of the full pipeline, giant inputs and idempotence of `analyze` on a real document were not run.
- L5. Hypothesis was used for numfmt/parse_amount only; periods, consensus and engine boundaries are hand-written cases.
