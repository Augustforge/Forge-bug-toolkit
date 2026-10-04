# Specialized Checklist: MEV-Boost / PBS

## Relay trust
- [ ] Relay can equivocate (sign two valid blocks) — protocol assumption
- [ ] Proposer slashing for double-signing
- [ ] Relay reputation tracked

## Builder behavior
- [ ] Builder bids verifiable
- [ ] Builder cannot extract from unsigned bundle
- [ ] Bundle inclusion guarantees clear

## Proposer
- [ ] Proposer signs commitments
- [ ] Equivocation slashable
- [ ] MEV revenue distribution to stakers

## Smart contracts integrating MEV-Boost
- [ ] Protocol doesn't assume single block proposer
- [ ] Protocol survives bundle censorship
- [ ] No protocol-level MEV that relies on specific relay
