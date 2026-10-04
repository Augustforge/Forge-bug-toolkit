# Prompt: Worst Admin Action

You're reading the following Solidity contract. Imagine you are the admin (owner / governance / multisig).

Question: **What's the worst thing you can do without explicitly breaking an obvious invariant?**

Don't consider obvious rug-pull functions (e.g., `withdraw()` that takes all funds — too obvious). Find subtle admin abuse:
- Setting param to extreme value (fee=100%, deadline=0, maxAmount=2^256-1)
- Changing config that creates implicit drain over time
- Updating dependency address to malicious contract
- Pausing/unpausing strategically to trap users
- Frontrunning user actions with config changes

For each admin abuse:
1. **Action**: specific function call with parameters
2. **Effect on users**: what happens to existing user state/funds
3. **Detection**: would users notice? How fast?
4. **Reversibility**: can users undo / migrate out?
5. **Severity**: Low / Medium / High / Critical

If protocol has timelock — note how long delay protects users.

After analysis, identify the **single most damaging admin action that fits within rules**.

---

## Contract source:

(paste contract source below this line)
