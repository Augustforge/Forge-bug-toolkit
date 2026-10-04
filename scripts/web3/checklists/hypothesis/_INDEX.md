# Hypothesis Checklists — Index

Each checklist = template for hypothesis-driven hunting. Apply based on signals from scanners.

## Core Templates (Phase 2B)

| Template | When to apply | Cross-ref past exploit |
|----------|---------------|------------------------|
| [asymmetric_control_flow.md](asymmetric_control_flow.md) | `asymmetry_scanner.py` flags security modifier asymmetry | DeXe (2024) |
| [oracle_guard_bypass.md](oracle_guard_bypass.md) | 2+ functions reach same state, one without oracle/slippage check | Alchemix WstETH/SFraxETH |
| [state_invariant_violation.md](state_invariant_violation.md) | Invariant identified, want to break it | Various (Curve r/o reentrancy) |
| [audit_trail_mining.md](audit_trail_mining.md) | `audit_trail_miner.py` flags commit-vs-diff drift | Alchemix runbook-only fix |
| [non_obvious_lows.md](non_obvious_lows.md) | Project well-audited, looking for missed Low/Medium | All projects |

## Extended Templates (Phase 6)

| Template | Purpose |
|----------|---------|
| `fresh_code_path.md` | Recent commits, least-tested |
| `cross_chain_drift.md` | Multi-chain deploy mismatch |
| `comment_mining.md` | Self-documented invariants |
| `class_of_bug_expansion.md` | Same pattern in 10 other places |
| `composability_chain.md` | Low + Low + Low = High |
| `numerical_edge.md` | Off-by-one, rounding, overflow |
| `permit2_witness.md` | Witness binding, nonce mismatch |
| `readonly_reentrancy.md` | Getter stale state |
| `flash_loan_path.md` | FL-amplified attacks |
| `code_config_extremes.md` | Admin sets params at boundaries |
| `reentrancy_taxonomy.md` | 8 sub-types |
| `defi_primitives_quirks.md` | Cross-ref to DEFI_PRIMITIVES.md |
| `time_dependent_bugs.md` | Interest, decay, lockup |
| `multi_step_chains.md` | rekt.news patterns |
| `liquidity_locker_privilege.md` | liquidity locker / vesting / escrow holding time-locked custody (DxSale 2026) |
| `fund_liveness_reachability.md` | phased-lifecycle funds whose EXIT transition can never fire / be withheld — permanent freeze (HONG 2026) |

## Cross-cutting (not a pattern-template — a reading discipline)

| File | Purpose |
|------|---------|
| `mental_tool_reading_protocol.md` | Feynman/Socratic/Inversion + binding `[Tool:]` anti-skim markers; applied during T1 reading of every score-3+ file, not signal-triggered. Prompts: `../../prompts/reading_lens_*.md` |
| `invariant_synthesis.md` | Derive invariants (G/I/X/E formalism, 7 scans, On-chain=No = bug candidate); synthesis layer ABOVE `comment_miner.py`/`state_machine_analyzer.py`. Applied at J1. Canonical source for invariant-formalism quality gate. |

## How to Use

1. After scanner output, look at flags
2. Open corresponding checklist
3. Walk through pattern questions
4. For each pattern question → mark CONFIRMED / FALSE / NEEDS DEEPER
5. CONFIRMED → escalate to PoC writing

Workflow integration: J0 (Hypothesis Generation) of `/deephunt`.
