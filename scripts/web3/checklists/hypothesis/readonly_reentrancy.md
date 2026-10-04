# Hypothesis: Read-Only Reentrancy

**Trigger**: target reads price/state from external protocol that has reentrancy callback paths.

**Real example**: Curve protocols had `remove_liquidity` non-reentrant guard, BUT view function `get_virtual_price()` was not guarded. Attacker callbacks during remove read stale virtual_price.

## Common at-risk patterns

### Pattern 1: Curve LP price oracle
- Target reads `ICurvePool.get_virtual_price()`
- During `remove_liquidity(...)`, balances are reduced BEFORE LP burn
- Callback can read inflated virtual_price

### Pattern 2: Balancer LP price
- `IBalancerVault.getRate()` during withdraw
- Same pattern

### Pattern 3: ERC-4626 vault preview
- `preview*` functions may be stale during mid-tx state

### Pattern 4: Internal view functions
- Contract's own view function reads state that's being updated by mutating function with callback (ERC-721/777 callbacks)

## Verification

Write Foundry test:
1. Setup: protocol that reads price from Curve pool
2. Attacker provides liquidity to Curve pool
3. Attacker calls `remove_liquidity` with malicious receiver
4. Callback during remove → calls protocol's vulnerable function
5. Protocol reads stale `get_virtual_price` → makes wrong decision
6. Profit extracted

See `foundry_corpus/ReadOnlyReentrancy.t.sol.template`.

## Mitigation patterns to verify

- Does target wrap external view calls with reentrancy lock check?
- Does target validate price across multiple sources?
- Does target use TWAP with sufficient window (>30 min)?
