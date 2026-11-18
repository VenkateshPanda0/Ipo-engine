# Documentation index

| You want to | Read |
|---|---|
| Understand the aim and the fixed rules | `CHARTER.md` |
| See how the parts fit together | `ARCHITECTURE.md` |
| Know what to work on next | `roadmap.md` (the ordered TODO), then `plan.md` (phases and gates) |
| See today's numbers and known defects | `status.md` |
| Find why something is built the way it is | `decisions.md` (D-001 onward) |
| Understand the threat model for hostile PDFs | `security.md` |
| See how a held-out set went | `history/heldout-run-N.md` |
| Work on the screening app | `screening/` (its own architecture, regulations, review workflow, benchmark); where it disagrees with `ARCHITECTURE.md` or `status.md`, those win |

## Follow the steps

1. Set up and run: `README.md`, "How to use it".
2. Change something: `CONTRIBUTING.md` (gate, tests, labels first).
3. Pick work: first unchecked item in `roadmap.md`.
4. Finish: update `CHANGELOG.md`, `status.md` (computed numbers only) and `decisions.md`; run
   `tools/gate.sh; echo rc=$?`; push to `main`.
