# Solana Bug Bounty Toolkit — Phase K

Hypothesis-driven hunting toolkit for Solana programs. Parallel to `scripts/web3/` (EVM toolkit, Phase J).

## Quick Start

```bash
# Detect chain
python3 scripts/chain_detect.py --target sol:<PROGRAM_ADDRESS>

# Quick scan
bash scripts/sol/scan.sh --onchain sol:<PROGRAM_ADDRESS> --output sessions/$TARGET

# Deep hunt (via skill — calls all phases S-2..S9)
/deephunt sol:<PROGRAM_ADDRESS>
```

## Folder Structure

```
sol/
├── README.md                     ← this file
├── scan.sh                       ← orchestrator (fetch + detect + scan)
├── fetch_program.py              ← Solscan/SolanaFM/GitHub source fetcher
├── correlate.py                  ← Solana severity ↔ Immunefi mapping
├── threat_intel.md               ← Solana exploit history + patterns
│
├── hypothesis/                   ← S0 — 17 broader-class scanners
│   ├── README.md                 ← class mapping reference
│   ├── signer_check_scanner.py
│   ├── owner_check_scanner.py
│   ├── account_trust_audit.py    ← Loopscale + Mango + Cashio class
│   ├── state_route_analyzer.py   ← Marginfi class
│   ├── time_horizon_audit.py     ← Drift class
│   ├── inverse_op_symmetry.py    ← Sec3/Kamino class
│   └── ... (see hypothesis/README.md)
│
├── specialized/                  ← S3 — 13 specialized hunters
│   ├── amm_hunter_sol.py         ← Raydium/Orca/Phoenix
│   ├── lending_hunter_sol.py     ← Solend/MarginFi/Kamino
│   ├── token_extensions_hunter.py← Token-2022
│   ├── governance_hunter_sol.py  ← Squads + durable nonce
│   ├── depin_hunter_sol.py       ← Helium/Render/IO.net
│   ├── cnft_hunter.py            ← Bubblegum/cNFT
│   ├── zk_compression_hunter.py  ← Light Protocol
│   └── svm_derivative_hunter.py  ← Eclipse/Sonic/MagicBlock
│
├── longtail/                     ← Long-undiscovered
├── detectors/                    ← Rust-based wrappers (cargo-audit, Sol-azy, Trident)
├── bytecode/                     ← sBPF disassembly (Phase S5)
├── program_test_corpus/          ← solana-program-test templates
├── checklists/                   ← Hypothesis + specialized class checklists
├── prompts/                      ← AI prompts adapted to Solana
├── realtime/                     ← Mempool + slot leader monitoring
├── opsec/                        ← Solana wallet management
├── post_find/                    ← Solana-specific submission playbook
│
├── HIGH_VALUE_PATTERNS_SOL.md    ← 35 Critical patterns
├── DEFI_PRIMITIVES_SOL.md        ← AMM/lending/restaking math
└── SOLANA_QUIRKS.md              ← Sealevel/CU/rent/borrow specifics
```

## Methodology

> ⚠️ **Patterns as Hypothesis Seeds, NOT Copy Templates** (global principle).

Every known Solana exploit (Mango, Wormhole, Cashio, Loopscale, Marginfi, Drift) is an **instance** of a broader hypothesis class, not a template to copy. Scripts look for NEW instances of the class in other programs.

See `hypothesis/README.md` for script ↔ class mapping.

## Tools Required (Dockerfile)

- Solana CLI 2.0+
- Anchor CLI 0.31+
- cargo-audit, cargo-geiger, cargo-deny, cargo-careful, cargo-mutants
- Sol-azy (FuzzingLabs) — sBPF disassembly + CFG
- Trident (Ackee) — Rust fuzzer
- Sec3 X-Ray (free tier) — supplementary scanner
- llvm-objdump (--triple=bpf)
- Ezbpf — simple sBPF dasm

## Validation Targets (Phase S9)

8 historical exploits — ≥5/8 PASS = production-ready:
1. Mango Markets ($114M, oct 2022)
2. Wormhole ($325M, feb 2022)
3. Cashio ($52M, mar 2022)
4. Crema ($8.7M, jul 2022)
5. Raydium CLMM ($505K bounty, 2024)
6. Loopscale ($5.8M, apr 2025)
7. Marginfi flash loan ($160M prevented, sep 2025)
8. Drift governance ($285M, apr 2026)

## Script Categories: Auto-Scan vs Standalone

`sol/scan.sh` glob-runs `hypothesis/*.py` and `specialized/*.py` with `--target $SOURCE_PATH --output X --quiet`. Scripts fall into 2 categories:

### Category A: Auto-scan compatible (run by the `scan.sh` autoflow)

They accept the `--target <source_path> --output <dir>` interface. Run automatically in `/hunt` and `/deephunt` Phase S1-S3:

**Hypothesis** (broader-class):
- `signer_check_scanner.py`, `owner_check_scanner.py`, `account_trust_audit.py`
- `state_route_analyzer.py`, `pda_seed_analyzer.py`, `cpi_authority_checker.py`
- `cpi_program_id_validator.py`, `account_reinit_detector.py`, `close_reinit_detector.py`
- `discriminator_collision.py`, `custom_discriminator_audit.py`, `arithmetic_overflow.py`
- `sysvar_trust_scanner.py`, `type_confusion_scanner.py`, `compute_dos_analyzer.py`
- `callback_state_mutation.py`, `permissionless_setup_race.py`, `inverse_op_symmetry.py`
- `time_horizon_audit.py`, `crypto_completeness.py`
- `native_solana_scanner.py` — trust-gap patterns in **native (non-Anchor)** programs (`next_account_info` without owner/signer/discriminator checks; Wormhole/Cashio class) + CPI-4/5: `assign()` owner-hijack + unbounded lamport drain (asymmetric.re). Auto-runs via glob.
- `ed25519_offset_validator.py` — Ed25519 sig-instruction read at hardcoded offset vs declared `public_key_offset` (asymmetric.re Relay double-spend, taxonomy 15.10). Auto-runs via glob.
- `cpi_stale_reload.py` — field read after a CPI without `.reload()` → stale deserialized struct (asymmetric.re CPI-2, taxonomy 15.11). Auto-runs via glob.

**Detectors** (auto-run via `detectors/*.py` glob):
- `detectors/sec3_xray_wrapper.py` — wraps Sec3 X-Ray (50+ Solana vuln types, free tier). If x-ray binary not installed → prints install hint, skips gracefully (no crash).

**Specialized** (protocol-class):
- `amm_hunter_sol.py`, `lending_hunter_sol.py`, `restaking_hunter_sol.py`
- `bridge_hunter_sol.py`, `memecoin_launcher_hunter.py`, `orderbook_dex_hunter.py`
- `multisig_hunter.py`, `token_extensions_hunter.py`, `governance_hunter_sol.py`
- `depin_hunter_sol.py`, `cnft_hunter.py`, `zk_compression_hunter.py`, `svm_derivative_hunter.py`

### Category B: Standalone tools (require specific args, not run by the autoflow)

Run manually in /deephunt Phase J4 (economic), J5 (PoC), S-1 (recon), S9 (report):

| Script | Required args | When to use |
|---|---|---|
| `hypothesis/anchor_idl_diff.py` | `--program-id`, `--source-idl` | S-1 recon: detect IDL takeover before scanning |
| `hypothesis/anchor_idl_fuzzer.py` | `--idl`, `--program-id` | S2 invariant break: random crash discovery |
| `hypothesis/cu_profiler.py` | `--rust-source` OR `--signature` | S4 economic: CU cost feasibility |
| `specialized/squads_v4_simulator.py` | `--multisig-pda` OR `--config-file` | S3 governance hunt: Drift-class detection |
| `specialized/mev_simulator_sol.py` | `--scenario` | S4 economic: MEV-accessibility component |
| `opsec/solana_wallet_manager.py` | subcommands (create/list/rotate/note) | S0/pre-hunt: isolated wallet per target |
| `post_find/sec3_audit_comp_strategist.py` | `--finding-json` | S9 post-find: submission route decision |
| `longtail/state_setup_miner_sol.py` | `--target`, `--output` | S2/longtail: flag rare state configs that trigger bugs (threshold=0, max supply, zero/100% fee, empty signers, 0/18 decimals) |
| `bytecode/selector_enum_sol.py` | `--elf`, `--guess-instructions` | S5 bytecode: extract instruction discriminators from sBPF (closed-source / no-IDL programs) |
| `realtime/slot_leader_monitor.py` | `--rpc`, `--epoch` | S4 economic / MEV: sandwich risk per slot leader (leader schedule + known-malicious flag) |
| `realtime/mempool_watcher_sol.py` | `--api-key`, `--watch` | realtime monitoring: watch shred/pre-Jito stream for exploit-shaped txs (stub — needs Helius key) |

In `scan.sh` they gracefully skip via `|| true` (argparse exit 2 does not block the pipeline). Use them manually when needed.

## Phase K 9.9 Upgrade (Latest)

**Fork PoC Automation** — `scripts/sol/fork/`:
- `spawn_validator.sh` — orchestrate solana-test-validator + cloned mainnet state
- `fork_runner.py` — submit attacker tx + diff state before/after + verdict
- `exploit_harness.py` — build attacker tx from finding templates (5 templates)
- `replay_corpus.sh` — regression suite for all historical exploits
- `corpus/pre_fix_manifest.json` — 8 historical exploit references with pre-fix SHAs
- `re_discovery_runner.py` — automated pre-fix re-discovery validation

**Pre-fix Re-discovery Status**: 2/8 PASS:
- `cashio_2022` — owner_check_scanner found `collateral` as [known_class] critical
- `raydium_clmm_2024` — remaining_accounts_validator found `[0]` @ increase_liquidity.rs:292 in pre-fix 83b5a47, **0 in post-fix e6dd1d5** (symmetric proof)

**Solana-Specific Deep Capabilities** (4 new tools):
- `hypothesis/remaining_accounts_validator.py` — every `remaining_accounts[N]` without require_keys_eq (Raydium CLMM class — proven by re-discovery)
- `specialized/pyth_lazer_deep.py` — slot staleness, authority pin, confidence interval, slot monotonic (Drift v2 surface)
- `specialized/sealevel_race_detector.py` — parallel execution race on crank/bot patterns
- `specialized/cu_exhaustion_composer.py` — DoS via user-input loops + CPI stacking
- `specialized/token2022_hook_composability.py` — transfer fee unaware, hook reentrancy surface

## New in This Iteration (Phase K Enhancements)

Additions to baseline Phase K (16-item enhancement batch):

| Category | Files |
|---|---|
| **OPSEC** | `opsec/solana_wallet_manager.py`, `opsec/anchor_deployment_safety.md` |
| **Post-find** | `post_find/sec3_audit_comp_strategist.py`, `post_find/immunefi_solana_submitter.md` |
| **Fuzzing** | `program_test_corpus/TridentFuzzHarness.rs.template`, `hypothesis/anchor_idl_fuzzer.py` |
| **IDL safety** | `hypothesis/anchor_idl_diff.py` — detect on-chain IDL takeover |
| **Governance** | `specialized/squads_v4_simulator.py` — Drift-class analysis |
| **MEV economics** | `specialized/mev_simulator_sol.py` — cross-slot sandwich + bundle exclusion |
| **CU economics** | `hypothesis/cu_profiler.py` — static + RPC profiling |

Cross-chain coordination:
- `scripts/_meta/exploit_feed_aggregator.py` — pulls rekt.news + Sec3 + SlowMist + Immunefi blog
- `sessions/_methodology/cross_chain_hypothesis_amplifier.md` — EVM ↔ Solana class mapping
- `sessions/_methodology/sol_failure_modes.md` — known process gaps (8 documented)

EVM hypothesis scripts now classify findings as `[known_class]` vs `[novel_instance]` (5 scripts updated):
- `web3/hypothesis/asymmetry_scanner.py`
- `web3/hypothesis/comment_miner.py`
- `web3/hypothesis/audit_trail_miner.py`
- `web3/hypothesis/variant_scanner.py`
- `web3/hypothesis/invariant_generator.py`
- `web3/hypothesis/economic_analysis.py`

Economic analysis supports `--chain solana` with a CU cost model (microlamports/CU + Jito tip + SOL price).

## See Also

- `../web3/HYPOTHESIS_GUIDE.md` — overall methodology (cross-chain)
- `../web3/HIGH_VALUE_PATTERNS.md` — EVM counterpart
- `../chain_detect.py` — unified router
- `~/.claude/plans/sprightly-swinging-sky.md` — full Phase K plan
