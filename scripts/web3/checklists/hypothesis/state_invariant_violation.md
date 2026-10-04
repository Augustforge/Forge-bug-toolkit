# Hypothesis: State Invariant Violation

**Trigger**: invariant identified (from comments, business logic, or audit reports). Want to break it.

**Real example**: DeXe's `_canMove` function explicitly defines the invariant `depositedTokens >= stakedTokens + amount`. Multiple functions check it via `ifNotStaken`, but `delegateTokens` doesn't, breaking the invariant.

---

## Checklist

### 1. State invariant identification
- [ ] Write invariant as a precise MUST-statement
- [ ] Example: `sum(user_balances) MUST equal totalSupply` (always)
- [ ] Example: `vault.totalAssets() MUST be approximately strategy.balance() + idle.balance()`
- [ ] Example: `user.depositedTokens MUST >= user.stakedTokens + user.delegatedOut`

### 2. Identify all mutating paths
- [ ] List EVERY function that can change variables in the invariant
- [ ] For each, ask: does it preserve invariant?

### 3. Check guards
- [ ] For each mutating function, what enforces invariant preservation?
  - Explicit require/revert?
  - Modifier?
  - Implicit by ordering of state changes?

### 4. Find the gap
- [ ] Which mutating path doesn't have explicit guard?
- [ ] Trace through state changes step-by-step
- [ ] Find a sequence of operations that violates invariant

### 5. Verification via Foundry invariant tests
- [ ] Generate test:
```solidity
function invariant_userDepositsCoverStakes() public {
    for (uint i; i < users.length; i++) {
        address u = users[i];
        assertGe(
            depositedTokens[u],
            stakedTokens[u] + delegatedOut[u],
            "Invariant violated"
        );
    }
}
```
- [ ] Run `forge test --match-test invariant` for 1h
- [ ] Counterexample found → confirmed bug

### 6. Severity by impact
- [ ] If invariant break = funds extractable → **Critical**
- [ ] If invariant break = governance manipulation → **High**
- [ ] If invariant break = display only (UI shows wrong number) → **Low**

---

## Common invariants to test

### Vault/Pool
- `totalSupply == sum(balances)`
- `totalAssets == strategy.balance + idle.balance + claimable.balance`
- `share_price MUST monotonically increase` (or stable, never strictly decrease without admin action)
- `pricePerShare ≥ 1e18` (no negative yield)

### Lending
- `total_borrows ≤ total_supply`
- `user_collateral_value × LTV ≥ user_debt_value` (per position)
- `sum(reserves) == total_supplied - total_borrowed - bad_debt`

### Staking
- `staked[user] ≤ deposited[user]`
- `rewards_paid[user] ≤ rewards_earned[user]`
- `sum(staked) == total_staked`

### Governance
- `vote_count ≤ snapshot_total_supply`
- `proposal_state transitions are monotonic`

### AMM
- `reserve_X * reserve_Y ≥ K_pre` (after fees)
- `LP_supply * price_per_LP == reserve_X * 2` (for 50/50 V2)

### Bridge
- `locked_on_source == issued_on_destination - burned_on_destination`

---

## Output format

```markdown
## Invariant H<N>: <one-line statement>

### Formal
For all users u and all valid states:
`<invariant expression>`

### Mutating paths
1. `<FunctionA>` (file:line) — preserves: yes/no (because <reason>)
2. `<FunctionB>` (file:line) — preserves: ...

### Break sequence
1. Initial state: <description>
2. Call <FunctionX> with params <Y>
3. State now violates invariant

### Verification
- [ ] Foundry invariant test passes (with counterexample seed if found)

### Impact
- Funds extractable: <yes/no, $amount>
- Governance breakable: <yes/no>
```
