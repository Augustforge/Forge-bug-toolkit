# Specialized Checklist: Restaking (EigenLayer-likes)

## Slash propagation
- [ ] Withdrawal delay > slash propagation window
- [ ] Slash from AVS → core has finality before withdrawal completes
- [ ] No slash race condition (withdraw before slash applies)

## Operator
- [ ] Operator opt-in process secure
- [ ] Operator deregistration delay > operation timeframe
- [ ] Operator commission settable, but bounded

## AVS commitment
- [ ] AVS authorization verified per slash
- [ ] AVS withdrawal of stake delayed
- [ ] Multiple AVSs operate independently

## Withdrawal queue
- [ ] Queue position fair (no MEV jumping)
- [ ] Cancel handling: cancelled withdrawal doesn't grief queue
- [ ] Queue depth limits if any

## Reward distribution
- [ ] Reward calculation accurate per-operator
- [ ] No double-claim across AVSs
- [ ] Fee accrual timing correct

## Operator collusion
- [ ] No incentive for operators to slash each other artificially
- [ ] Voting weight in slashing decisions distributed
