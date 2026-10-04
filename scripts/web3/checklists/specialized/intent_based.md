# Specialized Checklist: Intent-Based Protocols (CowSwap, UniX)

## Intent lifecycle
- [ ] Intent created with clear constraints
- [ ] Intent matched by solver / filler
- [ ] Intent settled atomically (or fails gracefully)

## Filler gaming
- [ ] Filler can't extract more than intent expects
- [ ] Filler can't grief by partial fills
- [ ] Filler can't reorder intents to extract MEV

## Replay
- [ ] Intent has nonce / unique id
- [ ] Cannot replay intent on different chain
- [ ] Cannot replay after expiry

## Settlement
- [ ] Settlement price = best of competing fillers
- [ ] No price manipulation between intent creation and settlement
- [ ] Settlement window adequate

## Cross-chain intents
- [ ] L1↔L2 message integrity
- [ ] No double-settlement across chains
