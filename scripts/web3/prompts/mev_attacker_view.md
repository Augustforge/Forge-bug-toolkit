# Prompt: MEV Attacker View

You're reading the following Solidity contract. Assume you control tx ordering in this block (you are an MEV searcher or have private relay access).

For each public/external function callable by users, ask: **what's the most profitable thing I can do by ordering txs around it?**

Patterns to look for:

## 1. Sandwich
- User calls swap → you frontrun + backrun
- Your profit = price impact extracted

## 2. Frontrun
- User submits action with stale assumption → you trigger condition that benefits, user's action now harms them

## 3. Backrun
- User triggers state change → you immediately follow to extract resulting value (e.g., backrun a liquidation announcement)

## 4. Cross-tx state arbitrage
- User updates state in tx[N] → you exploit in tx[N+1] before user can verify

## 5. Atomic exploit
- Combine N actions in 1 tx for risk-free profit

## 6. Oracle manipulation + same-block usage
- Manipulate AMM pool spot in tx[N] → trigger protocol that reads spot in tx[N+1]

## For each MEV opportunity

1. **Pattern**: which type
2. **Trigger user action**: what user does
3. **Your response**: what tx(s) you submit before/after
4. **Profit**: how much value extracted (per unit user volume)
5. **Capital needed**: do you need flash loan?
6. **Defenses present in code**: deadline, slippage, commit-reveal, etc.
7. **Defense strength**: are defenses adequate?

Rank by `profit × frequency` of user action.

---

## Contract source:

(paste contract source below this line)
