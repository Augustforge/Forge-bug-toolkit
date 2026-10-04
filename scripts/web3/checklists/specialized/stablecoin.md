# Specialized Checklist: Stablecoins (DAI, FRAX, LUSD, others)

## Peg defense
- [ ] PSM (Peg Stability Module) swap fees set
- [ ] PSM ceiling on supply absorbed
- [ ] Multiple peg defense mechanisms (over-collateral + arb + PSM)

## Redemption
- [ ] Fixed-rate redemption: full back at $1?
- [ ] Market-rate redemption: discount applied?
- [ ] Redemption permissioned (LUSD) or open (DAI)
- [ ] Redemption favors least-collateralized positions

## Depeg recovery
- [ ] Mechanism on -5% deviation
- [ ] Mechanism on +5% deviation
- [ ] Emergency shutdown if extreme

## Stability fee
- [ ] Fee accrual rate set
- [ ] Fee rate update timelock
- [ ] Fee compounding correctly

## Vault (CDP)
- [ ] Liquidation threshold
- [ ] Liquidation bonus
- [ ] Bad debt absorption (surplus / debt buffer)

## Algorithmic vs fiat-backed
- [ ] Risk model documented
- [ ] User awareness of model
- [ ] Worst-case scenario considered
