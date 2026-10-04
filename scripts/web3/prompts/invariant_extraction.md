# Prompt: Invariant Extraction

You're reading the following Solidity contract. Extract every INVARIANT it assumes.

An invariant is a property that must always hold for the contract to function correctly. Examples:
- `totalSupply == sum(balances)`
- `vault.totalAssets() >= strategy.balance() + idle.balance()`
- `user.depositedTokens >= user.stakedTokens + user.delegatedOut`
- `share_price never decreases without admin action`
- `proposal state transitions are monotonic`

Sources of invariants:
- Explicit: `require(x >= y)` statements
- Implicit: based on business logic (e.g., math expects positive)
- Comments: `@dev MUST be true that...`
- Modifier semantics: what state modifiers enforce
- Cross-function: states updated together

For each invariant:
1. **Statement**: precise MUST-condition (e.g., "totalShares × pricePerShare == totalAssets")
2. **Location**: where in code is this enforced/assumed
3. **Mutating paths**: which functions could violate this
4. **Verification**: how would you write a Foundry invariant_* test for it
5. **What happens if violated**: economic / security consequence

Output as ranked list of invariants. Rank by potential damage if violated.

Don't give code refactors. Just identify invariants.

---

## Contract source:

(paste contract source below this line)
