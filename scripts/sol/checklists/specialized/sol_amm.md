# Checklist: Solana AMM (Raydium/Orca/Phoenix)

## Account validation
- [ ] Tick array accounts: key validated via `require_keys_eq!`? (Raydium 2024)
- [ ] remaining_accounts: each indexed account validated?
- [ ] Pool state account: owner + discriminator + key checks?

## Math
- [ ] sqrt_price calc: checked_mul/div used?
- [ ] Tick boundary off-by-one?
- [ ] Fee deducted before or after swap math? Affects rounding direction.
- [ ] Bidirectional rounding: swap A→B and B→A — same direction → profit round-trip

## Liquidity ops
- [ ] First-depositor inflation guard?
- [ ] Donation (direct token transfer to pool) — affects share math?
- [ ] LP token mint discriminator verified?

## Oracle dependency
- [ ] Price feed: staleness check?
- [ ] TWAP window: cardinality, manipulation resistance?
- [ ] Multiple sources?
