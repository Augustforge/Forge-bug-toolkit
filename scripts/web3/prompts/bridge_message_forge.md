# Prompt: Bridge Message Forge

Lens: cross-chain bridges and attested-payload systems consume signed messages (notary state roots, guardian VAAs, operator reports, oracle bundles). They cryptographically verify signatures + Merkle proofs + hash bindings — but rarely verify **semantic invariants** inside the attested payload. Two attacker postures:
- **Lone attacker** forges payload contents (Verus 2026, Nomad 2022)
- **N-of-M collusion** of legitimate signers (Multichain CEO, Ronin Lazarus, theoretical Thorchain bonded coalition)

Complement to [`relayer_censors.md`](relayer_censors.md) (upstream — transit/ordering) — this prompt is **downstream** (verification gap on destination).

> Examples: Verus-Ethereum bridge ($11.58M, 2026 — source-amount conservation gap), Wormhole Solana ($325M, 2022 — uninitialized signatureSet trusted), Nomad ($190M, 2022 — default `0x00` merkle root accepted), Ronin ($625M, 2022 — 5/9 validators compromised), Multichain ($130M, 2023 — CEO controlled MPC shares).

---

## Section A: Lone-Attacker Forge

Attacker has no signing privilege but can submit any payload to destination chain as long as cryptographic envelope is valid.

### Questions

1. **What does the verification step actually prove?**
   - Signatures recovered correctly → proves *who* signed
   - Merkle proof valid → proves *inclusion in attested set*
   - Hash binding match → proves *payload integrity (no tampering after attestation)*
   - **None of these prove**: payload amounts/prices/states reflect reality on source chain
2. **Where does the payout amount come from on destination?** Trace from `_mint/_release/_transfer` arg back. Verified payload field, attacker-controlled input, or hybrid?
3. **Is there a downstream semantic check linking attested payload to verified source-chain state?** E.g., `require(amount <= verifiedPayload.burnedAmount)`. **Absence = Verus 2026 class root cause**.
4. **Can attacker create the attestation cheaply on source?** Cost of forging valid payload (e.g., send $0.01 VRSC to bridge, get notaries to sign state root containing it) — should be `proportional` to potential gain, but often isn't.
5. **Is there a sentinel value that means 'trusted'?** Default `0x00` merkle root, empty signature set, uninitialized account treated as confirmed = Nomad 2022 / Wormhole 2022 class.
6. **Replay across (src_chain, dst_chain, sender, nonce)?** All 5 fields needed in replay-protection key. Missing any = forge opportunity through replay variant.
7. **Account-based attestation (Solana/Anchor)?** If `signature_set` or `guardian_set` passed as account arg — is account creation path validated? Wormhole 2022: attacker created fake account, destination trusted it.

---

## Section B: N-of-M Collusion (bonded actors)

Attacker controls M out of N signers (legitimately bonded/whitelisted/elected) and submits semantically-invalid but cryptographically-valid payload.

### Questions

1. **What threshold M unlocks attack?**
   - Ronin: 5/9 (55% — too low for bridge)
   - Wormhole: 13/19 (68%)
   - Verus: 8/15 (53% — too low for bridge)
   - Thorchain TSS: ⅔+1 (variable)
2. **What's the bond economics?** Total bonded value vs. potential drain value. If `total_bond << bridge_TVL`, slashing is rational risk for attacker.
3. **Are signers independent entities?** Same org running 8 of 15 notaries on same cloud = effectively 1-of-1. Verify via on-chain validator addresses + off-chain attribution.
4. **Geographic / jurisdictional concentration?** If all signers in same country, state-level coercion = Multichain class.
5. **Key custody**: do signers control their keys, or shared infra (CEO controlled multichain MPC)? Centralization through ops = single point of failure even with M signers.
6. **What payload could M colluders sign that protocol would accept?**
   - Sign a fake state root showing $X burned when nothing burned
   - Sign cross-chain export with attacker's recipient
   - Sign price update that drains lending protocol via stale-price liquidation
   - Sign slashing report saying "no slashing happened" when slashing did happen (LRT class)
7. **Slashing for semantic misbehavior?** Slashing usually covers double-signing (integrity), not signing-semantically-invalid-payload. If slashing doesn't catch semantic misbehavior → bonded actors free to lie within signing envelope.

---

## Output

For each "what if message forged or signers colluded" hypothesis:
1. **Code location**: destination contract function consuming attested payload without semantic check
2. **Adversarial action**: lone forge / N-of-M collusion / what payload contents
3. **Trust assumption violated**: what the protocol silently assumes the signer set verifies
4. **Required malicious party count**: 0 (forge) / M (collusion threshold)
5. **Economic feasibility**: cost-to-attack vs reward
6. **Mitigation gap**: specific check missing (e.g., conservation assert, deviation bound, slashing condition)

---

## Anti-pattern

- "If signers verify the payload, payload must be valid." — **Wrong**. Signers verify what they're asked to verify. If protocol asks them to sign state root hash, they verify hash, not contents.
- "Threshold N>50% solves it." — **Wrong**. Threshold solves integrity (no rogue minority), not semantics (majority can still sign invalid payload).
- "Slashing makes it expensive." — **Wrong** unless slashing covers semantic misbehavior, not just integrity violations.

---

## Cross-link

- Threat model: [`threat_models/cross_chain_source_destination_binding.yaml`](../threat_models/cross_chain_source_destination_binding.yaml) (bridge-specific)
- Sibling lens (broader): [`threat_models/attested_amount_trust_gap.yaml`](../threat_models/attested_amount_trust_gap.yaml) (LRT/oracle/intent-solver siblings)
- Checklist: [`checklists/specialized/bridge.md`](../checklists/specialized/bridge.md) Sections 1-3
- Operational detector: [`bridge_tests/source_amount_grep.sh`](../bridge_tests/source_amount_grep.sh)

---

## Source:

(paste cross-chain bridge contract or attestation consumer code — verification logic + payout logic below)
