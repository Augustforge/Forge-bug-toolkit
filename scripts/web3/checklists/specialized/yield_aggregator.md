# Specialized Checklist: Yield Aggregators (Yearn, Beefy)

## Strategy switching
- [ ] Switch authorized
- [ ] Switch timing protected (MEV between switch + first deposit)
- [ ] User has notice before switch (timelock?)

## Fee calculation
- [ ] Fee on gross profit vs net profit clarified
- [ ] Performance fee floor (e.g., share price never decreases)
- [ ] Management fee calculation correct over time

## Share dilution at rebalance
- [ ] Rebalance doesn't dilute existing shares
- [ ] OR: rebalance mints/burns shares atomically

## Underlying protocol invariants
- [ ] If underlying breaks, aggregator handles gracefully
- [ ] Aggregator doesn't blindly trust underlying state

## Profit accrual
- [ ] Profits credited proportionally to share at accrual time
- [ ] No flash-loan share-acquisition before profit credit
