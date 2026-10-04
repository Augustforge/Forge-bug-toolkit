# Target Routing — Single Decision Page

**When Claude sees a target → it reads this file → understands which direction to move.**

This meta-doc is the entry point for `/hunt` Phase 2.5 and `/deephunt` J0. It answers the question: *given chain.json + source code, which detectors / TMs / checklists / prompts to apply?*

Without this doc Claude has to remember the cross-references between `_coverage_map.md`, `_actors_index.md`, `threat_models/_INDEX.md`, `threat_models/_PATTERN_REGISTRY.md` and a dozen scripts. With it — a single lookup table.

---

## ⚠️ Core principle: auto-routing is ADDITIVE, not EXCLUSIVE

Auto-classifiers (bridge_detector, future vault/oracle/LRT detectors) add tags. They **do not cancel** general detectors (`asymmetry_scanner`, `comment_miner`, `spec_miner`, `vault_hunter`, etc.) and **do not cancel** other-class checks.

**Multi-class targets are the 2026 reality**:
- AllBridge = bridge + AMM + staking + governance (4 classes)
- Aave V3 = lending + cross-chain (2 classes)
- EigenLayer = restaking + LRT + slashing (3 classes)
- Wormhole-built apps = bridge + custom logic per app

→ If bridge_detector returns STRONG → bridge artifacts auto-apply. **Plus** vault_detector / oracle_detector / etc. still run and may add their own tags. **Plus** general detectors (asymmetry / comment / spec / vault_hunter / amm_hunter) run unconditionally regardless of classification.

**Hunting a multi-class target = union of all matched classes**, not first-matched-only.

---

## Auto-classifiers (run FIRST in every hunt)

They modify `_tags.txt` automatically. Apply.py picks up their output. **Run unconditionally** in Phase 2.5 / J0 after chain_detect.py.

| Class | Detector | Output tags |
|---|---|---|
| **Bridge / attested-payload** | `hypothesis/bridge_detector.py` | `protocol_class:bridge`, `bridge`, `attested-payload`, `<framework>` (wormhole/layerzero/axelar/ccip/stargate/etc.) |
| **Account Abstraction (ERC-4337)** | `hypothesis/aa_erc4337_classifier.py` | `protocol_class:account-abstraction`, `erc4337`, `aa`, `smart-account`, `<framework>` (entrypoint-v07/zerodev-kernel/safe-account/biconomy/etc.) |
| Vault (ERC-4626) | _(TBD — generic protocol_class_detector backlog)_ | `protocol_class:vault`, `erc4626` |
| Oracle consumer | _(TBD)_ | `protocol_class:oracle`, `pyth|chainlink|redstone` |
| LRT / restaking | _(TBD)_ | `protocol_class:restaking`, `eigenlayer|symbiotic` |

→ When new auto-classifiers are added, always update this table.

---

## Routing decisions per `protocol_class`

### `protocol_class:bridge` (post-Verus 2026)

**Trigger**: `bridge_detector.py` outputs a STRONG verdict OR `_tags.txt` has `protocol_class:bridge`.

**Auto-applied artifacts** (Claude must open all):

| Artifact | Where | Why |
|---|---|---|
| 🎭 `threat_models/cross_chain_source_destination_binding.yaml` | applied via `apply.py` | Generates 6 instantiated hypotheses about source-amount conservation |
| 🎭 `threat_models/attested_amount_trust_gap.yaml` | applied via `apply.py` | Sibling lens — broader (LRT/oracle/intent-solver if relevant tags also present) |
| 🤖 `bridge_tests/source_amount_grep.sh` | run unconditionally | Static detector — flags entry functions without conservation assertions |
| 🤖 `bridge_tests/check_bridges.sh` | run unconditionally | LayerZero DVN config + framework-specific checks |
| 📋 `checklists/specialized/bridge.md` Sections 1-4 | read manually | 4 sections: Source-Amount Conservation, Replay Protection, Notary Independence, Finality Assumption |
| 🧠 `prompts/bridge_message_forge.md` | apply lens | Lone-forge + N-of-M collusion adversarial |
| 🧠 `prompts/relayer_censors.md` | apply lens (upstream complement) | Relayer cherry-pick / drop / reorder |
| 📚 `research/_audit_corpus/notes/verus_2026_source_amount.md` | required reading | Canonical case study |
| 📚 `_known_findings.jsonl` IDs `verus-2026-source-amount-forge`, `wormhole-2022-signature-bypass`, `nomad-2022-merkle-root-init` | read summaries | Historical class siblings |
| 📜 `threat_intel.md` §8 | read | Class framing + cumulative loss tally |

**Phase 2.5 / J0 escalate signal**: if `source_amount_grep.sh` found bridge entry functions but **0 conservation assertions** → strong escalate per `stop_signals.md`. Severity ceiling: Critical.

**If no findings after full pass**: outcome FALSE_REFUTED_BY_READ → `calibration_log.jsonl` with class=`bridge-cross-chain`.

**Live hunt queue**: [`sessions/_methodology/live_targets_bridges.md`](../../sessions/_methodology/live_targets_bridges.md) — priority-ranked bridge programs.

---

### `protocol_class:account-abstraction` (post-Cantina 2025 advisory)

**Trigger**: `aa_erc4337_classifier.py` outputs a STRONG verdict OR `_tags.txt` has `protocol_class:account-abstraction` / `erc4337`.

**Auto-applied artifacts**:

| Artifact | Where | Why |
|---|---|---|
| 🎭 `threat_models/erc4337_signature_replay.yaml` | applied via `apply.py` | Generates 6 instantiated hypotheses (cross-account replay, ERC-1271 reuse, paymaster drift, initCode frontrun, modular replay, bundler simulation divergence) + 5 executable grep checks |
| 🤖 `detectors/erc4337_issues.py` | Slither custom detector | Static analysis pass |
| 🤖 `specialized/aa_erc4337_hunter.py` | run unconditionally | Hunter-style scan |
| 📋 `checklists/specialized/aa_erc4337.md` | read manually | 7 sections: Signature Validation, Paymaster Griefing, Bundler Griefing, EntryPoint Auth, Aggregator, Upgrade/Recovery, Composability |
| 📚 `_known_findings.jsonl` IDs `erc4337-2025-calldata-hash-collision`, `erc4337-2025-erc1271-signature-reuse`, `erc4337-2025-paymaster-unbounded-sponsorship`, `erc4337-2025-bundler-initcode-frontrun` | read summaries | 4 Cantina-advisory patterns |
| 🧠 [_PATTERN_REGISTRY Axis 1](threat_models/_PATTERN_REGISTRY.md) | conceptual lens | Same root cause class as bridges (crypto verify ≠ semantic verify) — apply cross-axis hypotheses |

**Phase 2.5 / J0 escalate signal**: framework detected without an EIP-712 domain separator in `isValidSignature` → cross-context signature replay likely. Severity ceiling: High.

**If no findings after full pass**: outcome FALSE_REFUTED_BY_READ → `calibration_log.jsonl` with class=`erc4337-account-abstraction`.

---

### `protocol_class:mpc-custody` or tag `tss`

**Trigger**: target uses TSS/MPC threshold sig (GG18/GG20/FROST/threshold BLS).

| Artifact | Where |
|---|---|
| 🎭 `threat_models/tss_validator_extraction.yaml` | apply.py |
| 📋 `checklists/specialized/tss_mpc.md` | manual |
| 🧠 `prompts/validator_extracts.md` | apply lens |
| 🧠 `prompts/bonded_actor_threat.md` | apply lens |
| 📚 `research/_audit_corpus/notes/` (Thorchain TSSHOCK once added) | reading |
| 📜 `threat_intel.md` §7 | read |
| 🎓 `sessions/_methodology/learning_paths/tss.md` | if accuracy <30% per calibration |

---

### Any target with a disclosed past paid bounty

**Trigger**: rekt.news / Solodit / Verichains shows a prior bounty payout for this protocol/auditor.

| Artifact | Where |
|---|---|
| 🎭 `threat_models/post_bounty_variant_drift.yaml` | apply.py (manual flag — `--tags past_paid_bounty`) |
| 🤖 `longtail/bounty_regression.py` | run |
| 📜 `threat_intel.md` "Post-bounty variant drift" | read |
| 📜 Worked example: Thorchain α-shuffle 2022 → c-split 2026 | reading |

---

### Adversarial actor classes (orthogonal to protocol_class)

Apply **in addition** to protocol_class routing. Multiple actors may apply simultaneously.

| Actor | When | Prompt |
|---|---|---|
| Bonded validator/oracle/relayer | Any protocol with a bonded role | `prompts/bonded_actor_threat.md` |
| Oracle that can lie | Pyth/Chainlink/TWAP/custom | `prompts/oracle_lies.md` |
| Relayer that can censor | IBC/LZ/Wormhole/Axelar (upstream) | `prompts/relayer_censors.md` |
| Sequencer that can reorder | Centralized-sequencer L2 | `prompts/sequencer_reorders.md` |
| TSS validator that can extract | GG18/20/FROST/threshold BLS | `prompts/validator_extracts.md` |
| Keeper that skips | Compound v3 / Aave liquidator / Yearn | `prompts/keeper_skips.md` |
| MEV searcher that inserts | DEX/AMM/batch solver | `prompts/mev_searcher_inserts.md` |
| Frontend compromised | DeFi UI on Vercel/CF/S3 | `prompts/frontend_compromised.md` |
| Bridge message forger (lone+collusion) | Bridges + attested-payload | `prompts/bridge_message_forge.md` |

See `prompts/_actors_index.md` for the full catalog.

---

## Routing decision tree (Claude logic in J0)

```
1. Run chain_detect.py → chain.json (chain, framework, source_path)
2. Run all auto-classifiers:
   - bridge_detector.py (other classifiers TBD)
3. Read _tags.txt + chain.json into context
4. Open _target_routing.md (this file)
5. For each protocol_class detected:
     → run all "Auto-applied artifacts" in the matched section
6. For each actor potentially present in target:
     → apply matched adversarial-actor prompts
7. Read all matched threat_model_hypotheses.md output
8. Funnel hypotheses through prompts/hypothesis_triage.md
9. PLAUSIBLE + INTERESTING + NEEDS_DEEP → J1
10. Phase gate: check stop_signals.md — bridge-specific signal fires automatically if applicable
```

---

## Worked example: AllBridge on HackenProof

**Trigger**: the operator says "let's hunt Allbridge" → `/deephunt target=<allbridge-repo>`.

**Pipeline that should happen**:

| Phase | Step | What Claude does | What it discovers |
|---|---|---|---|
| J-1 | chain_detect.py | Detects EVM (multi-chain deploy) + Solana side | `chain.json` written |
| J0 step 1 | Manual top-3 read | Reads Allbridge Router / TokenManager / Validator contracts | Manual mental model |
| J0 step 2 | asymmetry_scanner | Runs unconditionally | May flag asymmetric modifiers (governance/treasury) — **non-bridge bug class** |
| J0 step 2 | comment_miner | Runs unconditionally | May flag oracle/edge case comments (defensive choice mismatch) — **non-bridge** |
| J0 step 2 | spec_miner | Runs unconditionally | Whitepaper claims vs code — may find drift in AMM math (Alchemix-class) |
| J0 step 3 | Specialized — ALL matched | bridge_hunter.py + amm_hunter.py + governance_hunter.py (multi-class!) | Each surfaces its own class hypotheses |
| J0 step 4 | longtail/audit_rebuttal_analyzer | Runs unconditionally | Past audit findings re-evaluated |
| J0 step 5 | AI prompts | read_as_attacker + worst_admin_action + actors_index (relayer_censors + oracle_lies if oracle present) | Multi-actor lens applied |
| J0 step 6a | **bridge_detector.py** | Auto-detect: framework + entry functions + storage → STRONG | `_tags.txt`: `protocol_class:bridge, bridge, attested-payload, allbridge, layerzero?` |
| J0 step 6b | Manual tags | Claude adds: `amm, staking, governance, multi-class` after reading | Augmented tags |
| J0 step 6c | apply.py | Matches: cross_chain_source_destination_binding + attested_amount_trust_gap + (post_bounty_variant_drift if Allbridge has paid bounty history) | TMs emit hypotheses |
| J0 step 6d | source_amount_grep.sh + check_bridges.sh | Bridge-class detectors run | RED FLAG if no conservation assertion |
| J0 phase gate | stop_signals.md | Bridge escalate signal fires if RED FLAG | Move to J1 with severity ceiling Critical |
| J1 | Hypothesis ranking | All hypotheses across classes ranked together | Bridge + AMM + governance ones competing for top-5 |
| J2/J3 | Proof construction | Critical-est first, regardless of class | Could be a governance bug, AMM math bug, OR bridge bug |
| J3 specialized | All applicable specialized rows | Bridge row + AMM row + Governance row | Multi-class deep |

**What should **NOT** happen**:
- ❌ Bridge auto-routing blocks the amm_hunter.py run
- ❌ apply.py matched bridge TMs → Claude ignores asymmetry_scanner output
- ❌ J3 specialized → only the bridge row, vault/AMM/lending rows are skipped
- ❌ Hypothesis triage → only bridge-class hypotheses survive, governance/AMM filtered out

**Memory check**: per the operator's preferences (memory file), all severities matter — Medium $10K flat, Low $1K-5K are important. **If** the AllBridge bridge layer is clean, but governance has a timelock bypass — that is a reportable Medium/High. Do not discard.

**Recommended HackenProof reporting flow** (per memory `hackenproof_format`):
- 7 fields in the right order
- Screenshots not needed
- Applies to **all** severity findings, not only Critical

---

## How to extend this doc

When a new protocol_class or actor is added:

1. Author an auto-classifier (`hypothesis/<class>_detector.py`)
2. Author a threat_model YAML (`threat_models/<class>.yaml`)
3. Add a row to the Auto-classifiers table above
4. Add a new section "Routing decisions per `protocol_class:<class>`"
5. List all artifacts: TM YAML, scripts, checklists, prompts, papers, learning_paths
6. Update `_coverage_map.md` (per-detector view) with the same artifacts
7. Update `threat_models/_PATTERN_REGISTRY.md` if a new conceptual axis emerges

---

## Cross-link

- [`_coverage_map.md`](_coverage_map.md) — per-detector view (orthogonal to this routing view)
- [`threat_models/_INDEX.md`](threat_models/_INDEX.md) — TM catalog + authoring guide
- [`threat_models/_PATTERN_REGISTRY.md`](threat_models/_PATTERN_REGISTRY.md) — conceptual axes (axis-level reasoning)
- [`prompts/_actors_index.md`](prompts/_actors_index.md) — adversarial actor catalog
- [`threat_intel.md`](threat_intel.md) — attack pattern intel (case-studies layer)
- [`sessions/_methodology/gap_review.md`](../../sessions/_methodology/gap_review.md) — quarterly deferred-class review
- [`sessions/_methodology/live_targets_bridges.md`](../../sessions/_methodology/live_targets_bridges.md) — hunt queue
