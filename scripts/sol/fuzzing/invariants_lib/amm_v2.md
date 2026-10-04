# Constant-Product AMM Invariants — Library

For Raydium V4, Saber, Aldrin, and other x*y=k AMMs on Solana.

## Core invariants

### I1: Reserve product non-decreasing (modulo fees)
```
After swap:
    x_new * y_new >= x_old * y_old (without fees, ideally equal)
    x_new * y_new >= x_old * y_old * (1 - fee_rate) (with fees)
```
Violation: pool drained.

### I2: Reserve match vault
```
pool.reserve_a == vault_a.amount
pool.reserve_b == vault_b.amount
```
Violation: accounting drift.

### I3: LP token supply tracks pool ownership
```
sum(lp_tokens) == lp_mint.supply
user.share = user.lp_balance / lp_mint.supply
```

### I4: Slippage enforcement on swap
```
swap returns out_amount >= min_out OR errors
```

### I5: Slippage enforcement on add/remove liquidity
```
add_liquidity returns lp_minted >= min_lp_out OR errors
remove_liquidity returns (token_a_out, token_b_out) >= (min_a, min_b) OR errors
```

## Sandwich resistance

### I6: Per-block swap amount bounds (if implemented)
Some AMMs limit max swap per block. Verify cap enforced.

### I7: TWAP manipulation resistance (if oracle)
```
TWAP at t = average(prices over [t-window, t])
single tx shouldn't shift TWAP > X%
```

## First-depositor inflation

### I8: First deposit inflation defense
```
lp_minted = sqrt(deposit_a * deposit_b) - MINIMUM_LIQUIDITY_LOCKED
```
MINIMUM_LIQUIDITY_LOCKED ≥ 1000 typical Uniswap V2. Less = inflation vulnerable.

## Strategy hints

```rust
strategies! {
    Swap(a_to_b, amount = 1..u64::MAX, min_out = 0..amount),
    AddLiquidity(a_amount, b_amount, min_lp = 0..),
    RemoveLiquidity(lp_amount, min_a = 0.., min_b = 0..),
    DonateToVault(amount), // direct SPL transfer to manipulate price
}
```

## Critical scenarios
- First-depositor attack: empty pool → 1 wei stake → donate → victim deposits → victim gets 0 LP
- Roundtrip: swap A→B then B→A, attacker shouldn't profit
- Sandwich: front + victim + back
