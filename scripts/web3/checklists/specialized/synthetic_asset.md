# Specialized Checklist: Synthetic Assets (Synthetix, UMA, Mirror)

## Oracle dependence
- [ ] Multiple oracle sources
- [ ] Oracle staleness check
- [ ] Oracle deviation check (vs prior, vs Chainlink)
- [ ] Manipulation-resistant (TWAP / Chainlink)

## Liquidation
- [ ] Threshold below 150% collateral
- [ ] Bonus structured
- [ ] Backstop for bad debt

## Debt position
- [ ] Position math correct with shifting prices
- [ ] Socialized debt model (Synthetix) or isolated
- [ ] Position closure refund correct

## Synthetic asset minting
- [ ] Collateral locked before mint
- [ ] Mint fee charged
- [ ] Mint cap if any

## Snapshot timing for liquidation
- [ ] Use oracle at liquidation time, not at position open
- [ ] No same-block manipulation of oracle to trigger / avoid liquidation
