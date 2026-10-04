# Lending Protocol Invariants — Library

For Solend, MarginFi, Kamino-class lending protocols.

## Solvency invariants

### I1: Pool solvency
```
sum(deposits) >= sum(borrows)
```
Always — total reserves cover total liabilities.

### I2: Per-account collateralization
```
account.collateral_value * LTV >= account.borrow_value (for healthy)
account.collateral_value * LTV < account.borrow_value → liquidatable
```

### I3: Interest accrual monotonic
```
total_borrowed_value at t2 >= total_borrowed_value at t1 (if no repayments)
```
Interest doesn't decrease over time.

## State transition invariants

### I4: Cannot withdraw past collateral threshold
```
withdraw(amount) requires account remains healthy after
```

### I5: Cannot borrow past collateral
```
borrow(amount) requires account.health_factor > 1.0 after
```

### I6: Liquidation only on unhealthy accounts
```
liquidate(account) requires account.health_factor < 1.0 at tx start
```

### I7: Liquidation incentive bounded
```
liquidator_profit <= liquidation_bonus_percent * collateral_seized
```

## Oracle invariants

### I8: Oracle price freshness
```
swap/borrow/liquidate uses oracle.price where now - oracle.publish_time < MAX_STALENESS
```
Violation: stale oracle drives bad decisions.

### I9: Oracle confidence
```
oracle.confidence_interval / oracle.price < MAX_CONFIDENCE_RATIO
```

### I10: Oracle authority pinned (Pyth Lazer / similar)
```
oracle_account.update_authority == expected_authority
```

## Flash loan invariants

### I11: Flash loan state flag set during execution
```
during flash_loan: ACCOUNT_IN_FLASHLOAN flag set
all NEW instructions check flag → reject if set
```
Marginfi 2025 class: missed flag in new instruction = $160M.

### I12: Flash loan repayment in same tx
```
end_of_tx: borrowed_amount + fee returned to vault
```

## Interest model invariants

### I13: Utilization-rate model monotonic
```
borrow_rate is monotonic non-decreasing function of utilization
```

### I14: Interest rate within bounds
```
borrow_rate <= MAX_BORROW_RATE
```

## Strategy hints for Trident

```rust
strategies! {
    Deposit(amount = 1..u64::MAX),
    Withdraw(amount = 1..u64::MAX),
    Borrow(amount = 1..u64::MAX),
    Repay(amount = 1..u64::MAX),
    Liquidate(target_account = arbitrary, collateral_seized = 1..u64::MAX),
    UpdateOracle(price_delta = -50%..200%),
}
```

## Critical scenarios

1. **Liquidation race**: 2 liquidators racing same account
2. **Oracle update mid-tx**: borrow at price1 → oracle moves → liquidation profitable
3. **Flash loan + price manipulation**: flash + manipulate vault price + liquidate own position
4. **Cross-account composition**: multi-collateral, multi-debt accounts
