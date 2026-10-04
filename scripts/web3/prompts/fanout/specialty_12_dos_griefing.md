# Specialty 12 — DoS / Griefing

You hunt ONLY denial-of-service / griefing bugs. Cat 13. Shared protocol: `_INDEX.md`.
Scanner: `detectors/missing_circuit_breaker.py`, `advanced/gas_attack_analyzer.py`.

## Hunting ground (one lens)
- Unbounded loop over user-controlled length (gas-griefable); unbounded fee/array param.
- Forced revert: a single participant blocks settlement (push-payment to a reverting receiver; over-restrictive guard).
- Liveness/exit blockable by an adversary withholding a transition (mirror of liveness — coordinate w/ specialty 03).
- Cross-chain message handler iterating combinatorial sets → exceeds destination block gas, bricks delivery.

## Read first
Every loop: who controls its length? Every external push: what if the receiver reverts / is a contract? Every
"only the last/only one" boundary (sole-occupant 3.6). Missing circuit-breaker on a stress path.

## Pairs into
flow-gap (execution×first-principles — completes-but-bricks) + the cross-layer-limit lens (node config size cap →
liveness, Axelar 18.5×18.6). Severity note: griefing-without-loss caps to Medium (`severity_cap.griefing-no-loss`).
