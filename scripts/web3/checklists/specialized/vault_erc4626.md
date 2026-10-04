# Specialized Checklist: ERC-4626 Vault

## Donation attack (Cream pattern)
- [ ] `_decimalsOffset()` overridden (OZ virtual shares)
- [ ] First depositor protection (mint ≥ 1 share OR mint to vault itself)
- [ ] `totalAssets()` uses internal accounting, not `balanceOf(this)`

## Share inflation
- [ ] `convertToShares` rounds DOWN (favor vault)
- [ ] `convertToAssets` rounds DOWN (favor vault)
- [ ] `previewDeposit` matches `deposit` exactly
- [ ] `previewWithdraw`, `previewRedeem` consistent

## Rounding direction
- [ ] Mint: round shares UP (user pays slightly more)
- [ ] Deposit: round shares DOWN (user gets slightly fewer)
- [ ] Withdraw: round assets UP (user gets slightly fewer)
- [ ] Redeem: round assets DOWN (user gets slightly fewer)

## Hook reentrancy
- [ ] No external calls before share accounting
- [ ] OR `nonReentrant` on all mutating functions

## maxDeposit / maxWithdraw lying
- [ ] `maxDeposit(user)` matches actually-allowed deposit
- [ ] `maxWithdraw(user)` matches user's actual claim

## Async withdrawal (queued)
- [ ] Cancel cascade not exploitable
- [ ] Queue position fairness
