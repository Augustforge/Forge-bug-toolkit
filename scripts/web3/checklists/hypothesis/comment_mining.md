# Hypothesis: Comment Mining

**Trigger**: developer documented invariants/assumptions/limitations in comments. Verify each.

Use `scripts/web3/hypothesis/comment_miner.py` to extract candidates.

## What to look for

### Explicit invariants
- `@dev MUST be X`
- `@dev assumes Y`
- `@dev cannot exceed Z`
- `// Should always hold: X`

### Acknowledged limitations
- `// WARNING: this assumes Y, breaks if Y false`
- `// TODO: handle edge case Z`
- `// FIXME: race condition possible`

### Audit references
- `// fixed in audit X` — verify ACTUALLY fixed in code
- `// see security note Y` — check note for what's covered

### "Cannot happen" claims
- `// this should never happen because X`
- → if X false, what happens?

## Per-comment workflow

1. Extract comment + nearby code (10 lines)
2. Identify the claim
3. Ask: "what if the claim is false?"
4. Trace what state changes
5. Build hypothesis if exploit possible

## Past examples

### Alchemix (success)
- Comment: "Direct WETH-to-wstETH allocation marks down vault shares during depeg"
- → confirms bug existence
- "Fix" was a runbook, not code
- Hypothesis: bug is live in code
- Verified: yes, $X loss per depeg

### Hypothetical
- `// @dev assumes oracle is fresh (< 1h old)`
- Question: what if oracle is stale > 1h?
- Test: feed stale oracle data, check if protocol breaks

## Output format

For each comment-based hypothesis:
- File:line
- Comment text
- Inferred invariant/assumption
- Failure mode if invariant breaks
- Verification approach (Foundry test or scanner check)
