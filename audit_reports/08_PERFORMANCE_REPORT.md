# Performance report

Measured in the sandbox. Numbers are from real runs; nothing is estimated.

## Request throughput (no regression)

`tools/loadtest.py --selfhost --duration 10`, baseline source (`f970795`, a throwaway git worktree) against the audit branch, alternated, same machine, no other work running:

| Round | Baseline | Audit branch |
|---|---:|---:|
| 1 | 81 req/s | 81 req/s |
| 2 | 82 req/s | 78 req/s |

The difference is within the run-to-run noise of this machine. Two earlier single runs (120 req/s at the start while eight review agents shared the machine, 83 req/s at the end) differed by more than the code change could explain; they are noise from machine state and are kept in `raw/` for the record, not used as a comparison.

## Fixes that change a measured resource

| Case | Before | After | Source |
|---|---|---|---|
| `detect_unit` on a caption with 5,000 digits and no unit word | 1.385 s | 0.001 s | measured on both trees |
| same, 10,000 digits | 6.548 s | 0.002 s | measured |
| same, 20,000 digits | 22.781 s | 0.005 s | measured |
| related-party figure count, 20,000 digits | 0.990 s | 0.000 s | measured |
| 199 KB PDF whose deflate stream expands to 200 MB | passed validation | refused in 0.14 s (`too_large_decoded`) | measured on both trees |
| the same file decoded by the web pipeline | 0.46 s, 452 MB resident | no longer reached | ingest agent, baseline only |
| the same file in the CLI parser | 1.97 s, 648 MB | unchanged (CLI path has no cap; F-18 open) | ingest agent |
| in-process rate limiter after 50,000 distinct clients | 50,000 entries kept | idle entries dropped every 1,024 calls | db agent (before); unit test (after) |
| webhook receiver sending 1 byte every 0.5 s | dispatcher blocked 50 s | cut off by a 20 s whole-exchange timer | network agent (before); test with a 1 s timer (after) |

## Bottlenecks identified and not changed

- One thread sends every organisation's webhooks (F-46).
- Validation now decompresses every deflate stream once to count its size. This was not timed on a real 1,500-page filing; on the test files it added 0.14 s for a 200 MB stream. A real-filing timing is open.
- Single-process in-memory limiter per replica (a database-backed option exists).

Memory and CPU profiles beyond the above were not taken.
