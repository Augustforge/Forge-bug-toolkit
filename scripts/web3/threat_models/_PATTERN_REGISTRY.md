# Threat Model Pattern Registry — Conceptual Axes

**Goal**: classify all TM YAMLs by conceptual axes for J0 hypothesis generation.

When you see a target → spot the axes that apply → look for TMs along those axes → generate hypotheses. This is more powerful than per-detector matching: axis-level reasoning surfaces hypotheses that a single TM wouldn't emit.

**Update protocol**: after each new TM YAML — classify it under an existing axis or add a new one.

---

## Axis 1: Cryptographic verification ≠ semantic verification

**Core insight**: cryptographic envelope validity (signatures, Merkle proofs, hash bindings) proves authorship/integrity, **not** semantic claims about the state inside the payload. A bridge having a signature ≠ the bridge having accurate amount accounting.

**TMs**:
- `tss_validator_extraction.yaml` — a bonded validator participates in N legitimate signing ceremonies, reconstructs the key offline (Thorchain 2026). The cryptographic protocol was followed strictly, the semantic outcome catastrophic.
- `cross_chain_source_destination_binding.yaml` — the bridge verifies sigs/Merkle/hash, does not verify source amount conservation (Verus 2026, Wormhole 2022, Nomad 2022).
- `attested_amount_trust_gap.yaml` — broader sibling: any consumer of off-chain-attested payloads (LRT operator reports, Pyth bundles, intent solver fills, restaking attestations).
- `erc4337_signature_replay.yaml` — UserOp/ERC-1271 signature validity ≠ intent validity. The same crypto signature is valid cross-account, cross-context, cross-chain if the hash construction doesn't commit to (chainId, entryPoint, account, application context).

**Open siblings** (candidates for new TMs along this axis):
- `bridge_finality_assumption.yaml` — source-chain finality verified only via "X confirmations passed", not via cryptographic state finality (sequencer reorg, L2 finality gap)
- `oracle_deviation_bound_missing.yaml` — oracle payload signed but no downstream deviation bound check
- `intent_solver_attested_fill.yaml` — UniswapX/CowSwap class: solver-signed fill price without verification against oracle / on-chain swap price at execution
- `lrt_operator_slashing_report.yaml` — EigenLayer/Symbiotic: operator-signed slashing reports not cross-checked with on-chain Slashed events

**Hunting heuristic for J0**:
> For every signature/proof verification at any protocol layer ask: **what exactly does this verification prove?** Authorship? Inclusion? Integrity? What does it **not** prove? Where does downstream code touch a semantic claim of the payload contents without a separate semantic check?

---

## Axis 2: Asymmetric defense / post-bounty drift

**Core insight**: defense is applied non-uniformly — one code path is protected, a sibling path is not. Or the paid bounty fix is narrow, sibling variants of the class remain.

**TMs**:
- `post_bounty_variant_drift.yaml` — past paid bounty with a potentially narrow fix. Thorchain α-shuffle 2022 → c-split 2026 = a 4-year window between siblings.
- (de facto via `comment_miner.py` + `asymmetry_scanner.py`, not a separate YAML)

**Open siblings**:
- `paired_function_modifier_asymmetry.yaml` — auto-applied for existing DeXe/Alchemix patterns (covered in `successful_patterns.md` #1, #2 but not in YAML)
- `multi_path_guard_drift.yaml` — Alchemix-class: `_allocate` vs `_allocateWithSwap` (same protocol, different paths)
- `audit_baseline_storage_drift.yaml` — Mezo-class storage layout drift between the audit baseline and current

**Hunting heuristic for J0**:
> For every defensive measure (modifier, require, validation) ask: is it applied symmetrically to all sibling paths? If the defense appeared after a paid bounty — was the fix narrow?

---

## Axis 3: Bonded-actor adversarial economics

**Core insight**: a legitimate role (validator, operator, oracle publisher, intent solver, sequencer) with signing privilege can weaponize its legitimate capability — if bond << potential gain, the attack is rational.

**TMs**:
- `tss_validator_extraction.yaml` (partial — also Axis 1)
- (de facto via prompts/_actors_index.md, not a separate YAML)

**Open siblings**:
- `validator_bond_economics_gap.yaml` — bond cost vs drain potential, slashing semantic coverage
- `sequencer_reorder_extraction.yaml` — L2 sequencer extracts MEV through reordering

**Hunting heuristic for J0**:
> For every actor with signing/relay/oracle privilege: **how much are they bonded** vs **how much can they potentially drain**? Does slashing cover semantic misbehavior or only integrity?

---

## Axis 4: Custody exit-path / privileged extraction

**Core insight**: a contract that HOLDS third-party funds (bridge locked assets, LP locker,
vault, escrow) is safe on the happy-path but falls when an EXIT-path or the quorum-verification
LOGIC is unguarded. Enumerate every way assets leave + every privileged actor. Distinct from
Axis 3 (bonded-actor economics) — here it's the code-level integrity of the release path, not
the bond math. Seeds: Gravity Bridge ($5.4M, 2026), DxSale/DxLock ($7.3M, 2026).

**TMs**:
- `validator_set_quorum_integrity.yaml` — M-of-N bridge quorum LOGIC: updateValset cumulative-power re-check, signer dedup, checkpoint/nonce replay, power overflow, EVM-vs-native malleability. (Scope note: key-theft itself = declared trust model, NOT findable.)
- `liquidity_locker_privileged_unlock.yaml` — locker/vesting/escrow with owner-mutable lock params (setFee/setUnlockTime) or emergency-withdraw over pooled custody → release others' funds (DxSale 2026).

**Open siblings**:
- `vault_emergency_withdraw_bypass.yaml` — vault admin path bypasses per-user accounting
- `escrow_arbiter_unilateral_release.yaml` — single arbiter releases escrow without dual-consent

**Hunting heuristic for J0**:
> For every contract holding others' funds: list ALL exit-paths (withdraw/unlock/submitBatch/migrate/emergency) and ALL privileged actors. For each: is there a timelock / guardian / quorum-integrity check? The happy-path may be fine — the exit-path breaks. Filter through designed-trust-vs-logic-bug (see `hypothesis_generation.md` anti-patterns).

---

## Axes coverage gaps (where TMs are lacking)

After 5 TMs (as of 2026-05-19), 3 axes are partially covered:

| Axis | TMs covering | Open candidates |
|---|---|---|
| Crypto ≠ semantic | 4 TMs | 4 candidates |
| Asymmetric defense | 1 TM | 3 candidates |
| Bonded actor economics | 1 TM (partial) | 2 candidates |

**Action**: if a hunter is working a target and spots a new axis (e.g., "timing assumption violations") — add the axis here. If 2+ candidate TMs of one axis accumulate — appoint TM authoring (per `_INDEX.md` Steps 1-10).

---

## How to use this in J0

1. Run `apply.py --target $T` — gets matched TMs based on `applies_when`
2. **Plus** — open this file. For the protocol_class, which axes apply?
3. For each axis: which "open siblings" (candidate TMs) could apply to this target?
4. Add candidate hypotheses to `hypothesis_candidates.md` even if no TM exists for them
5. If a candidate manifests in J9 (confirmed) → trigger TM authoring (`_INDEX.md` Steps 1-10)

This is the **conceptual lens layer** above per-TM matching. Without it the toolkit catches known axes; with it — it surfaces unknown siblings.

---

## Cross-link

- [_INDEX.md](_INDEX.md) — catalog + authoring guide
- [`apply.py`](apply.py) — runtime matcher
- [`sessions/_methodology/successful_patterns.md`](../../sessions/_methodology/successful_patterns.md) — confirmed instances per pattern
- [`sessions/_methodology/gap_review.md`](../../sessions/_methodology/gap_review.md) — quarterly trigger conditions for new axes
- [`_coverage_map.md`](../_coverage_map.md) — per-detector view (orthogonal to this axis view)
