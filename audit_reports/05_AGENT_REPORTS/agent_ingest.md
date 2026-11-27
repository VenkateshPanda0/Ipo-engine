# Agent report: untrusted-file handling, validation, parser robustness

Branch: audit/remediation-2026-11. No tracked file was modified; nothing committed. Throwaway scripts and fixtures are in /tmp/agent_ingest/ (gen.py, gen2.py, t_*.py, fx/, cli/). The effort cap was ~45 tool calls, then a short resume budget after a rate-limit stop; several planned checks were not run (see Limitations).

Machine: 4 cores, 16 GB RAM, Python 3.12.3, pdfplumber 0.11.10, pypdfium2 5.15.1, pikepdf 10.17.0.

## Scope and method

Code read: src/ipo_engine/screening/intelligence/ingest.py, parse/pdf.py, ingest/local.py, ingest/fetch.py, ingest/manifest.py, cli.py (add/run/parse), report_html.py, brief.py (escape usage), screening/api/routers/screen.py and v1.py (_read_limited, upload), screening_service.screen_pdf, intelligence/pipeline.py, intelligence/pages.py (deadline logic).

Dynamic tests: hostile PDFs crafted with tests/pdfgen.py and raw byte writers, fed to:
1. `validate_pdf` / `sanitize_filename` (web Stage A) directly.
2. `parse.pdf.parse_pdf` (the CLI path, pdfplumber + pdfium).
3. `screening.intelligence.pipeline.run_pipeline` (the web path, mostly pdfium).

Regex sweep: every module-level compiled `re.Pattern` in the ipo_engine package (79 distinct patterns) was run with `.search()` against 12 adversarial 100 KB strings. Each run had a 5 s alarm. Slow patterns were re-measured at several sizes and then driven end-to-end through a crafted PDF.

CLI `add` was exercised with spaces in paths, a directory, a missing file, bad doc ids and a symlink planted in `data/raw`.

## Checks and results

| # | Check | Result | Measured |
|---|---|---|---|
| 1 | Zero-byte file | Not Found | Web: rejected "empty". CLI parse: PdfiumError (clean). |
| 2 | Non-PDF content with .pdf name (MZ header, HTML) | Not Found | Web: rejected "not_pdf" by magic bytes, not by name or MIME. CLI parse: PdfiumError. |
| 3 | Content-type spoofing | Not Found (static plus check 2) | Type is decided from the bytes only. The declared Content-Type is never consulted in `validate_pdf`. |
| 4 | Truncated PDF | Not Found | Web: rejected "corrupt". CLI parse: PdfiumError. |
| 5 | Encrypted PDF (user password) | Not Found | Web: rejected "encrypted". CLI parse: PdfiumError "Incorrect password". Owner-password-only PDFs are accepted with a warning; text is extracted (0.03 s). |
| 6 | Junk bytes before %PDF | Not Found | Accepted with a warning (signature within the first 1024 bytes). |
| 7 | Page tree loop | Not Found (minor) | Web validate: rejected "corrupt". CLI `parse_pdf` raised a bare `IndexError: list index out of range` (opaque message). `_cmd_parse` catches it at the batch boundary. No hang. |
| 8 | Deeply nested array, 200k deep, 400 KB file | Not Found | Validate rejected as "no pages"; `parse_pdf` took 1.03 s and 95 MB RSS with no crash. |
| 9 | Huge declared /Count (99,999,999) with one real page | Not Found | Handled; 1 page. |
| 10 | Huge MediaBox (14,400,000 pt) | Not Found | Parsed in 0.00 s, no rendering is done. |
| 11 | 20,000-page empty PDF (1.9 MB) | Not Found (web), CLI inconclusive | Web: rejected at 0.49 s and 90 MB RSS by the 1500-page cap. The CLI path has no page cap (see F-3); I did not run `parse_pdf` on it. |
| 12 | Upload size limit | Not Found | `_read_limited` streams in chunks and aborts at the limit. v1 upload also checks Content-Length early. 50 MB default (`MAX_UPLOAD_SIZE_MB`, range 1 to 500). |
| 13 | **Flate decompression bomb** | **Confirmed** (F-1) | See F-1. |
| 14 | **ReDoS / quadratic regex** | **Confirmed** (F-2) | See F-2. |
| 15 | Filename traversal / hostile names | Not Found | `sanitize_filename`: `../../etc/passwd` gives `passwd`, `C:\Windows\...\cmd.exe` gives `cmd.exe`, NUL and newline removed, RTL override removed, a 5000-char name cut to 150, `<script>alert(1)</script>.pdf` gives `script_.pdf`, fullwidth solidus and NFKC tricks are neutralised. Cosmetic issues: a CJK name becomes `_.pdf`; `.pdf` becomes `pdf`; Windows reserved names (`CON`, `NUL.pdf`) are kept in the display name. The ingest docstring says stored filenames are server-generated; I did not trace the storage path in documents.py. |
| 16 | CLI path handling | Not Found | Paths with spaces work. A directory and a missing file give a clean "is not a file". `--doc-id` is validated by `^[a-z0-9][a-z0-9_-]{2,79}$`, so `../evil`, spaces, upper case and too-short ids are all refused. |
| 17 | **Output path symlink following** | **Confirmed** (F-4) | See F-4. |
| 18 | HTML report XSS | Not Found (static only) | report_html.py and brief.py wrap every document-derived string (issuer, rule names, spans, row text, section titles, hrefs with `quote=True`) in `html.escape`. Unescaped interpolations are static literals, ints, `date.isoformat()`, `Decimal` and `float`. Not run dynamically against a generated report. Note: `entry.url` goes into `href` after escaping, so a `javascript:` URL in an operator-supplied sources.toml would be a live link. That is operator-controlled, not PDF-controlled (P4). |
| 19 | Number parsing edge cases (`parse.units.parse_amount`) | Not Found | `nan`, `inf`, `-inf`, `NaN`, `Infinity`, `1e999`, `0x10`, `1_000`, `1,2,3`, `--5`, `1.2.3` all give `None`. `-0` and `(0)` give `Decimal('0')`. `(1,234)` gives -1234. `1,23,45,678.50` gives 12345678.50. A 5000-digit string gives an arbitrary-precision Decimal (no crash). Non-ASCII digits (Arabic-Indic, fullwidth) are accepted as numbers (via `str.isdigit` or `\d`). That is plausible behaviour, not a vulnerability. |
| 20 | Time and memory ceilings | Partial, see F-1 and F-3 | Web path: page cap 1500, size cap 50 MB, 900 s deadline checked only between pages. CLI path: none. |

## Confirmed findings

### F-1 Decompression bomb: no cap on decoded stream size or total decode work (P2)

Where: validation counts only compressed bytes and page count, in screening/intelligence/ingest.py `validate_pdf` (about lines 55-110). Decoding happens later, in pdfium inside `_pdfium_words` (screening/intelligence/pages.py `extract_pages`) and in pdfplumber/pdfminer in parse/pdf.py `_parse_pages`.

Root cause: the size limit applies to the upload, not to decompressed content streams. FlateDecode expands about 1000:1, and a single stream can be shared by every page via /Contents.

Reproduction (fixtures from /tmp/agent_ingest/gen.py and gen2.py; run with `python -I`):
- `bomb200.pdf`: 204 KB file, one page, 200 MB of spaces in a Flate content stream.
  - `validate_pdf`: accepted, 0.00 s.
  - Web `run_pipeline`: 0.46 s, peak RSS 452 MB.
  - CLI `parse_pdf`: 1.97 s, peak RSS 648 MB.
- `bomb1000.pdf`: 1.0 MB file, one page, 1000 MB decoded. Web `run_pipeline`: 2.20 s, peak RSS 2055 MB. Memory grew about 2x the decoded size, roughly linearly from the 200 MB case. I did not test beyond 1 GB (extrapolation to the 50 MB upload cap is unverified).
- `shared30x200.pdf`: 208 KB file, 30 pages sharing one 200 MB stream. Web `run_pipeline`: 12.37 s, about 0.41 s per page. By linear extrapolation 1500 pages would be about 10 minutes of CPU per upload (unverified).

Impact: a small authenticated upload can pin a worker thread for minutes and spike memory by GB per document. The OOM risk with several workers is plausible but not measured. The deadline in pages.py is checked only at page boundaries, so one huge page cannot be interrupted.

Suggested fix: add a decoded-size ceiling per stream and per document, either by pre-scanning streams with pikepdf (compare stream length against `/Length` and a decode limit) or by running extraction in a subprocess with `RLIMIT_AS` and a hard wall-clock kill. Check the deadline inside the page loop where possible. Apply a page cap to the CLI path too.

### F-2 Quadratic (ReDoS-class) regexes on attacker-controlled text (P2)

The sweep of 79 patterns at 100 KB hit the 5 s alarm on these (O(n^2) behaviour, no exponential blow-up found):
- screening/intelligence/numbers.py:151-154 `_AMOUNT_PHRASE_RE` (`\d[\d,]*(?:\.\d+)?\s*(?:lakhs?|...)\b`), called at numbers.py:168 in `detect_unit`.
- checks/related_party.py `_FIGURE` (`\d[\d,]*\.\d{1,2}(?!\d)`): 5.4 to 5.9 s at 100 KB.
- Also at the 5 s alarm on whitespace-heavy input: segment.py `_ENTRY`, screening/intelligence/tables.py `_NOTE_SUFFIX_RE`, screening/intelligence/periods.py `_FY_RANGE_RE`, extract/financials.py `_BARE_YEAR`, and related_party `_PCT`. The pdf word splitter normally removes long whitespace runs, so I judged those unreachable and did not scale them.

Scaling, isolated (`t_scale.py`):

| n | `_AMOUNT_PHRASE_RE` on `'1'*n` | `_FIGURE` on `'1'*n` |
|---|---|---|
| 5,000 | 1.37 s | 0.08 s |
| 10,000 | 5.34 s | 0.27 s |
| 20,000 | 22.30 s | 0.86 s |

End to end, through a real PDF (`t_e2e3.py`): a 9 KB PDF with one caption line `Statement of Profit and Loss (Rs. in lakhs) 111...1` directly above a ruled table, run through the web `run_pipeline` (the same `PipelineConfig` as the screening service):

| digits in caption | wall time |
|---|---|
| 2,000 | 0.53 s |
| 4,000 | 2.24 s |
| 8,000 | 7.85 s |

The same line with the digit run in a table cell or on its own line was not slow (0.22 s at 8000, 0.04 s at 8000), so the trigger is a long digit run in a unit caption. The `_FIGURE` path was not reproduced end to end (not attempted).

Impact: extrapolating quadratically, a 100 KB digit token in a caption would cost minutes of CPU per caption (unverified), and the 900 s deadline is only checked between pages.

Suggested fix: bound the repetition, for example `\d[\d,]{0,30}`, and truncate the input to `detect_unit` and `related_party` regexes (a few KB). Anchor `_FIGURE` with a leading `(?<![\d,])` so the engine does not rescan from every digit. Truncate caption text before matching.

### F-3 CLI/offline parse path has no page, size or time cap (P3)

Where: parse/pdf.py `parse_pdf` (about lines 440-500). Only the optional `--max-pages` limits work. `ingest/local.py::add_local` checks only `is_file` and an `%%EOF` marker (`looks_complete`). `Fetcher.MAX_BYTES` is 600 MB for downloads. Nothing limits decoded size or elapsed time. This is a local tool, so the threat is mostly self-inflicted or a malicious downloaded filing. Measured: `bomb200.pdf` took 1.97 s and 648 MB RSS here (F-1). I did not run the CLI on the 20,000-page fixture, so the page-count effect is unverified.

Suggested fix: reuse `validate_pdf` limits in `add_local`, and add a default `--max-pages` or a timeout.

### F-4 `ipo add` / `ipo run` follow a pre-existing symlink at data/raw/<doc_id>.pdf and overwrite its target (P4)

Where: ingest/local.py, `shutil.copyfile(pdf, final)` (about line 47) with `final = data_dir/raw/{doc_id}.pdf`.

Reproduction: `ln -s /tmp/agent_ingest/cli/victim.txt dd/raw/linkdoc.pdf`, then `ipo --data-dir ./dd add "dir with space/my file.pdf" --doc-id linkdoc --issuer X`. The command succeeds and `victim.txt` (previously `ORIGINAL`) now begins with `%PDF-1.4`.

Impact: requires an attacker who can already write inside the operator's data directory, so low. Suggested fix: refuse a destination that is a symlink, or write to a temp file and `os.replace` (as `Fetcher.fetch` already does).

## Minor observations (not findings)

- Rejection for a nested-array file reports "no pages" rather than a parser-depth reason (cosmetic).
- `sanitize_filename` degrades non-Latin names to `_` (usability, P4).
- `parse_pdf` on a page-tree-loop PDF raises a bare `IndexError`.

## Limitations

- The HTTP upload endpoints (`/screen/pdf`, v1 documents) were not exercised over HTTP. `validate_pdf`, `sanitize_filename` and `run_pipeline` were called directly, so multipart-level behaviour (Content-Length lies, chunked bodies) was only read, not run.
- HTML XSS was reviewed statically only, not with a generated report containing injected text.
- OCR path, hidden-text logic, pdfplumber table-finding blow-up (a page with thousands of rects and lines), the CLI on a 20,000-page file, and concurrent-upload memory exhaustion were not tested.
- Of the regex sweep, only `_AMOUNT_PHRASE_RE` was reproduced end to end. The others were measured on the bare regex against 100 KB strings only. Reachability of `_FIGURE` and the whitespace-heavy patterns is unverified.
- The sweep covers module-level compiled patterns only, not patterns built inside functions or passed straight to `re.search`/`re.sub`.
- The sweep used `.search` only; patterns used with `finditer` or `sub` may behave worse.
- Timings are from one 4-core sandbox; extrapolations are labelled as such.
