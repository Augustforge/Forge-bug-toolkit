# Liquid Staking / LST Invariants — Library

For xORCA, Marinade (mSOL), Jito (JitoSOL), Sanctum-class protocols. Stake → mint LST, unstake → escrow → withdraw.

## Conservation invariants

### I1: Vault solvency
```
vault.balance >= state.escrowed_amount + virtual_amount_underlying
```
Always — if vault.balance < escrowed, protocol is insolvent.

### I2: Total LST supply matches all mints
```
sum(MintTo events) - sum(Burn events) == lst_mint.supply
```
Track via events vs on-chain mint supply field.

### I3: Conservation across stake/unstake cycle
For attacker performing:
```
let xorca_minted = stake(amount_orca);
let orca_returned = unstake(xorca_minted) → pending_withdraw → withdraw;
orca_returned <= amount_orca  // never profit
```
Violation: profit extraction via roundtrip = Critical.

## Pricing/Rate invariants

### I4: Conversion rate non-decreasing (after rewards)
```
exchange_rate_t1 = (non_escrowed_orca + 100) / (xorca_supply + 100)
exchange_rate_t2 = (non_escrowed_orca' + 100) / (xorca_supply' + 100)
After rewards distribution: t2 >= t1
After user stake/unstake (no rewards): t2 == t1 (within rounding)
```

### I5: Symmetric rounding
Both `convert_orca_to_xorca` and `convert_xorca_to_orca` should produce **monotonic** behavior. If one truncates DOWN and the other UP → profit extraction.

### I6: First-depositor inflation bounded
With virtual_amount, max attacker loss to victim = `victim_deposit × (donation / virtual_amount)`. Check virtual_amount is large enough (>10^6 for 6-decimal tokens, NOT 100).

## State machine invariants

### I7: PendingWithdraw uniqueness per (unstaker, index)
Each (user_pubkey, withdraw_index) maps to at most ONE PendingWithdraw at a time.

### I8: PendingWithdraw must be created before withdraw
```
withdraw requires existing PendingWithdraw account
```

### I9: Cooldown enforcement
```
withdraw at time T requires PendingWithdraw.withdrawable_timestamp <= T
```
Violation: instant withdrawal bypassing cooldown.

### I10: Escrowed amount tracks pending withdrawals
```
state.escrowed_orca_amount == sum(pending_withdraw.withdrawable_orca_amount for all open pending)
```
Violation: stale escrow, vault math off.

### I11: Authority gates
- `initialize`: only DEPLOYER_ADDRESS
- `set`: only state.update_authority
- `stake/unstake/withdraw`: anyone

## Token authority invariants

### I12: LST mint authority is state PDA
```
lst_mint.mint_authority == state_pda
lst_mint.freeze_authority == None (or state_pda)
```
Violation: someone can mint LST out of band.

### I13: Vault owner is state PDA
```
vault_token_account.owner == state_pda
```
Violation: someone can drain vault.

### I14: Vault mint matches expected
```
vault_token_account.mint == ORCA_MINT (or staking mint)
```

## Slashing invariants (if applicable)

### I15: Slash reduces pool fairly
On slash event: each LST holder loses proportional value, no asymmetric effect.

### I16: Slash doesn't reduce specific user's value
Slashing affects pool-wide ratio, not per-account balances.

## Economic edge cases (fuzz scenarios)

### Sandwich scenarios
1. `attacker.stake(small) → victim.stake(large) → attacker.unstake(small)` — verify attacker doesn't profit
2. `attacker.stake(1) → donate(vault, large) → victim.stake(N) → attacker.unstake(1)` — inflation attack — verify victim isn't 90%-rugged

### Empty pool scenarios
3. `last_user.unstake(all) → vault leftover (rent + virtual)` — verify next staker gets fair price
4. After mass exodus: `non_escrowed = 0` — staking should error, not crash

### Extreme amounts
5. `stake(u64::MAX) → assert mint succeeded or error gracefully`
6. `stake(1)` repeated — accumulate rounding losses to xORCA pool over thousands of small stakes

### Reentrancy
7. If LST is Token-2022 with transfer hook → mid-mint state mutation possible? Trident reentrancy strategy.

## Strategy hints for Trident

```rust
// In fuzz strategy:
strategies! {
    Stake(amount = 1..1_000_000_000),
    Unstake(xorca_amount = 1..1_000_000_000, index = 0..10),
    Withdraw(index = 0..10),
    DonateToVault(amount = 1..1_000_000_000), // simulate direct SPL transfer
    UpdateCooldown(period_s = 0..86400 * 30), // admin action
}
```

Mix instructions randomly, track invariants after each.

## Critical paths

1. **Stake → Unstake → Withdraw cycle** under varying pool state
2. **Multi-user concurrent stake/unstake** (Sealevel-aware — these serialize)
3. **set_cooldown then ongoing operations** — does cooldown change affect existing pending?
4. **Rare states**: empty vault, all liquidity escrowed, very imbalanced ratios

## Validation

Test by introducing intentional bug (e.g., make convert_xorca_to_orca round UP instead of DOWN) — fuzz should detect roundtrip profit within minutes.
