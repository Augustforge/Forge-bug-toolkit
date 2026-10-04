# Specialty 03 — State Machine & Liveness

You hunt ONLY state-transition / freeze bugs. Cat 2 (StateMachine) + 13.6 (liveness). Shared protocol: `_INDEX.md`.
Scanner: `advanced/state_machine_analyzer.py` (+ checklist `checklists/hypothesis/fund_liveness_reachability.md`).

## Hunting ground (one lens)
- One-shot latches `require(state==X); …; state=Y` reachable in wrong order / re-enterable.
- Exit transition orphaned: a `withdraw/refund/claim` gated by a flag whose ONLY writer is an activity that can
  cease (HONG class) → permanent freeze (no theft needed — still Crit/High).
- Migration/partial-state branches that strand users (2.5).
- Library-under-wrong-storage-context: an honest lib writing the wrong slots under delegatecall (2.7).

## Read first
Enumerate every exit + its gate var → find ALL writers of each gate (analyzer maps gate→writers+visibility).
Uncalled-finalizer test: does exit need `finalize()` nobody is incentivized to call?

## Pairs into
flow-gap lens (execution×first-principles — end-state contradicts purpose). Cross-contract state via X-N invariants.
