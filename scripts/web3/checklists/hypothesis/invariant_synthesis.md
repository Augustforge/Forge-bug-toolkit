# Invariant Synthesis — taxonomy + G/I/X/E formalism

Systematic method to **derive** the invariants a target must uphold, then turn each into a falsifiable
hypothesis. Adapted from pashov x-ray Step 2g ([[reference_pashov_skills]] block E). This is the **synthesis
layer ABOVE** our existing extractors — it does NOT replace them, it consumes their output:
- `comment_miner.py` → NatSpec/comment-stated invariants (the "claimed" set). Run it FIRST (J1 already does).
- `state_machine_analyzer.py` → enum/one-shot transitions + freeze reachability (feeds the StateMachine row).
- `fund_liveness_reachability.md` → the liveness/exit sub-case of StateMachine invariants.
Do NOT re-extract what those produce; synthesize on top.

This file is also the **canonical source for submission_checklist `quality_required.invariant-formalism`** —
when you write a finding, state the broken invariant in this notation with its derivation.

## The formalism (4 buckets + On-chain verdict)
Every synthesized property gets an ID and an **On-chain = Yes/No** verdict. **On-chain = No is the
high-signal output: the property SHOULD hold but the code doesn't enforce it everywhere → simultaneously an
invariant AND a candidate bug.** That row is a ready-made T2 STATE A hypothesis.

- **G-N — Enforced Guard** (§1): a per-call precondition (`require`/`assert`/`if-revert` referencing storage),
  quoted verbatim + location. NOT falsifiable on its own (code guarantees it at that callsite) — it's raw
  material for lifting. Skip pure parameter-only checks with no storage tie-back.
- **I-N — Single-contract invariant** (§2): a global property within one contract (Conservation / Bound /
  Ratio / StateMachine / Temporal). Lifted from a guard or stated in NatSpec.
- **X-N — Cross-contract invariant** (§3): a property spanning an external call (caller assumption vs
  callee's independent write sites).
- **E-N — Economic invariant** (§4): a higher-order property derived from a combination of I-N / X-N. Must
  cite the source IDs; if any source is On-chain=No, the economic one is too.

## The 7 synthesis scans (walk top-to-bottom per scope)
Inputs: delta-writes (per-function `Δ(var) = ±expr`, same-basic-block only), guard predicates, enum/one-shot
transitions, comment-stated invariants. (First route every NatSpec/doc `@invariant` directly to §2/§3/§4 by
shape, then run the structural scans — they confirm On-chain=Yes or contradict =No.)

1. **Conservation** — find Δ-pairs `Δ(A)=+e ∧ Δ(B)=−e` (or mapping counterpart) in one function → candidate
   `A + B = const` / `scalar == Σ mapping[key]`. Verify across ALL functions writing either var; if one writes
   without the mirror → "partial conservation", split Yes/No. **Negative conservation:** a function that OUGHT
   to track a flow (flashloan pull/push, receive/forward) with ZERO storage Δ = a finding (absence is the clue).
2. **Guard-lift + all-write-site check** — for each guard `require(var </<=/== K)`: if ALL write sites of `var`
   enforce an equivalent guard → I-N Bound, On-chain=**Yes** (derivation: cite guard + confirm all sites). If
   ANY write site lacks it → I-N Bound, On-chain=**No**, cite the unguarded site = the gap. Include setter-level
   bounds; multiple setters writing one var but only some guarding = On-chain=No.
3. **Ratio** — two coupled quantities expected to hold a ratio (share/asset, collateral/debt); check the ratio
   survives every mutating path (rounding direction included → ties to taxonomy 1.2/1.9).
4. **StateMachine** — one-shot `require(state==X); …; state=Y` (`X@Lx → Y@Ly`). Distinguish: one-shot latch (real
   invariant), togglable flag (skip — flips back), cyclic `false→true→false` (cycle invariant). Use
   `state_machine_analyzer.py` output; freeze/unreachable-exit cases → `fund_liveness_reachability.md` (Cat 13.6).
5. **Temporal** — check-then-update vs update-then-check ordering; per-block/per-epoch staleness (a value read
   before its update in the same epoch — ties to taxonomy 1.9 view≠write, Cat 9 Tranchess checkpoint).
6. **Cross-contract** — for each external-call return used in arithmetic/storage-write: record caller's
   assumption, then find callee's write sites. If callee can change it independently → X-N On-chain=No. ONLY when
   BOTH sides are in scope. Include setter-vs-invariant mismatch (admin setter writes a value without rechecking
   a dependent invariant — e.g. `setReserveCapacity` ignoring current liquidity). **Depth-traversal (GregoAI
   depth-ceiling, [[reference_grego_ai]]):** don't stop at the first callee. An X-N invariant can hold at hop 1-2
   yet break at hop 5+ — trace the SAME invariant down the full interaction chain (`A→B→C→hook→settle→re-read`),
   noting at which depth each side last writes the var. Survived-audit criticals live below the ~4-5-layer human
   ceiling; a verdict reached at depth ≤3 = not yet checked. The deepest layer where the property is still
   assumed-but-unenforced = the highest-signal On-chain=No row.
7. **Economic derivation** — do single + cross invariants imply a higher-order property? Each E-N cites its I-N/X-N
   sources; a gap in any source propagates On-chain=No upward.

## Completeness classification (4 state-shape buckets — pashov `fizz`)
Orthogonal to G/I/X/E (that axis is *scope*); this axis is the property's *temporal shape*. After the 7
scans, bucket every synthesized property and use **empty buckets as a coverage gap-map**:
- **VALID_STATE** — predicate that must hold WHILE the system is in a specific mode (paused / shutdown /
  epoch-N). **Completeness rule: zero VALID_STATE properties → you never checked pause/shutdown/emergency
  flags → almost certainly a gap.** Grep mode flags, assert what must (not) be possible in each mode.
- **STATE_TRANSITION** — what must / must-not change across a mode switch (e.g. `pause` freezes balances
  but not interest accrual).
- **VARIABLE_TRANSITION** — monotonicity / bounds of one variable over time (`totalSupply` only ↑ on mint).
- **HIGH_LEVEL** — system-wide across several vars/actors (solvency: Σassets ≥ Σliabilities; fair-share).
An empty bucket is a hypothesis prompt, not a pass — the most-missed is VALID_STATE (mode-conditional safety).

## Verification gate (MANDATORY before recording any inferred invariant)
- Conservation: confirm the Δ-pair exists at the cited lines (same function body).
- Guard-lift: confirm you checked EVERY write site, not just one.
- NatSpec: confirm the tag/comment exists verbatim AND asserts a GLOBAL property (not a per-call note) — else drop.
- A row you couldn't verify = drop it (don't ship a guessed invariant). Same discipline as T2 D-Kill.

## How it plugs into the hunt
- **J1 Invariant Discovery**: after `comment_miner.py`, run these 7 scans → each On-chain=No row = a T2 STATE A
  hypothesis (the gap IS the bug candidate).
- **T6**: On-chain=No invariants are first-class building blocks; pair across contracts (X-N) for composites.
- **Submission**: cite the broken I-N/X-N/E-N + its derivation in the report (invariant-formalism quality gate).
