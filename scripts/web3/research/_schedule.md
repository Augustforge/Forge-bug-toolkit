# Research Schedule

Time-box: **4h/week** on one primitive from the top-3 priority in `_INDEX.md`.

## Rules

- One primitive at a time. No jumping between topics — context-switching costs more than it seems.
- 4h block = 2h spec reading + 2h hands-on (clone repo, read code, run examples).
- Block over? Update status in `_INDEX.md`. NOT "a little more". Otherwise the weekly cadence breaks.
- If a primitive becomes production-mainstream (multiple deploys, $100M+ TVL) — promote to threat_intel.md + author a threat_model.

## Current rotation (top-3 priority)

1. **ZK VMs** (very-high) — start here. Soundness errors = $100M+ class bugs.
2. **Restaking AVS** (very-high) — EigenLayer is already massive, the AVS class is fresh.
3. **MPC threshold (beyond GG18/20)** (high) — leverages post-Thorchain knowledge.

## Per-week plan

| Week | Primitive | Focus |
|---|---|---|
| W1 | ZK VMs | Risc0 architecture — read whitepaper + arch doc, then clone risc0 repo, walk through `circuit.rs` |
| W2 | ZK VMs | SP1 — different design choice. Compare to Risc0. Identify shared bug classes. |
| W3 | ZK VMs | zkEVM (Scroll, Linea) — circuit constraints, look for underconstraint patterns |
| W4 | Restaking AVS | EigenLayer AVS module — operator opt-in, slashing logic, withdrawal queues |
| W5 | Restaking AVS | Symbiotic — alternative model. Slasher contracts. |
| W6 | MPC threshold | FROST — Schnorr-based. Different math but same insider class. |
| W7 | MPC threshold | GG24, threshold BLS, DKG variants |
| W8 | Review + threat_model authoring — for studied primitives → write YAML |

## Output per primitive (when status → can-hunt)

Minimum:
1. Per-primitive doc enriched with specific attack vectors + code locations to check
2. 1+ threat_model YAML in `scripts/web3/threat_models/` for the class
3. 1+ checklist in `scripts/web3/checklists/specialized/` if the class is large
4. Entry in `threat_intel.md` when the first actual exploit happens (or PoC found)

## Anti-pattern

**Don't** start primitive #2 without moving primitive #1's status to at least `familiar`. Half-done knowledge is worse than no knowledge — it generates wrong hypotheses.

**Don't** read 10 papers in a week. Read 1 spec deeply + clone 1 implementation. Depth > breadth in a 4h block.
