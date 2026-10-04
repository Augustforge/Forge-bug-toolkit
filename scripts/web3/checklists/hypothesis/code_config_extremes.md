# Hypothesis: Code + Config Extremes

**Trigger**: target has admin-settable parameters. Test what happens when admin sets extremes.

This finds bugs where contract code is correct, but admin (even legitimate, even just buggy migration) can break invariants by setting params at boundaries.

## Common params to test at extremes

### Fee rates
- `fee = 0` — no protocol revenue, but check if math breaks (division by zero?)
- `fee = MAX_BPS (10000)` — 100% fee, user gets nothing back
- `fee > MAX_BPS` — if uncapped, can exceed 100%

### Time params
- `timelock = 0` — instant execution, no protection
- `timelock = type(uint256).max` — never executable
- `lockDuration = 0` — instant unlock, breaks staking incentive
- `gracePeriod = 0` — no grace, immediate liquidation

### Threshold params
- `liquidationThreshold = 0` — no liquidation possible
- `liquidationThreshold = MAX` — everyone liquidatable
- `minDeposit = 0` — dust deposits clog state
- `maxDeposit = 0` — no deposits possible

### Address params
- `setOracle(0x0)` — oracle returns 0, price = 0
- `setOracle(address(this))` — self-referential, infinite loop
- `setTreasury(burnAddress)` — funds lost

### Multiplier/reward params  
- `rewardRate = 0` — no rewards (stalls users)
- `rewardRate = MAX` — overflow on reward calculation
- `multiplier = 0` — math breaks

## Verification

For each admin-settable param, write Foundry test:
```solidity
function test_ConfigExtreme_FeeAt100Pct() public {
    vm.prank(admin);
    target.setFee(10000); // 100%
    
    deal(token, user, 100e18);
    vm.prank(user);
    target.deposit(100e18);
    
    // Check user state — did they get anything?
    uint256 userShares = target.balanceOf(user);
    // If shares == 0 due to 100% fee, that's bad UX but maybe not a bug.
    // If shares is huge due to overflow, that's a critical bug.
}
```

## Severity weight

- Admin doesn't lose money but creates bad UX → Low
- Admin can drain user funds by setting fee=100% → Medium (rug-pull vector but obvious)
- Admin can break invariants leading to fund loss → High
- Anyone (not just admin) can trigger via composability → Critical

## Defense to verify

Bounds check in setter:
```solidity
function setFee(uint256 newFee) external onlyOwner {
    require(newFee <= MAX_FEE_BPS, "Fee too high");
    fee = newFee;
}
```
