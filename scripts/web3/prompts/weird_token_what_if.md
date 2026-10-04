# Prompt: Weird Token What-If

You're reading the following Solidity contract that accepts arbitrary ERC-20 tokens. Analyze the contract's behavior under non-standard token implementations:

For each token quirk below, trace what happens:

## 1. Fee-on-transfer
Transfer deducts fee, recipient gets less. Example: SAFEMOON.
- Where does `_amount` mean "sent" vs "received"?
- Does protocol assume `transferFrom(user, X) == X received`?
- Result: protocol credits user for X but only receives X*(1-fee)

## 2. Rebasing
`balanceOf(user)` changes via rebase. Example: AMPL.
- Stored balances vs computed balances drift
- Protocol may credit X shares for X tokens, but after rebase user's tokens != X
- Does protocol read balanceOf to detect, or trust deposit amount?

## 3. ERC-777 callback
`tokensReceived` callback during transfer. Example: imBTC.
- Where does protocol receive tokens? Is there reentrancy guard on caller?
- Can attacker re-enter via callback?

## 4. Blacklisting (USDC pattern)
Specific addresses blocked from receiving.
- If user gets blacklisted between deposit and withdraw, withdrawal fails forever
- Does protocol have escape hatch?

## 5. Zero decimals (USDT-like)
`decimals() == 6` or even 0. Some tokens have wildly different decimals.
- Off-by-one in amount calculations
- Truncation when scaling

## 6. Max decimals (18+)
Some tokens 21+ decimals.
- Overflow in multiplications
- Precision loss in division

## 7. No-revert-on-fail
Some tokens return false but don't revert. Example: ZRX older versions.
- Protocol assumes `require(token.transfer(...))` works
- Reality: silent failure

## 8. Same-token twice in pair
What if `token0 == token1`? Some routing logic breaks.

## Output

For each quirk that breaks something:
1. **Quirk**: which one
2. **Function affected**: function name
3. **Failure mode**: how it breaks
4. **Exploit**: can attacker profit?
5. **Severity**: Low/Medium/High

---

## Contract source:

(paste contract source below this line)
