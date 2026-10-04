# Specialized Checklist: Bridges

## LayerZero v2 specifics
- [ ] DVN config: `requiredDVNCount ≥ 2` (KelpDAO pattern needs 2+)
- [ ] DVN diversity: not all DVNs operated by same entity
- [ ] Optional DVN threshold meaningful
- [ ] `srcChainId` validated in `_lzReceive`
- [ ] Block confirmations adequate per chain

## Wormhole specifics
- [ ] Guardian set check: current set used (not stale)
- [ ] VAA replay protection (`consumedVAAs` mapping)
- [ ] Quorum check: 13/19 guardians
- [ ] Token bridge: wrapped vs canonical asset handling

## Axelar specifics
- [ ] Gateway `validateContractCall` present
- [ ] Source chain allowlist enforced
- [ ] Token transfer integrity verified

## CCIP specifics
- [ ] Source chain selector validated
- [ ] Allowlisted senders enforced
- [ ] Risk Management Network (RMN) status checked

## Generic bridge bugs
- [ ] Replay attack: nonce per source/destination
- [ ] Cross-chain accounting: locked ≡ issued - burned
- [ ] No double-spend across chains
- [ ] No "force finalization" without proof

---

# Post-Verus 2026: Bridge invariant deep checks

Source: Verus-Ethereum bridge $11.58M hack (May 2026) + siblings Wormhole 2022 ($325M) and Nomad 2022 ($190M). Common root cause: **cryptographic verification ≠ semantic verification**. The bridge trusts signatures/proofs, but doesn't validate the semantic contents of the attested payload.

Related artifacts:
- Threat model: [`threat_models/cross_chain_source_destination_binding.yaml`](../../threat_models/cross_chain_source_destination_binding.yaml)
- Sibling lens: [`threat_models/attested_amount_trust_gap.yaml`](../../threat_models/attested_amount_trust_gap.yaml)
- Operational detector: [`bridge_tests/source_amount_grep.sh`](../../bridge_tests/source_amount_grep.sh)
- Adversarial prompt: [`prompts/bridge_message_forge.md`](../../prompts/bridge_message_forge.md)
- Reading note: [`research/_audit_corpus/notes/verus_2026_source_amount.md`](../../research/_audit_corpus/notes/verus_2026_source_amount.md)
- Stop signal: bridge-no-conservation = strong escalate ([`stop_signals.md`](../../../../sessions/_methodology/stop_signals.md))

## Section 1: Source-Amount Conservation (Verus 2026 class)

For **every** bridge entry function on destination chain (`submitImports`, `receiveMessage`, `claimMessage`, `relayMessage`, `completeTransfer`, `process`, `executeMessage`, `redeem`, `unlock`, `mintWithProof`):

- [ ] **Where does payout `amount` come from?** Trace from `_mint/_release/_transfer` arg back to its source. Must originate from **verified** payload field, not attacker-controlled input.
- [ ] **Is there an explicit `require/assert` linking payout amount to verified source-chain field?** E.g., `require(amount <= verifiedPayload.burnedAmount)`. Absence = critical gap (Verus 2026 root cause).
- [ ] **Does the verification step validate semantics, not just integrity?** Sig recovery proves authorship. Merkle proof proves inclusion. Hash binding proves payload-to-hash match. **None of these prove `sum(burned) >= sum(paid)`** — that's a separate semantic check.
- [ ] **Decimal normalization**: if source chain uses different decimals (e.g., Bitcoin sats vs ETH wei), conversion happens **before or after** signature verification? After-verification conversion = potential amplification bug.
- [ ] **Fee accounting**: bridge fees deducted from incoming or outgoing? If asymmetric → attacker can game by exploiting wrong side.
- [ ] **Asymmetry check**: if multiple entry functions, does **one** have the conservation check but another doesn't? Alchemix-class asymmetry signal. Run [`asymmetry_scanner.py`](../../hypothesis/asymmetry_scanner.py).

## Section 2: Message Replay Protection (Nomad 2022 class)

- [ ] **Unique nonce per (source_chain_id, destination_chain_id, sender, recipient, nonce)** — all 5 fields included in replay-protection key. Missing any field = replay vector.
- [ ] **Default trusted state**: if `confirmedMessages[hash] == 0x00` treated as 'confirmed', this is the Nomad bug. Verify default state path explicitly.
- [ ] **Upgrade safety**: did any historical upgrade reset replay-protection storage? `git log --all -- ReplayProtection.sol`.
- [ ] **Cross-deployment replay**: same payload accepted on mainnet vs testnet of same chain? Layer-2 vs L1?
- [ ] **Cross-fork replay**: if source chain forked (e.g., ETH ↔ ETC, or L2 fork), can pre-fork message be replayed post-fork on destination?

## Section 3: Notary / Validator Set Independence

- [ ] **N-of-M threshold sane?** Ronin 5/9 was too low. Verus 8/15 sufficient threshold but operational concentration?
- [ ] **Operators independent entities?** Check `validators` array on-chain — separate orgs, separate hosting, separate jurisdictions?
- [ ] **Geographic distribution**: are all validators in same country / jurisdiction? Single-state actor risk.
- [ ] **Key rotation policy**: defined? automated? validator can opt-out? what if all keys compromised simultaneously (CEO arrest = Multichain)?
- [ ] **Bonded amounts**: are validators bonded such that misbehavior is economically irrational? If bonded $X but can drain $Y where Y >> X — bonded-actor attack viable.
- [ ] **Slashing conditions**: well-defined? slashable for **signing semantically-invalid payloads**? Or only for double-signing? Most slashing covers integrity, not semantics — same gap as the verification.

## Section 4: Finality Assumption

- [ ] **Source finality**: how many confirmations does bridge wait before considering source-chain event final? Per chain (ETH PoS != BTC PoW != Solana != Cosmos)?
- [ ] **Source reorg handling**: what if source chain reorgs **after** bridge confirms event? Compensation? Revert mechanism? Or stuck-with-bad-state?
- [ ] **Destination finality**: same question reversed — if destination chain reorgs after mint, is source `burned` event idempotent?
- [ ] **Cross-chain ordering**: if 2 messages arrive out-of-source-order, does protocol handle? Or assume strict ordering (Nomad-class bug area)?
- [ ] **Time skew**: blocks have timestamps. Source timestamp manipulated → destination conditions (deadlines, expiry) bypassed?

## When to escalate

If **Section 1** check fails (no conservation assertion linking payout to verified source field) AND bridge entry function found via [`source_amount_grep.sh`](../../bridge_tests/source_amount_grep.sh) — this is a strong escalate signal per [`stop_signals.md`](../../../../sessions/_methodology/stop_signals.md). Move to J2 (proof construction). Severity ceiling: Critical.
