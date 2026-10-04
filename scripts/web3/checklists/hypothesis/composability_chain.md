# Hypothesis: Composability Chain (DeFi Lego)

**Trigger**: target depends on external protocol that can be manipulated cheaply.

## Pattern

A → reads from B. B can be manipulated. A inherits B's risk.

## Common composability attacks

| Chain | Attack |
|-------|--------|
| Vault → Oracle | Manipulate oracle, exploit vault math |
| Lending → AMM (TWAP) | Manipulate TWAP, exploit collateral pricing |
| Insurance → Risk pool | Manipulate risk pool, claim cheap |
| Stablecoin → Oracle | Manipulate oracle, redeem at off-peg |
| Strategy → Underlying | Drain underlying, strategy holds shares of empty pool |

## Composability matrix to map

For target T:
1. List all external contracts T reads from / writes to
2. For each external C, ask: "what would happen to T if C is compromised/manipulated?"
3. Check: how cheaply can C be compromised?
   - Flash loan (zero capital)
   - Few % price move ($100k-1M capital)
   - Multi-day manipulation ($10M+ capital)

## Verification

Use `scripts/web3/longtail/composability_matrix.py` to extract dependency graph.

Then for each high-risk dependency:
```solidity
function test_Composability_OracleManipulation() public {
    // Step 1: manipulate B
    pool_B.swap(largeAmount);
    
    // Step 2: trigger T action that reads B
    targetT.functionUsingPriceFromB();
    
    // Step 3: extract value
    targetT.withdraw(...);
}
```

## Defenses to verify

- T uses Chainlink (manipulation expensive)
- T uses TWAP with long window
- T uses median of multiple oracles
- T validates price within ±X% of recent
