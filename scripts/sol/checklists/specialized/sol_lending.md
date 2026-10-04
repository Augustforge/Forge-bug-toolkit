# Checklist: Solana Lending (Solend/MarginFi/Kamino)

## State flags
- [ ] Flash loan flag (`ACCOUNT_IN_FLASHLOAN` or equivalent) — checked in EVERY instruction?
- [ ] Liquidation flag — bypass routes?
- [ ] Paused flag — do all instructions respect it?

## Health check
- [ ] Does every borrow/withdraw trigger a health check?
- [ ] Health check uses fresh oracle price?
- [ ] Partial vs full liquidation math correct?

## Oracle
- [ ] Pyth/Switchboard staleness check (max_age)?
- [ ] Confidence interval check (price.confidence < threshold)?
- [ ] Manipulation-resistant aggregation?

## Exchange rate
- [ ] Share-to-asset conversion: precision loss bounded?
- [ ] Inverse op symmetry: mint vs redeem rounding direction asymmetric?
- [ ] Kamino-class: redeem more than deposited?

## Bad debt
- [ ] Bad debt absorption mechanism?
- [ ] Liquidator incentive sufficient at edge cases?
- [ ] Dust liquidation gas-economical?
