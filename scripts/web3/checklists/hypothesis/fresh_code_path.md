# Hypothesis: Fresh Code Path

**Trigger**: recent commits / upgrades. Newest code = least-tested.

## Why fresh code is bug-rich

- No production exposure
- Tests written by same developer who wrote code
- Auditors haven't seen it (if commit is post-audit)
- Reviewers fatigued by end of audit
- Edge cases not yet found by users

## Identification

```bash
# Recent commits with code changes
git log --since="30 days ago" --stat --no-merges -- '*.sol'

# Commits touching critical files
git log -p --since="30 days ago" -- contracts/core/

# Functions added recently
git log --since="60 days ago" -p -- '*.sol' | grep -B 2 "^+\s*function"
```

## What to look at

1. **Newly-added functions**: most likely to have bugs
2. **Modified functions**: changes can introduce bugs in adjacent paths
3. **Added state variables**: storage layout / serialization concerns
4. **Removed checks**: someone removed a `require()` — was it needed?
5. **New external dependencies**: new addresses introduced

## Specific things to test

- Functions added without unit tests
- Function whose signature changed (parameter order!)
- Modifier changes affecting many functions
- Storage layout changes in upgradeable contracts

## Verification

For each recent change:
1. Read the diff (git show <sha>)
2. Apply other hypothesis templates to NEW code
3. Run scanners against pre/post: are new findings present in new code?

## Pattern matching with audit_trail_miner

`scripts/web3/hypothesis/audit_trail_miner.py` flags commits where claim doesn't match diff. Most useful AFTER audit completion to find new bugs introduced.
