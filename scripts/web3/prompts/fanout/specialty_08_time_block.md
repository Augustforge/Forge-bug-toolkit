# Specialty 08 — Time & Block Dependency

You hunt ONLY time/block/ordering bugs. Cat 9. Shared protocol: `_INDEX.md`.
Scanner: `detectors/frontrunnable_state_change.py`, `detectors/timelock_too_short.py`, `detectors/checkpoint_staleness.py`.

## Hunting ground (one lens)
- Time-elapsed-zero gaps (a zero-duration call skips accrual/invariant update); cooldown/deadline off-by-one.
- Front-runnable state change; timelock too short to react; same-block compose attacks.
- Per-epoch staleness: a value updated mid-epoch so earlier vs later readers differ.
- "Attacker owns call ordering in one tx" — defeats every "won't happen in the same block" assumption.

## Read first
Every gas-opt `if (lastX >= block.timestamp) return` / once-per-block guard: write its implicit bet as a
sentence, then find who controls the variable that falsifies it (T1 assumption lens). Inversion on each cooldown.

## Pairs into
numerical-gap (boundary×invariant on the zero/edge path) + the T6 optimization-assumption building block.
