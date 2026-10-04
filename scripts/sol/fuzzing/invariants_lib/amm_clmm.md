# AMM CLMM Invariants — Library

Concentrated Liquidity AMM (Orca Whirlpools, Raydium CLMM, Phoenix-class). Use these as starting set, then add target-specific invariants from hypothesis phase.

## Conservation invariants

### I1: Total liquidity conservation across positions
For any tick range fully active at `current_tick`:
```
sum(position.liquidity for position in positions_active_at(current_tick))
    == pool.liquidity
```
Violation: someone gained liquidity without depositing OR pool double-counts.

### I2: Token balance vs accounted reserves
```
vault_a.amount >= sum(positions.token_a_owed) + sum(unclaimed_protocol_fee_a)
vault_b.amount >= sum(positions.token_b_owed) + sum(unclaimed_protocol_fee_b)
```
Violation: pool solvency broken.

### I3: Tick boundary consistency
```
pool.tick_current_index == tick_from_sqrt_price(pool.sqrt_price)
```
Violation: tick/sqrt_price drift causes incorrect math downstream.

### I4: Sqrt price bounds
```
MIN_SQRT_PRICE_X64 <= pool.sqrt_price <= MAX_SQRT_PRICE_X64
```
Violation: math overflow/underflow possible.

## Swap invariants

### I5: No profit roundtrip
For (amount, a_to_b) and reverse swap of received amount:
```
let out_b = swap(amount, a_to_b=true, ignore_fees);
let out_a = swap(out_b, a_to_b=false, ignore_fees);
out_a <= amount  // strictly less if liquidity is finite
```
Violation: profit extraction via roundtrip = Critical AMM bug.

### I6: Slippage enforcement
```
swap(amount, min_out) returns out_amount where out_amount >= min_out OR errors
```
Violation: silent under-delivery.

### I7: K-invariant (analog to x*y=k)
For CLMM, the L-invariant: liquidity active during swap × delta(sqrt_price) consistent with token deltas.

### I8: Fee accumulation monotonic
```
pool.fee_growth_global_a never decreases
pool.fee_growth_global_b never decreases
```
Violation: fee underflow.

## Position lifecycle invariants

### I9: Position fee_owed bounded by accumulated growth
```
position.fee_owed_a <= position.liquidity × (fee_growth_inside_a - fee_growth_checkpoint_a)
```
Violation: fee inflation, attacker claims fees they didn't earn.

### I10: Empty position closeable
```
position.liquidity == 0 AND fees_owed == 0 AND rewards_owed == 0
  → close_position can succeed
```
Violation: forced rent stuck in account.

### I11: Locked position is unmodifiable
```
LockConfig exists for position → decrease_liquidity errors
LockConfig exists for position → close_position errors
```
Violation: lock can be bypassed (Critical if so).

### I12: Position can only be closed by owner
For non-locked: `signer == position_token_account.owner OR delegate`
For locked transfer: `signer == position_token_account.owner` ONLY

## Tick array invariants

### I13: Initialized tick liquidity_net signed sum
```
sum(tick.liquidity_net for all tick) == 0  
```
(across all ticks in pool — net flows cancel)

### I14: Tick array boundary
```
tick_array.start_tick_index <= tick.index < tick_array.start_tick_index + TICK_ARRAY_SIZE * tick_spacing
```
Violation: out-of-bounds access.

### I15: Tick array discriminator
```
tick_array.discriminator == FixedTickArray::DISCRIMINATOR OR DynamicTickArray::DISCRIMINATOR
```
Violation: type confusion.

## Adaptive Fee invariants (Orca-specific)

### I16: Volatility accumulator bounded
```
oracle.adaptive_fee_variables.volatility_accumulator <= oracle.adaptive_fee_constants.max_volatility_accumulator
```
Violation: fee rate explodes beyond cap.

### I17: Volatility reference bounded
```
oracle.adaptive_fee_variables.volatility_reference < oracle.adaptive_fee_variables.volatility_accumulator (post-decay)
```

### I18: Total fee rate hard limit
```
get_total_fee_rate() <= FEE_RATE_HARD_LIMIT (100_000 = 10%)
```
Violation: protocol could charge >10% fees.

### I19: Reference update timestamp monotonic
```
oracle.adaptive_fee_variables.last_reference_update_timestamp non-decreasing
```

### I20: Trade enable timestamp respect
```
current_timestamp < oracle.trade_enable_timestamp → swap errors
```
Violation: pre-launch trading.

## Token-2022 specific

### I21: Transfer hook reentrancy
During CPI to transfer hook, state must NOT be re-entered:
- Strategy: record `whirlpool.liquidity` before hook → after hook → must match (no swap during hook)

### I22: Transfer fee accounting
```
amount_charged_for_user = amount_to_pool + transfer_fee
```
Violation: pool gets less than user paid (lost difference).

## Cross-protocol composability

### I23: Whirlpool not vulnerable to external token program behavior
Pool should refuse mints with:
- NonTransferable extension (rejected)
- DefaultAccountState that auto-freezes (rejected unless badge)
- Pausable (rejected unless badge)

## Strategy hints for Trident

When writing fuzz harness, prioritize these instruction sequences:
1. `open_position → increase_liquidity → swap×N → decrease_liquidity → close_position`
2. `open_position → lock_position(Permanent) → try_decrease (expect fail)`
3. `swap_v2 with extreme amounts (u64::MAX, 1, 0+1)`
4. `reposition_liquidity_v2 with new_range == old_range OR overlapping`
5. `Mixed Anchor + Pinocchio instructions on same position`

## Critical paths to fuzz first

1. **swap** — economic core, math complexity
2. **reposition_liquidity_v2** — NEW post-audit code, 538 lines
3. **adaptive_fee swap with extreme volatility**
4. **lock_position interactions**
5. **Cross-program calls with Token-2022 extensions**

## Validation

Test the invariants by INTENTIONALLY introducing a bug, running fuzz, and verifying the fuzzer catches it. Workflow:
```
1. Implement invariant
2. Temporarily break protocol code (e.g., comment out a safety check)
3. Run fuzz 30 min
4. If invariant violated → fuzzer reports → confirm
5. Restore protocol code
```

This calibration ensures invariants actually detect what they should.
