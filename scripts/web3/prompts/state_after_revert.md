# Prompt: State After Revert

You're reading the following Solidity contract. For each public/external function, trace what happens if it REVERTS at each possible revert point.

Many bugs come from "stuck state" — partial execution leaves contract in inconsistent state.

For each function:
1. List all revert points (require, assert, custom revert, external call failure)
2. For each revert point, identify what state was modified BEFORE the revert
3. If a revert undoes the tx, what's the impact?
4. Specifically check for:
   - Approval set, then transfer fails → approval lingers
   - Variable set, then external call fails → variable left set
   - Reentrancy mid-tx → state mid-flight
   - Failed-flag set but not unset on subsequent success

For each "stuck state" candidate:
1. **Function**: which function
2. **Revert point**: line + condition
3. **State left**: what state vars are stuck
4. **Impact**: can user be DoS'd? Can attacker exploit?

---

## Contract source:

(paste contract source below this line)
