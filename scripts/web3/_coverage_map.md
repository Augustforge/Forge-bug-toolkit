# Coverage Map — Bug-Bounty-Toolkit

Navigation map: for each bug class — which assets (detectors / hunters / checklists / threat_models / prompts) we have. Updated regularly (after each added detector / checklist).

**Goal**: the operator sees where we have holes and where to invest the next hour. If a class has 0 coverage — it is the next priority.

## Legend

- 🎯 = primary asset (start here)
- 📋 = checklist
- 🤖 = automated detector / hunter script
- 🧠 = AI prompt (Claude-driven)
- 🎭 = threat_model YAML (apply.py)
- 📜 = case study in threat_intel.md

---

## Coverage by bug class

### Reentrancy

- 🤖 `scripts/web3/detectors/readonly_reentrancy.py`
- 🤖 `scripts/web3/detectors/erc3525_reentrancy.py`
- 🤖 `scripts/web3/detectors/hook_callback_unauthorized.py`
- 🤖 `scripts/web3/detectors/transient_storage_reentrancy.py`
- 📋 `scripts/web3/checklists/reentrancy.md`
- 📋 `scripts/web3/checklists/hypothesis/reentrancy_taxonomy.md`
- 📋 `scripts/web3/checklists/hypothesis/readonly_reentrancy.md`

### Oracle manipulation

- 🤖 `scripts/web3/detectors/oracle_single_source.py`
- 🤖 `scripts/sol/hypothesis/oracle_integration_audit.py` (Solana)
- 🤖 `scripts/sol/specialized/pyth_lazer_deep.py` (Solana — validated on Drift v2)
- 📋 `scripts/web3/checklists/oracle.md`
- 📋 `scripts/web3/checklists/hypothesis/oracle_guard_bypass.md`
- 🧠 `scripts/web3/prompts/oracle_lies.md`
- 📜 KelpDAO DVN ($292M, 2025) in `threat_intel.md` §1

### Governance / multisig

- 🤖 `scripts/web3/specialized/governance_hunter.py`
- 🤖 `scripts/web3/detectors/unprotected_role_granting.py`
- 🤖 `scripts/web3/detectors/timelock_too_short.py`
- 🤖 `scripts/sol/specialized/squads_v4_simulator.py` (Solana)
- 📋 `scripts/web3/checklists/governance.md`
- 📋 `scripts/web3/checklists/specialized/governance.md`
- 📜 Drift governance + durable nonce ($285M) in `threat_intel.md` §5
- 📜 Resolv mint authority ($80M) in `threat_intel.md` §6

### Access control / authorization

- 🤖 `scripts/web3/detectors/asymmetric_modifier.py`
- 🤖 `scripts/web3/hypothesis/asymmetry_scanner.py`
- 🤖 `scripts/sol/hypothesis/signer_check_scanner.py` (Solana)
- 🤖 `scripts/sol/hypothesis/owner_check_scanner.py` (Solana)
- 📋 `scripts/web3/checklists/access_control.md`

### Math / accounting

- 🤖 `scripts/web3/detectors/erc4626_inflation.py`
- 🤖 `scripts/sol/hypothesis/arithmetic_overflow.py` (Solana)
- 📋 `scripts/web3/checklists/math.md`
- 📋 `scripts/web3/checklists/hypothesis/numerical_edge.md`
- 🤖 `scripts/web3/detectors/checkpoint_staleness.py` — **standalone Solidity scanner** (Cat 9.6, post-Tranchess 2026). Flags accounting-sync funcs with a per-block skip guard (`if (lastCheckpoint >= block.timestamp) return`) + a downstream `(liveBalance - recordedSupply)` delta sink. **When it applies:** any vault/staking/rebalancing protocol with a `_checkpoint`/`_update`/`_sync` snapshot. Run `py -3 -X utf8 checkpoint_staleness.py <src>`; each flag → manual "can I run the sync first, change the real balance same-block, then read a stale delta?" (Tranchess $95M-risk, $200K, chainsiren).

### Cross-chain / bridge

- 🤖 `scripts/web3/specialized/bridge_hunter.py`
- 🤖 `scripts/web3/detectors/layerzero_verifier_count.py`
- 🤖 `scripts/web3/bridge_tests/check_bridges.sh`
- 🤖 `scripts/sol/specialized/bridge_hunter_sol.py` (Solana)
- 📋 `scripts/web3/checklists/bridge.md`
- 📋 `scripts/web3/checklists/specialized/bridge.md`
- 📋 `scripts/web3/checklists/hypothesis/cross_chain_drift.md`
- 🧠 `scripts/web3/prompts/relayer_censors.md`
- 📜 KelpDAO DVN in `threat_intel.md` §1

### Bridge source-amount conservation  🆕 (post-Verus 2026)

- 🤖 `scripts/web3/bridge_tests/source_amount_grep.sh` — operational detector (Verus/Wormhole/Nomad classes)
- 🎭 `scripts/web3/threat_models/cross_chain_source_destination_binding.yaml`
- 🎭 `scripts/web3/threat_models/attested_amount_trust_gap.yaml` (sibling lens — LRT/oracle/intent-solver)
- 📋 `scripts/web3/checklists/specialized/bridge.md` Sections 1-4 (Source-Amount Conservation, Replay Protection, Notary Independence, Finality Assumption)
- 🧠 `scripts/web3/prompts/bridge_message_forge.md` (lone-forge + N-of-M collusion)
- 📚 `scripts/web3/research/_audit_corpus/notes/verus_2026_source_amount.md`
- 📚 `_known_findings.jsonl` entries: verus-2026-source-amount-forge, wormhole-2022-signature-bypass, nomad-2022-merkle-root-init
- 🎓 `sessions/_methodology/learning_paths/bridges.md`
- 📜 Bridge Source-Amount Conservation Class in `threat_intel.md` §8 + cumulative tally $521M+
- 🎯 Hunt queue: `sessions/_methodology/live_targets_bridges.md`
- 🚨 Mempool early-warning: `scripts/web3/mempool/patterns/bridge_outflow_anomaly.yaml`
- 🗺️ Conceptual axis catalog: `scripts/web3/threat_models/_PATTERN_REGISTRY.md`

### Validator-set quorum integrity  🆕 (post-Gravity 2026)

- 🎭 `scripts/web3/threat_models/validator_set_quorum_integrity.yaml` (auto on `bridge`/`gravity`/`validator-set`/`custody`)
- 🤖 `scripts/web3/specialized/gravity_validator_hunter.py` — Nakamoto coefficient + quorum-logic heuristics
- 🔧 `scripts/web3/hypothesis/bridge_detector.py` — recognizes Gravity (submitBatch/updateValset) + the `custody` tag
- 📋 `scripts/web3/checklists/specialized/gravity_validator.md` (§8 = degradation vector)
- 📜 Gravity Bridge ($5.4M) in `threat_intel.md` R11
- ⚠️ Scope: key-theft ≥2/3 = declared trust model, NOT findable (see `feedback_ton_self_destructive_severity`)
- 🆕 **Degradation sibling (Cat 18.6, post-Axelar 2026):** vectors 1-5 attack quorum *verification*; vector 6 attacks quorum *survival* — punishment/jailing without a systemic-failure or quorum-survival guard → attacker mass-removes honest validators → halt. Pairs with the size-limit trigger `cross_layer_resource_limit.md` (Cat 18.5). Axelar (marcohextor, $50K, $1B halt).

### Liquidity locker / vesting / escrow custody  🆕 (post-DxSale 2026)

- 🎭 `scripts/web3/threat_models/liquidity_locker_privileged_unlock.yaml` (auto on `locker`/`vesting`/`escrow`/`custody`)
- 🤖 `scripts/web3/hypothesis/liquidity_locker_privilege_scanner.py` — mutable lock-params + owner classification + risk score
- 📋 `scripts/web3/checklists/hypothesis/liquidity_locker_privilege.md`
- 🧠 `scripts/dapphunt/hypothesis/HYPOTHESES.md` H13 (+ H11 abandoned-legacy variant)
- 📡 `scripts/monitors/ownership_transfer_monitor.py` — ownership-transfer leading indicator
- 📜 DxSale ($7.3M) in `threat_intel.md` R12 (+ Decurity 2023 proves findable)

### TSS / MPC crypto layer  🆕 (post-Thorchain 2026)

- 📋 `scripts/web3/checklists/specialized/tss_mpc.md`
- 🎭 `scripts/web3/threat_models/tss_validator_extraction.yaml`
- 🧠 `scripts/web3/prompts/validator_extracts.md`
- 🧠 `scripts/web3/prompts/bonded_actor_threat.md`
- 📜 Thorchain 2026 ($10.8M, TSSHOCK) in `threat_intel.md` §7

### ZK circuit soundness / under-constraint  🆕 (post-Orchard 2026)

- 🤖 `scripts/web3/detectors/halo2_underconstraint.py` — **standalone Rust scanner** (NOT a Slither plugin; halo2 = Rust). Flags `assign_advice()` sites lacking a constraining `copy_advice`/`constrain_*`, ranks by risk (ecc/scalar-mul context + point/scalar witness name + no nearby constraint). **When it applies:** FIRST step on any halo2 / PLONK-ish Rust circuit target (analogue of circomspect for Circom). Run `py -3 -X utf8 halo2_underconstraint.py <src>`; every flagged site → manual "can this witness be anything else without violating a constraint?" check.
- 🤖 `scripts/web3/detectors/groth16_setup_check.py` — Slither detector, Groth16 verifier `delta2 == gamma2` trusted-setup misconfig (Solidity verifier contracts).
- 🎓 `sessions/_methodology/learning_paths/zk.md` — ZK path + **worked real example** (Orchard halo2 under-constraint, the `assign_advice`/`copy_advice` class).
- 📜 Zcash Orchard counterfeiting vuln (May 2026, $billions, AI-found, lived 4y through tier-1 audits) — memory `project_zcash_orchard_halo2`; under-constrained variable-base scalar-mul base → forge `[ivk]g_d = pk_d` → double-spend / unbounded undetectable inflation.
- 🧠 Process: seed the primitive's reference book into context (mythos T1 corpus note); targeted per-gadget prompts × multiple reruns (mythos T2); override model self-skepticism (mythos Mandate 0.7).
- ⏰ Trigger: re-run on any audited ZK target after a new frontier model release (`feedback_model_release_reaudit_window`).

### Consensus & Cross-Client Divergence  🆕 (post-asymmetric.re 2026 — taxonomy Cat 18)

**When it applies:** multi-client L1/L2, EVM-on-Cosmos, bridge event-listeners, MEV relays. An entire new class-home that we didn't have.

- 🧰 `scripts/web3/fuzz_harness/differential_harness.rs.template` + `corpus_seeds.md` — **T8 differential/involution fuzzing** harness (LibAFL). When: the target parses a wire format / 2+ clients (SSZ/RLP/borsh/JSON). Cat 18.1/18.2.
- 📋 `scripts/web3/checklists/hypothesis/serialization_divergence.md` — involution/injective + ghost-region (SSZ Prysm-class).
- 🤖 `scripts/web3/detectors/log_topic_confusion.py` — **standalone Go/Rust**: `UnpackLog` without a `Topics[0]` check (Heimdall log-confusion, Cat 18.3). When: bridge/sidechain event-listener.
- 📋 `scripts/web3/checklists/specialized/proposer_equivocation.md` — MEV relay `submitBlindedBlock` without KZG-commitment binding (Helix, Cat 18.4).
- 📋 `scripts/web3/checklists/specialized/cross_layer_resource_limit.md` — **Cat 18.5** (post-Axelar 2026): liveness-critical op serialized over a transport with an undocumented size limit (CometBFT `max_body_bytes=1MB`, RPC cap) → attacker inflates payload → op fails. **When it applies:** CometBFT/Tendermint vote-based bridges/oracles/AVS attesters; off-chain signer pushing inflatable payloads over a capped transport. Composite with 18.6 (validator-quorum §8) = halt. Axelar (marcohextor, $50K).
- 🎓 `sessions/_methodology/learning_paths/differential_fuzzing.md` + 🎯 `sessions/_methodology/live_targets_consensus.md` (hunt queue).
- 📜 asymmetric.re: Ghost-in-the-Block (SSZ halt), Finding Fractures (0x0B JSON), Heimdall log-confusion ($2B), Helix proposer. Axelar 1MB RPC halt (marcohextor, 18.5×18.6).

### EVM-on-Cosmos state-sync  🆕 (post-asymmetric.re — Cat 2.6)

- 🤖 `scripts/web3/detectors/precompile_state_commit.py` — **standalone Go**: `StateDB.Commit()` inside the precompile path (not EndBlock) → A→B→A infinite mint. **When it applies:** EVM-on-Cosmos (Evmos/Berachain/dYdX-class).
- 📜 asymmetric.re Evmos precompile infinite mint.

### Solana CPI / signature (asymmetric.re classes)  🆕

- 🤖 `scripts/sol/hypothesis/ed25519_offset_validator.py` — Ed25519 sig-instruction hardcoded offset vs `public_key_offset` (Relay, Cat 15.10).
- 🤖 `scripts/sol/hypothesis/cpi_stale_reload.py` — field read after CPI without `.reload()` (CPI-2, Cat 15.11).
- 🤖 `scripts/sol/hypothesis/native_solana_scanner.py` — extended: `assign()` owner-hijack + unbounded lamport drain (CPI-4/5, Cat 15.12).
- ⚠️ Already existed: arbitrary-CPI program-id (`cpi_program_id_validator.py`), CPI authority (`cpi_authority_checker.py`), migration-flag bypass (`state_route_analyzer.py` — Marginfi) — do NOT duplicate.

### Post-bounty regression  🆕 (meta-pattern)

- 🤖 `scripts/web3/longtail/bounty_regression.py`
- 🎭 `scripts/web3/threat_models/post_bounty_variant_drift.yaml`
- 📜 Thorchain α-shuffle 2022 → c-split 2026 in `threat_intel.md` "Post-bounty variant drift"

### Adversarial bonded actors  🆕

- 🧠 `scripts/web3/prompts/_actors_index.md` (catalog)
- 🧠 `scripts/web3/prompts/bonded_actor_threat.md` (general)
- 🧠 `scripts/web3/prompts/validator_extracts.md` (TSS specific)
- 🧠 `scripts/web3/prompts/oracle_lies.md`
- 🧠 `scripts/web3/prompts/relayer_censors.md`
- 🧠 `scripts/web3/prompts/sequencer_reorders.md`
- 🧠 `scripts/web3/prompts/keeper_skips.md`
- 🧠 `scripts/web3/prompts/mev_searcher_inserts.md`
- 🧠 `scripts/web3/prompts/frontend_compromised.md`

### Spec-vs-code gaps (Alchemix/Mezo class)  🆕

- 🤖 `scripts/web3/hypothesis/comment_miner.py` (in-code MUST/should)
- 🤖 `scripts/web3/hypothesis/spec_miner.py` (docs/whitepaper MUST/SHALL)
- 🧠 `scripts/web3/prompts/spec_assumption_check.md`

### MEV / sandwich / flashloan

- 🤖 `scripts/web3/foundry_corpus/FlashLoanDrain.t.sol.template`
- 🤖 `scripts/web3/realtime/exploit_race_monitor.py`
- 🤖 `scripts/sol/specialized/mev_simulator_sol.py` (Solana)
- 📋 `scripts/web3/checklists/hypothesis/flash_loan_path.md`
- 🧠 `scripts/web3/prompts/mev_searcher_inserts.md`

### Proxy / upgrade / storage

- 🤖 `scripts/web3/detectors/storage_layout_drift.py`
- 🤖 `scripts/web3/detectors/cpimp_proxy_init.py`
- 🤖 `scripts/web3/bytecode/storage_reader.py`
- 📋 `scripts/web3/checklists/hypothesis/state_invariant_violation.md`

### Restaking / AVS

- 🤖 `scripts/web3/specialized/restaking_hunter.py`
- 🤖 `scripts/sol/specialized/restaking_hunter_sol.py`
- 🤖 `scripts/sol/specialized/slashing_edge_case_analyzer.py`
- 📋 `scripts/web3/checklists/specialized/restaking.md`

### AMM / lending / vault

- 🤖 `scripts/web3/specialized/amm_hunter.py`
- 🤖 `scripts/web3/specialized/lending_hunter.py`
- 🤖 `scripts/web3/specialized/vault_hunter.py`
- 📋 `scripts/web3/checklists/specialized/amm.md`
- 📋 `scripts/web3/checklists/specialized/lending.md`
- 📋 `scripts/web3/checklists/specialized/vault_erc4626.md`

### Account abstraction (ERC-4337) 🆕 (expanded post-Cantina 2025 advisory)

- 🤖 `scripts/web3/specialized/aa_erc4337_hunter.py`
- 🤖 `scripts/web3/detectors/erc4337_issues.py`
- 📋 `scripts/web3/checklists/specialized/aa_erc4337.md` (expanded 2026-05-19: 7 sections with red-flag code patterns)
- 🎯 `scripts/web3/threat_models/erc4337_signature_replay.yaml` (auto-routing for AA targets — apply.py match by `protocol_class: account-abstraction` or tags `erc4337|aa|smart-account|paymaster|bundler`)
- 📚 `_audit_corpus/_known_findings.jsonl` entries: `erc4337-2025-calldata-hash-collision`, `erc4337-2025-erc1271-signature-reuse`, `erc4337-2025-paymaster-unbounded-sponsorship`, `erc4337-2025-bundler-initcode-frontrun`
- 🔗 Submission gate (all targets): [`sessions/_methodology/submission_checklist.yaml`](../../sessions/_methodology/submission_checklist.yaml)

### Frontend / web2 surface for DeFi

- 🧠 `scripts/web3/prompts/frontend_compromised.md`
- 📜 March 2026 5-protocol frontend hijack week in `threat_intel.md` §2

### Web2 (for bug bounty)

- 🤖 `scripts/scan.sh` (orchestrator: nuclei + sqlmap + dalfox + ...)
- 🤖 `scripts/recon.sh` (passive + active recon)
- 🤖 `scripts/cicd_leak_scanner.py`
- 🤖 `scripts/jwt_advanced.py`
- 🤖 `scripts/cache_deception.py`
- 🤖 `scripts/http_smuggling.py`
- 🤖 `scripts/graphql_advanced.py`
- 🤖 `scripts/websocket_test.py`

### TON node (C++)

- 🤖 `scripts/ton/scan.sh` (cppcheck + semgrep + custom rules)
- 📋 `scripts/ton/checklists/cpp_logic.md`

### Chain-specific quirks (per-chain bug classes)

**When it applies:** target deployed on one of these chains → run the matching `*_quirks.py` to seed chain-specific hypotheses BEFORE generic analysis (each prints the chain's quirks + bug classes). Route by `chain_detect.py` / `_target_routing.md`.

- 🤖 `scripts/web3/chain_quirks/monad_quirks.py` — Monad gas-billing-on-limit, 4× cold SLOAD, expensive ec-precompiles (ZK protocols hit hard), optimistic parallel re-execution
- 🤖 `scripts/web3/chain_quirks/op_stack_quirks.py` — OP-Stack (Optimism/Base/Mode/Zora/World/Soneium): sequencer-pause = no liquidation, L1↔L2 message timing, force-exit handling
- 🤖 `scripts/web3/chain_quirks/zk_rollup_quirks.py` — zkSync Era/Polygon zkEVM/Linea/Scroll/Starknet: prover-liveness withdrawal freeze, validium DA, verifier upgrade backdoor, force-exit
- 🤖 `scripts/web3/chain_quirks/hyper_evm_quirks.py` — HyperEVM: L1↔EVM bridge replay (native vs ERC-20), HyperLiquid oracle staleness on EVM side
- 🤖 `scripts/web3/chain_quirks/berachain_quirks.py` — Berachain PoL: gauge-weight manipulation, BGT burn races, PoL reward drift, validator commission gaming

### Advanced static analysis (Solidity early-pass)

**When it applies:** EVM/Solidity target with source. Run during T1 prioritization / J0–J1 to focus the manual hunt. All are grep/AST heuristics — output = ranked candidates for manual review, not findings.

- 🤖 `scripts/web3/prescan_check.sh <chain>:<addr>` — **gating step BEFORE any scan**: "is this target worth scanning?" (exit 0 PASS / 1 SKIP / 2 WARN)
- 🤖 `scripts/web3/realtime/solc_version_audit.py` — pragma vs known solc compiler CVEs (early step on any Solidity target; `--refresh` to update bug list)
- 🤖 `scripts/web3/advanced/complexity_risk_scorer.py` — McCabe complexity + LoC + nesting + external-call density → risk-rank functions (feeds T1 file prioritization)
- 🤖 `scripts/web3/advanced/crypto_audit.py` — cryptographic footguns: ecrecover malleability / 0-return, EIP-1271 lying, encodePacked collision, missing deadline/nonce (when: target uses signatures/crypto)
- 🤖 `scripts/web3/advanced/gas_attack_analyzer.py` — gas-griefing / OOG / block-gas DoS: unbounded storage loops, external call in loop (when: loops over user-growable arrays)
- 🤖 `scripts/web3/advanced/tokenomics_simulator.py` — model fee-on-transfer / rebasing / deflationary / pause-blacklist token behavior → predict accounting drift (when: protocol integrates external/arbitrary tokens)
- 🤖 `scripts/web3/advanced/test_coverage_analyzer.py` — functions NOT exercised by tests = bug-rich zone (when: target ships a test suite)
- 🤖 `scripts/web3/advanced/mutation_test_runner.py` — mutate source + run `forge test`; surviving mutations = weak coverage zone (when: Foundry target with tests)

### Monitors (operational early-warning)

- 🤖 `scripts/monitors/ownership_transfer_monitor.py` 🆕 — OwnershipTransferred/AdminChanged/RoleGranted on custody contracts from `contracts.watchlist.json` (DxSale leading indicator)
- 🤖 `scripts/monitors/{twitter,github,tvl,telegram}_monitor.py` + `aggregator.py` + `daily_digest.py`
- 🤖 `scripts/web3/deploy_listener.py` (new deploys only)

### Self-improvement

- 🤖 `scripts/_knowledge_base.py` (findings DB + threat_models bridge)
- 🤖 `scripts/_crm.py`
- 🤖 `scripts/_methodology/failure_analysis.py` 🆕
- 🤖 `scripts/_meta_analysis.py`
- 🤖 `scripts/_meta/hypothesis_quality_tracker.py` — novel:known ratio across hunts (scans `sessions/*/hypothesis/*.json`); target ≥0.5, <0.3 = "pattern-matching warning". **When:** periodic self-calibration (run across recent sessions)
- 🤖 `scripts/_meta/red_team_simulator.py` — "would we have found this BEFORE the public fix?" — clones pre-fix commit, runs our toolkit, checks if a script flags the bug. **When:** after any public exploit disclosure → calibrate + feed `failure_modes.md`
- 🤖 `scripts/web3/opsec/reputation_builder.py` — track our handle reputation across HackerOne/Immunefi/Sherlock (`~/.bbt/reputation.json`). **When:** platform-selection strategy (where to submit for max rep ROI)
- 🤖 `scripts/web3/_coverage_map.md` ← this file

---

## Gaps — what's NOT covered

(Update once a month. Each entry = priority for the next addition.)

- ⚠️ **Privacy primitives** (Aztec, Tornado, Railgun) — no nullifier collision check; halo2 circuit under-constraint now partly covered (`halo2_underconstraint.py`, Orchard class), but no generic shielded-pool drain detector
- ❌ **Post-quantum cryptography** — Kyber/Dilithium emerging targets, no analysis
- ⚠️ **ZK circuit / VM soundness** (halo2 circuits, zkEVM, zkVMs Risc0/SP1/Jolt) — halo2 `assign_advice` under-constraint covered (`halo2_underconstraint.py` + zk.md worked example, post-Orchard 2026); zkVM/zkEVM soundness still uncovered
- ⚠️ **Consensus & cross-client divergence** (Cat 18) — serialization involution/parser divergence (`fuzz_harness/` T8 + `serialization_divergence.md`), log-topic confusion (`log_topic_confusion.py`), proposer equivocation (`proposer_equivocation.md`), EVM-Cosmos precompile commit (`precompile_state_commit.py`), cross-layer size-limit→liveness (`cross_layer_resource_limit.md`, 18.5) + validator-quorum degradation (`gravity_validator.md` §8, 18.6) NOW covered post-asymmetric.re/Axelar 2026; remaining: no live multi-client devnet harness pre-built
- ⚠️ **Per-block checkpoint staleness** (Cat 9.6) — `checkpoint_staleness.py` covers the Tranchess per-block-skip → stale `(balance-recorded)` delta class (post-Tranchess 2026); heuristic triage, not proof
- ❌ **DA layers** (Celestia, EigenDA, Avail) — data unavailability attacks, no coverage
- ❌ **Intent-based solvers** (UniswapX, CowSwap solver pool) — batch auction manipulation, partial coverage in `checklists/specialized/intent_based.md` only
- ❌ **DAG consensus** (Sui, Aptos) — fork choice errors, no coverage
- ❌ **Real-time mempool** — Phase 2 (H1) plans this; not yet built
- ❌ **Composability prover** (formal-methods lite) — Phase 2 (H2) plans this; not yet built
- ❌ **Findings DB with peer review** — Phase 2 (H3) plans this; not yet built
- ❌ **Cloud security** (Prowler/Pacu/ScoutSuite) — out of scope for bug bounty / per README roadmap

## Inventory stats (snapshot 2026-05-31)

- Hypothesis scripts: 5 (asymmetry_scanner, comment_miner, audit_trail_miner, spec_miner, liquidity_locker_privilege_scanner 🆕)
- Specialized hunters: 8 (bridge, vault, amm, lending, restaking, governance, aa_erc4337, gravity_validator 🆕)
- Detectors: ~26 (Slither custom)
- Checklists (hypothesis): 24 markdown files (incl. liquidity_locker_privilege 🆕)
- Checklists (specialized): 15 markdown files (incl. gravity_validator 🆕)
- AI prompts: 17 (12 original + 5 actor lens + spec/triage/bonded)
- Threat models YAML: 7 (tss_validator_extraction, post_bounty_variant_drift, cross_chain_source_destination_binding, attested_amount_trust_gap, erc4337_signature_replay, validator_set_quorum_integrity 🆕, liquidity_locker_privileged_unlock 🆕)
- Monitors: 5 (twitter, github, tvl, telegram, ownership_transfer 🆕)
- Case studies: 9 (KelpDAO, frontend, stablecoin, drainer, Drift, Resolv, Thorchain, Gravity 🆕, DxSale 🆕)
- Sol-specific files: ~50+ across hypothesis/specialized/bytecode/checklists/fuzzing/fork
- TON: 2 (scan.sh + cpp_logic.md)

## How to update this file

After adding a new detector/hunter/checklist/prompt/threat_model:
1. Add to the appropriate class section above
2. If a new class — create a new section
3. Remove from "Gaps" if it filled a gap
4. Update inventory stats

If this file is stale — `scripts/web3/_coverage_map.md` needs to be updated **BEFORE** we count a feature as done.

---

## Methodology layer (cross-cutting, not class-specific)

These assets apply across all bug classes, not tied to a specific category:

### Active hunting discipline (hooked into hunt.md / deephunt.md phases)

| Asset | Purpose | When it applies (auto by skill) |
|---|---|---|
| `bug-bounty-toolkit/sessions/_methodology/hypothesis_quality.md` | Pre-flight 5Q checklist (concrete prediction, falsifier, severity ceiling, cost, 5-min refute) | Phase 2.5 step 6.5; deephunt J0 (REQUIRED — kills 80% of bad hypotheses before grep) |
| `bug-bounty-toolkit/sessions/_methodology/stop_signals.md` | Decision tree: abort vs escalate vs external review (8 stop + 6 escalate + 5 review signals) | Every phase gate (J0→J1, J1→J2, etc) |
| `bug-bounty-toolkit/sessions/_methodology/calibration_log.md` | Personal per-class accuracy tracking protocol (jsonl append-only) | J9 mandatory update before submit |
| `bug-bounty-toolkit/sessions/_methodology/calibration_log.jsonl` | Append-only accuracy data store | Updated by hunt + deephunt |
| `bug-bounty-toolkit/sessions/_methodology/adversarial_reading.md` | 7-field template for reading writeups/audits "backwards" — extract the author's mental model | J-2 (audit reading) + J-1 (writeup reading) |
| `bug-bounty-toolkit/sessions/_methodology/learning_paths/_INDEX.md` | Sequential primitive paths (spec→ref impl→toy bug→real review→hunt readiness) | Triggered when calibration_log shows a weak class (<30% accuracy AND n>=5) |
| `bug-bounty-toolkit/sessions/_methodology/learning_paths/tss.md` | TSS path (4-6 weeks @ 4h/week) | Triggered on TSS targets if weak class |
| `bug-bounty-toolkit/sessions/_methodology/learning_paths/zk.md` | ZK path (6-10 weeks) | Triggered on ZK targets if weak class |

### Existing methodology (already hooked)

| Asset | Purpose | When used |
|---|---|---|
| `bug-bounty-toolkit/sessions/_methodology/successful_patterns.md` | Confirmed hypothesis patterns with provenance | J9 — append new instance OR increment counter |
| `bug-bounty-toolkit/sessions/_methodology/cross_chain_hypothesis_amplifier.md` | EVM↔Solana class mapping | J8 mandatory for cross-chain generalization |
| `bug-bounty-toolkit/sessions/_methodology/sol_failure_modes.md` | Log of Solana NO_FIND hunts | After a Solana hunt without a find |
| `bug-bounty-toolkit/scripts/_methodology/failure_analysis.py` | Auto-classify rejected reports | After a CRM reject |
| `bug-bounty-toolkit/scripts/_methodology/failure_modes.md` | Auto-growing taxonomy of reject reasons | Updated by failure_analysis.py |
| `sessions/_methodology/validation/VALIDATION_REPORT.md` (<PROJECT_ROOT>) | Historical Phase J validation 2026-05-15 | Reference when validating a new tool |
| `sessions/_methodology/validation/PHASE_K_VALIDATION_REPORT.md` (<PROJECT_ROOT>) | Historical Phase K Solana validation 2026-05-17 | Same for Solana tools |

**Rule**: any time you add a new hypothesis scanner or threat_model, run it
against the validation corpus referenced above. If the tool doesn't re-discover
known bugs → regression, fix before merging.

**Discipline rule** (more important than the tool rule): even with a perfect toolkit, without
pre-flight + calibration + adversarial reading habits — the hunter doesn't exceed 9.5.
The discipline layer = what separates 9.5 from 9.99.
