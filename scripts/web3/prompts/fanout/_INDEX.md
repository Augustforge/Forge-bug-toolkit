# Parallel Specialty Fan-Out — orchestration index

12 single-specialty reading lenses, run as **parallel subagents** at /deephunt phase J0.5 (after J0
generative hypotheses, before J1). Adapted from pashov solidity-auditor's 12-agent architecture
([[reference_pashov_skills]] block A) — but each lens is a **thin orchestration wrapper over OUR existing
taxonomy + scanners**, NOT a re-statement of bug knowledge and NOT 12 new detectors. The taxonomy
(`methodology/hypothesis_taxonomy.md`) is the WHAT; these files are the WHO-reads-what dispatch.

## Why fan-out (vs one pass)
A single sequential read covers a fraction of the surface (asymmetric.re coverage finding; our T1 gap-map).
Twelve narrow lenses each reading the WHOLE scope for ONE class catches what a broad pass skims. Agents
1-9 are single-specialty; the seam BETWEEN them is hunted separately by the **gap-hunter lenses**
(taxonomy "Gap-Hunter Lenses" — numerical/trust/flow), which is our T6 cross-thread synthesis.

## Demarcation (avoid duplication — critical)
- A specialty **does NOT restate** taxonomy classes — it names its Cat(s) + runs the mapped scanner + reads
  with the mental-tool protocol. The detail lives in the taxonomy entry.
- This is **generation fan-out** (produce candidate hypotheses), distinct from **J3 specialized hunters**
  (`specialized/*_hunter.py` — protocol-class deep-dive on a CONFIRMED direction). J0.5 feeds J1/J3; it
  doesn't replace them.
- Distinct from `prompts/_actors_index.md` (actor lens: "who attacks?") — specialty lens is "which bug class?".

## Shared protocol (every specialty applies — do not repeat per file)
1. **Mental-tool reading** (block B): `[Feynman:]` on every function opened, `[Socratic:]` on unclear lines,
   `[Inversion:]` on clean-looking guards. Markers in your stream (`checklists/hypothesis/mental_tool_reading_protocol.md`).
2. **Run your mapped scanner first** (below), then read the flagged sites adversarially — scanner output is a
   lead, not a finding.
3. **Output contract:** append each candidate to `sessions/$TARGET/deep/hypothesis_candidates.md` as a
   `H-{NN}` block in T2 STATE A format (hypothesis one-liner · target file:line · attacker prereq · success
   signal · kill signal · marker-trail). No PoC yet — that's J2+. A candidate with no marker-trail = skim, redo.
4. **Discipline:** if your finding needs a SECOND lens to state, it's not yours — hand it to the gap-hunter
   lenses (it's a composite, T6). One-lens findings only.

## The 12 specialties → taxonomy Cat → mapped scanner(s)
| # | Specialty | Cat | Primary scanner(s) |
|---|---|---|---|
| 01 | math-precision | 1 | `detectors/erc4626_inflation.py`, `advanced/complexity_risk_scorer.py` |
| 02 | accounting-asymmetry | 3 | `hypothesis/asymmetry_scanner.py`, `detectors/asymmetric_modifier.py` |
| 03 | state-machine / liveness | 2, 13.6 | `advanced/state_machine_analyzer.py` (+ `checklists/hypothesis/fund_liveness_reachability.md`) |
| 04 | oracle / external-integration | 5 | `detectors/oracle_single_source.py`, `hypothesis/bridge_detector.py` |
| 05 | access-control / trust | 4 | `detectors/unprotected_role_granting.py`, `detectors/cpimp_proxy_init.py` |
| 06 | reentrancy / composability | 6 | `detectors/readonly_reentrancy.py`, `detectors/transient_storage_reentrancy.py`, `detectors/composable_external_calls.py` |
| 07 | vault / share / accounting-flow | 3, 8 | `hypothesis/economic_analysis.py`, `detectors/checkpoint_staleness.py` |
| 08 | time / block dependency | 9 | `detectors/frontrunnable_state_change.py`, `detectors/timelock_too_short.py`, `detectors/checkpoint_staleness.py` |
| 09 | signature / crypto | 14 | `detectors/missing_signature_nonce.py`, `detectors/signature_scope_coverage.py`, `detectors/eip1271_lying.py` |
| 10 | token-quirk | 11 | `prompts/weird_token_what_if.md` (+ Cat 11 / `severity_cap.weird-tokens`) |
| 11 | hook / module architecture | 12 | `detectors/hook_callback_unauthorized.py`, `detectors/erc3525_reentrancy.py` |
| 12 | DoS / griefing | 13 | `detectors/missing_circuit_breaker.py`, `advanced/gas_attack_analyzer.py` |

Each `specialty_NN_*.md` is the per-lens brief: its hunting ground + scanner + the gap-lens it pairs into.
After all 12 + the 3 gap-lenses, dedup `hypothesis_candidates.md` by `(file, function, Cat)` → promote to J1.
