# Specialized Checklist: Lending Protocols

## Liquidation
- [ ] Liquidation bonus capped (e.g., 5-20%)
- [ ] Liquidator profit cannot underflow at high price drop
- [ ] L2 deployments check sequencer uptime feed
- [ ] Bad debt absorption mechanism (insurance fund / socialization)

## Interest rate model
- [ ] Rate at 100% utilization doesn't overflow
- [ ] Rate change rate-limited
- [ ] Rate cannot be negative

## Collateral oracle
- [ ] Chainlink (not just spot from low-liq pool)
- [ ] Staleness checked
- [ ] Sequencer feed for L2
- [ ] Fallback oracle on outage

## Borrow path
- [ ] Health factor check at use time AND continuously during tx
- [ ] No flash-loan repayment race exploitable
- [ ] LTV computed from current oracle, not lagging

## Sequencer downtime
- [ ] All liquidations gated by sequencer-up
- [ ] Force-exit path for L2 force-include

## ERC-20 quirks
- [ ] Fee-on-transfer tokens handled (balance diff pattern)
- [ ] Rebase tokens excluded or specially handled
- [ ] Tokens without revert-on-fail handled (`SafeERC20`)
