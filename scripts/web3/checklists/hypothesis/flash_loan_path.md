# Hypothesis: Flash-Loan Amplified Attack

**Trigger**: target has function whose behavior depends on caller's balance/share-of-pool.

## Why flash loans matter

Flash loans give attackers UNLIMITED capital for one transaction. If a bug only manifests with $10M deposit, attacker doesn't need to OWN $10M — they borrow it. Cost: 5 bps fee + gas.

## Functions vulnerable to FL amplification

### Voting/governance
- Vote weight by token balance → flash loan, vote, repay
- Snapshot uses block.timestamp - 1 (current) → no protection
- Snapshot uses proposalCreationTimestamp → protected

### Pool sandbox manipulation
- Spot price = `reserve1 / reserve0`
- Big swap moves price → external function reads stale spot

### Share dilution
- Vault total supply matters for mint price
- Attacker mints huge share count temporarily → preview functions return inflated

### Liquidation eligibility
- Health factor based on collateral price
- Attacker manipulates price → triggers their own liquidation at advantage

### Redemption discount
- Stablecoin redemption price depends on deviation
- Flash loan creates artificial deviation → favorable redemption

## Verification

Use Aave V3 flash loan (mainnet $1B+ available):
```solidity
function executeOperation(asset, amount, premium, ...) {
    // Use `amount` for manipulation
    // Call vulnerable function
    // Reverse manipulation
    // Approve premium repayment
}
```

See `foundry_corpus/FlashLoanDrain.t.sol.template`.

## Defenses to check

- Snapshot at past block (not current)
- Commit-reveal (action delayed)
- TWAP with window > flash-loan tx
- Minimum holding period

## Severity argument

If FL-amplified attack works:
- `capital_required = 0` (FL covers it)
- `attack_cost = gas + FL fee` (typically $50-100)
- `expected_profit = depends on TVL exposed`
- Almost always **Critical** if profit > $1k
