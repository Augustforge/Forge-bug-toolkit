# Prompt: Relayer Censors

Lens: cross-chain protocols depend on relayer/executor/DVN/guardian to forward messages. What if relayer cherry-picks messages? Drops some, includes others? Reorders for advantage?

> Examples: Nomad Bridge ($190M, 2022 — replay enabled by trusted root), LayerZero KelpDAO ($292M — DVN trust), pre-V2 Wormhole guardian assumptions.

## Questions

1. **Who has relay authority?** Single entity, set of N, permissioned, permissionless?
2. **What can be relayed?** Arbitrary messages? Only matched src/dst? Replay-protected?
3. **What if relayer drops legitimate message?** User funds stuck? Escape hatch? Time-out + permissionless re-relay?
4. **What if relayer adds malicious message?** Without source-chain verification — protocol accepts as-if valid
5. **What if relayer reorders 2+ messages?** Message N processed before N-1 → state inconsistency
6. **Replay across chains?** Same payload accepted on multiple destinations?
7. **Replay across deployments?** L1 → L2 mainnet vs testnet — does payload distinguish?

## Specific systems

- **LayerZero**: DVN count, executor trust, ULN config — `requiredDVNCount` ≥ 2 minimum
- **Wormhole**: 13/19 guardian quorum — single guardian compromise insufficient, but 13 compromised = takeover
- **IBC**: relayer permissionless, but `verifyMembership` proofs required
- **Axelar**: validator set + threshold, plus Gateway `validateContractCall`
- **CCIP**: Risk Management Network as second layer
- **Custom**: relayer bonded? slashed for misbehavior? Verifiable proof attached?

## Output

For each "what if relayer adversarial" hypothesis:
1. **Code location**: where message is processed without source verification
2. **Adversarial action**: drop / inject / reorder / replay
3. **Trust assumption violated**
4. **Required malicious party count**: 1 / threshold / all
5. **Mitigation gap**: verification missing

## Anti-pattern

Don't only check "are guardians verified?". Check "what does protocol implicitly trust about relayer ordering, completeness, exclusivity?"

---

## Source:

(paste cross-chain protocol contracts — message processing, verification logic below)
