# Hypothesis: Numerical Edge Cases

**Trigger**: contract does arithmetic, rounding, or compare. Test extremes.

## Edge values to test

| Type | Edges |
|------|-------|
| `uint256` | 0, 1, type(uint256).max, type(uint256).max - 1 |
| `int256` | type(int256).min, -1, 0, type(int256).max |
| Address | 0x0, msg.sender, address(this), address(0xdead) |
| Token amount | 0, 1 wei (dust), 1 token, max supply, fractional |
| Decimals | 0, 6, 18, 27+ |
| Timestamps | block.timestamp ± 15s, 0, year 2038, year 2106 |

## Common bugs

### Off-by-one
- `for (i=0; i<arr.length-1; i++)` → misses last
- `for (i=1; i<=arr.length; i++)` → overruns

### Rounding direction
- Redeem should round DOWN (favor vault)
- Borrow should round UP (favor protocol)
- Deposit should round DOWN shares (favor vault)
- Check `Math.Rounding.Floor` vs `Math.Rounding.Ceil` correctness

### Overflow at extremes
- `a * b / c` — `a*b` overflows before division
- Use `Math.mulDiv` (OZ) which handles this

### Truncation
- `amount / 100 * 100 != amount` for non-multiples
- Division before multiplication loses precision

### Compare across types
- `uint256` compared with `int256` (cast issues)
- Signed/unsigned confusion

## Verification

For each suspect computation:
```solidity
function test_NumericalEdge_MAX() public {
    target.fn(type(uint256).max);  // should revert or handle gracefully
}
function test_NumericalEdge_ZERO() public {
    target.fn(0);  // should handle or revert clearly
}
function test_NumericalEdge_DUST() public {
    uint256 result = target.computeShares(1);  // 1 wei — does it round to 0?
    assertGt(result, 0);
}
```
