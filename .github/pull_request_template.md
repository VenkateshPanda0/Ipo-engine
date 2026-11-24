## What and why

<!-- What changes, and the reason. Link the issue if there is one. -->

## Checks

- [ ] `tools/gate.sh` passes (`rc=0`), and for frontend changes `cd frontend && npm run typecheck && npm test`
- [ ] Tests added or changed; a defect fix has a test that failed before the fix
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] If output changed: `ANALYSIS_VERSION` (or the ruleset / API version) bumped as `docs/VERSIONING.md` says, and `ipo eval` numbers recorded
- [ ] If a decision was made: a D-number added to `docs/decisions.md`
- [ ] No secrets, and no non-public data (filings, keys, personal details)

## Accuracy impact

<!-- "None: no extraction, rule or threshold changed", or the before/after numbers
     (`ipo eval`, `tools/rp_score.py`, `tools/lit_score.py`). -->
