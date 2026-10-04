# Cross-Layer Resource-Limit Mismatch → Liveness (Taxonomy 18.5)

Class: a **liveness-critical** operation (validator vote/attestation, block proposal,
heartbeat, oracle push) must serialize **attacker-inflatable** data and transmit it over a
transport with an **undocumented size/resource limit**. Exceed the limit → the op silently
hard-fails (no chunking / no graceful skip) → missed votes / stalled progress. Chains with
**18.6** (punishment without quorum-survival guard) → validators removed → **chain halt**.

> The limit lives in **node/infra config, not the contract** — invisible to contract-only
> review. You must read the actual node defaults. This is the half most hunters skip.

## Worked case — Axelar 2026 (@marcohextor, $50K, $1B chain, ~$5k attack cost)
- Validators run off-chain `vald`: observe L1 event → generate vote → submit vote over RPC.
- Most validators ran Tendermint with default `max_body_bytes = 1_000_000` (~1 MB RPC cap).
- Attacker emits txs carrying **thousands of events** → vote payload > 1 MB → vote submit fails.
- Axelar had **no minimum-quorum / systemic-failure guard** before counting missed votes
  (18.6) → honest misses punished → maintainers removed below quorum → halt.
- Report: `marcohextor.com/axelar-network`.

## Researcher's approach (the reusable lens — this is what the operator wants captured)
1. **Drop below the contract into node infra.** Read the actual default config the
   validators run (CometBFT/Tendermint `config.toml`, RPC server limits, gossip/p2p caps).
2. **Enumerate liveness-critical ops** (vote, attest, propose, ack) and for each ask:
   *what is the MAX attacker-controllable payload this op must serialize and transmit?*
3. **Find the mismatch:** is there an input the attacker can inflate (events per tx, logs,
   memo, calldata, proof size) so the serialized op exceeds a transport/infra limit?
4. **Chain to the punishment side (18.6):** when the op fails, is the validator punished
   without a guard? Two individually-weak clues (a config cap + a missing guard) woven
   together → halt. Textbook cross-thread synthesis.

## Checklist
- [ ] Locate node config defaults: `max_body_bytes`, `max_tx_bytes`, `max_packet_msg_payload_size`, RPC `max_request_batch_size`, gossip message caps, per-block gas/compute caps.
- [ ] List every liveness-critical op that serializes data over that transport.
- [ ] For each, compute the **worst-case attacker-controllable size** (events, logs, proofs, memos, calldata). Can it exceed the limit?
- [ ] On overflow, does the op **degrade gracefully** (chunk / paginate / skip-and-retry) or **hard-fail silently**?
- [ ] If hard-fail → cross to `gravity_validator.md` §8 (18.6): is there a quorum-survival / systemic-failure guard before punishment?
- [ ] Quantify: how many validators can the attacker knock out per attack round, and what's the cost? (Axelar: ~$5k → below quorum.)

## Targets
CometBFT/Tendermint chains with vote-based maintainers/attesters (cross-chain bridges,
oracle networks, AVS attesters), and any L1/L2 where an off-chain signer pushes
attacker-inflatable payloads over a capped transport. Hunt queue:
`sessions/_methodology/live_targets_consensus.md`.

## Severity
Liveness/halt of a fund-holding chain → **High–Critical** (program-dependent). The size-
limit alone (18.5) without the punishment guard gap (18.6) may only be a transient DoS;
the **composite** is the halt. Verify the punishment path before claiming Critical.

## Cross-refs
- Taxonomy: 18.5 (this), 18.6 (punishment-without-guard), 13.6 (fund liveness)
- `threat_models/validator_set_quorum_integrity.yaml` (vector 6, degradation)
- `checklists/specialized/gravity_validator.md` §8
