# Hypothesis: Multi-Step Exploit Chains

**Trigger**: target has multiple Low/Medium findings. Combine for Critical.

**Pattern from rekt.news**: Most $1M+ exploits are 3-step chains. Single bug = Medium. Chain = Critical.

## Common chain patterns

### Chain 1: Approval + Slippage + Sandwich
1. **Step A**: target allows arbitrary `spender` via `approve()`
2. **Step B**: spender contract has insufficient slippage validation
3. **Step C**: sandwich the tx → extract sandwich profit + drain via spender abuse

### Chain 2: Init + Storage + Upgrade
1. **Step A**: implementation contract not initialized atomically (init race)
2. **Step B**: attacker becomes admin via race
3. **Step C**: upgrade to malicious implementation → drain

### Chain 3: Oracle + Flash Loan + Liquidation
1. **Step A**: oracle reads from manipulatable AMM pool (Low if AMM is deep)
2. **Step B**: flash loan to manipulate pool (zero capital cost)
3. **Step C**: self-liquidate with manipulated price → profit on liquidation bonus

### Chain 4: Approval Race + Permit + Drain
1. **Step A**: token uses `approve(spender, X)` semantics (Low alone)
2. **Step B**: user signs Permit for X amount
3. **Step C**: attacker frontruns approve(0), then permits with old + new sigs

### Chain 5: Reentrancy + Math + Withdrawal
1. **Step A**: reentrancy guard missing on view function (Low alone)
2. **Step B**: math uses view-returned value mid-tx
3. **Step C**: attacker triggers reentrancy → wrong math → extract via withdraw

### Chain 6: Composability + Donation + Inflation
1. **Step A**: target reads price from low-liquidity AMM pool
2. **Step B**: anyone can donate to pool (manipulate reserves)
3. **Step C**: target's vault math affected → first-depositor inflation

## How to build a chain

1. List all confirmed Low/Medium findings
2. For each pair, ask: "does Low #1 enable or amplify Low #2?"
3. If pair found → try 3-chain
4. Write Foundry test executing chain in sequence
5. Measure total extraction value

## Verification

```solidity
function test_Exploit_ChainedAttack() public {
    // Step 1: trigger Low #1
    target.lowBug1();
    
    // Step 2: now Low #2 has different precondition
    target.lowBug2(...);
    
    // Step 3: extract via amplified bug
    uint256 extracted = target.drainPath();
    
    assertGt(extracted, EXPECTED_THRESHOLD);
}
```

## Severity argument

Each step alone = Low/Medium. Chained = High/Critical because:
- Single fix wouldn't address the chain
- Triggered by ordinary user action (no admin required)
- Profit > 10× cost (typically)

Use `scripts/web3/advanced/exploit_chain_builder.py` to scaffold.
