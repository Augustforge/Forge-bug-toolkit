# Hypothesis: Time-Dependent Bugs

**Trigger**: target has time-based logic (interest, decay, lockups, deadlines).

## Patterns

### Interest accumulation
- `interest = principal × rate × elapsed / SECONDS_PER_YEAR`
- Rounding error per block accumulates
- Long-term insolvency: 1 wei lost per accrual → millions lost over years
- Test: simulate 5 years of accruals, check totalDebt vs sum of user debts

### Reward decay
- `reward = baseRate × decayFactor^elapsed_blocks`
- Exponential decay can underflow at extremes
- Check edge: very long lock periods

### Lockup expiry
- Unlock at `block.timestamp >= lockEnd`
- Off-by-one at the exact second
- If lockEnd in past at deploy → instant unlock

### Block.timestamp manipulation
- Validator can manipulate ±15s
- Used as randomness = bug
- Used for tie-breaking = bug

### Time-weighted voting
- Vote weight = stake × time_held
- Snapshot timing matters
- Flash-lock + vote possible if snapshot at vote time

### Year 2038 (uint32)
- Some legacy contracts use uint32 timestamps
- Overflow at 2038-01-19

## Verification

For interest/reward accumulation:
```solidity
function test_TimeAccrual_LongPeriod() public {
    // Setup: user deposits
    target.deposit(1000e18);
    
    // Warp 5 years
    vm.warp(block.timestamp + 5 * 365 days);
    
    // Check accrued amount
    uint256 totalAccrued = target.getTotalAccrued();
    uint256 expectedAccrued = computeExpected(1000e18, 5 * 365 days);
    
    // Allow 1 wei drift per accrual
    uint256 maxDrift = 5 * 365 * 24 * 60 * 60 / 12; // 1 wei per block
    assertApproxEqAbs(totalAccrued, expectedAccrued, maxDrift);
}
```

For lockup edges:
```solidity
function test_Lockup_ExactExpiry() public {
    target.lock(100e18, 30 days);
    
    vm.warp(block.timestamp + 30 days - 1);
    vm.expectRevert();  // 1s before expiry
    target.unlock();
    
    vm.warp(block.timestamp + 1);  // exact expiry
    target.unlock();  // should succeed
}
```

## Past examples
- bZx: rate accumulation drift
- Various: timelock = 0 race conditions
- Audius: timestamp manipulation
