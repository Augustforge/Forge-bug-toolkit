# Gravity / M-of-N Bridge — Validator-Set Quorum Checklist

Class: Cosmos-Gravity, Ronin-style, and custom lock-mint bridges that approve transfers /
valset updates by **cumulative validator voting power ≥ 2/3**.

**Scope discipline first** (see `feedback_ton_self_destructive_severity`, threat model
`validator_set_quorum_integrity.yaml`): theft of ≥2/3 signing keys (Gravity $5.4M 2026,
Ronin $625M 2022) is the **declared** trust model — NOT a findable bug unless the program
pays for centralization/key-custody. FINDABLE = a logic flaw letting a SUB-quorum (or
replayed/forged set) pass verification, OR a concentration claim where the program accepts it.

Tool: `scripts/web3/specialized/gravity_validator_hunter.py`

## 1. updateValset power re-check
- [ ] Locate `updateValset` / `updateValsetAndSubmitBatch`
- [ ] Current set's signatures verified ≥ threshold? (expected)
- [ ] **Is `sum(newValset.powers) >= powerThreshold` asserted for the NEW set?**
- **Bug:** quorum signs a routine rotation → attacker substitutes an under-threshold / attacker-controlled new set → all later batches trivially pass. (Code4rena Gravity 2021)

## 2. Signer deduplication
- [ ] Find the signature-counting loop (`checkValidatorSignatures`)
- [ ] Are signers forced strictly-increasing / tracked in a used-map?
- **Bug:** without dedup, ONE validator's signature is counted N times → satisfies N-of-M alone

## 3. Checkpoint / nonce replay
- [ ] `makeCheckpoint` includes BOTH valset nonce AND event/batch nonce inside the hash?
- [ ] Is there a processed-batch map / monotonic nonce enforcement?
- **Bug:** old valid (valset, batch) re-submitted for a second payout (Nomad-adjacent)

## 4. Cumulative-power arithmetic
- [ ] Power summation uses checked arithmetic / wide enough type?
- **Bug:** overflow/wrap makes tiny powers compare ≥ threshold

## 5. EVM ↔ native signature asymmetry
- [ ] EVM side hardens ecrecover (s ≤ N/2, v ∈ {27,28})?
- [ ] Does the Cosmos/native side apply the SAME hardening?
- **Bug:** malleable sig accepted on one side, rejected on the other → freeze / one-sided divergence (Gravity Cosmos-side malleability, Maxwell Dulin writeup)

## 6. submitBatch value conservation
- [ ] Fee-on-transfer / deflationary token: credited amount == received amount?
- **Bug:** accounting drift → insolvency over many batches

## 8. Punishment / removal without quorum-survival guard (DEGRADATION)
Sections 1-6 attack quorum **verification** (forge/pass approval). This attacks quorum
**survival** — the math can be flawless and the set still dies from the punishment side.
- [ ] Locate the missed-vote / jailing / `removeValidator` / `removeMaintainer` / tombstone handler
- [ ] **Before removal, is there a systemic-failure guard** (`failedThisRound < N% of set`) **or a quorum-survival check** (`liveQuorum after removal >= threshold`)?
- [ ] Can an attacker make many honest validators miss *simultaneously*? Pair with **taxonomy 18.5**: a liveness-critical op (vote) serialized over a transport with an undocumented limit (CometBFT `max_body_bytes=1MB`, RPC cap) — inflate the payload past it → infra-wide vote failure.
- **Bug (composite 18.5×18.6):** oversized poll → all honest votes exceed RPC limit → every miss punished (no guard) → maintainers removed below quorum → **chain halt**. (Axelar 2026, marcohextor, $1B chain, $5k cost, $50K bounty)
- Cross-ref: `checklists/specialized/cross_layer_resource_limit.md` for the size-limit half.

## 7. Concentration (severity amplifier + standalone claim)
- [ ] Supply latest valset to `gravity_validator_hunter.py --valset-json`
- [ ] **Nakamoto coefficient** = min validators to reach 2/3
  - ≤3 → High concentration; compromising that few = full control
  - ≤5 → low Byzantine diversity
- [ ] Single validator ≥ 1/3 power → can veto/block quorum
- Use to amplify any other finding's severity, or as a centralization submission where accepted.

## Severity rubric
| Finding | Default |
|---|---|
| updateValset no power re-check (sub-quorum substitution) | Critical |
| Missing signer dedup | Critical |
| Checkpoint/nonce replay | High-Critical |
| Power overflow | High |
| EVM-vs-native malleability → freeze | High (DoS) |
| fee-on-transfer drift | Medium-High |
| Punishment w/o quorum-survival guard → halt (18.6, +18.5 trigger) | High-Critical *(liveness)* |
| Nakamoto ≤3 concentration | High *(program-dependent)* |
| Key theft ≥2/3 | **Out of scope** unless program pays for it |

## Cross-refs
- threat model `validator_set_quorum_integrity.yaml`
- `bridge_admin_compromise_chain.yaml` (threshold size/OPSEC) + `attested_amount_trust_gap.yaml` (amount conservation)
- `checklists/specialized/bridge.md`, `prompts/bridge_message_forge.md`
