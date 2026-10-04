# Checklist: Solana Bridge (Wormhole-class)

- [ ] VAA replay: sequence numbers monotonic, no skip?
- [ ] SignatureSet account: owner + signer verified? (Wormhole 2022 root cause)
- [ ] Guardian set: active index, expiration, threshold?
- [ ] ChainId in message hash? (cross-chain replay)
- [ ] Emitter authorized in config?
- [ ] Token wrap/unwrap math?
