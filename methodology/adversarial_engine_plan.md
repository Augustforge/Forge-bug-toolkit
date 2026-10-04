# Adversarial Objective Engine (AOE) — track plan

> Status: **ACCEPTED + IMPLEMENTED** (2026-08-05, v2.1). Design locked; implementation complete (5 tasks
> via SDD, final whole-plan review clean, all tests green — see `plans/.sdd/aoe-progress.md` +
> `plans/2026-08-05-aoe-implementation.md`). The name **AOE** is locked. A separate track, parallel to FDE.
> Source metaphor: "to catch a criminal, a detective thinks like a criminal — and we are a Sherlock system."
> We think like a black-hat, **we stay white-hat**.
>
> **Review history (traceability):** v0 (4 axes + 4 reinforcements) → **2× adversarial** → v1 (cut: objective blindness
> to non-economic Crit; one-sided enforcement = inflation; ~70% duplicates) → reinforcement round v2 → **2× final
> adversarial** → **v2.1** (fixes: the reinforcement round subtly repeated v0's sins). The final review found and fixed:
> (H1) contagion was bringing back theoretical-TVL inflation; (H2) `profit-via-sim` tied magnitude to the attacker's
> profit — a relapse of the v0 blindness; (H3) fork-sim was falsely declared "can't be fooled" — it overstates MEV/liquidity profit;
> (H4) §2.3 incentive = **a duplicate of Cat 22** (not "22.1 narrowly": Cat 22 is a whole game-theory category, 6 subclasses);
> (H5) a guardrail hole — live measurement of cascade/governance slipped past §0. All are tagged `[FIX-Hn]` below.

---

## 0. Diagnosis — the REAL delta (honest accounting after v2.1)

**What ALREADY exists (reuse, do NOT duplicate):** `attack_ev_estimate.py` (EV cost×impact), `magnitude_eval`
(claimed→real severity, references aevo/enzyme/penguinbridge/sherlock-euler — measured as **reachable, NOT TVL**), the T4
**evidence-artifact** mandate + **Ehsan counterfactual** ("delta IS loss magnitude, real not assumed" — measuring
from the fork output is already required), walk-backward + samczsun 8c, T9 Cold-Restart, **Category 22 "Incentive
Equilibrium Failure"** (a game-theory class, 6 subclasses 22.1-22.6 — MEV/22.2, liquidation-cascade/22.3,
death-spiral·bank-run/22.5, reward-wash·Sybil/22.6, updater-EV/22.4), `KILL_AUDIT_REASON`+`SOFT_EXHAUSTION`
(de-minimis→cold-T9), `active_ledger_wide_but_shallow` (depth-gate). The system knows: freeze/DoS = binary severity
by rubric, NOT a $-profit.

**The REAL delta — TWO new ENTITIES + method lenses over the existing machinery `[FIX-H4/scope]`:**
1. 🔴 **A consolidated attacker-capability profile** (+ manufacturable-precondition), against which the
   practicality refute passes **symmetrically**. The resources are scattered today; there is no single measurable artifact.
2. 🔴 **An explicit motive model** (extraction / external-payoff / griefing / insider-authority) — today the
   de-minimis judgment silently assumes extraction.

**Method lenses (NOT new entities — enforced wrappers over the existing machinery):** incentive-scan = **applying Cat 22
under the money-lead depth + fork-sim actor-payoff** (§2.3); fork-sim profit-oracle = a reinforcement of T4-evidence (§3.1);
contagion = a severity component under reachable discipline (§3). This is NOT a parallel engine — "two entities + N
lenses", consistent with §8 "don't re-balloon".

**The failure mode this track fixes:** *premature practicality refute* (a distinct class of miss) →
`blind_spots.md` + `failure_modes.md`.

---

## 1. Principle — the objective is harm to the protocol, not profit; measure where you can

**NOT `max(extractable − cost)`.** Instead: **`severity = f(protocol_loss)`, harm via ONE of the motives** — (a)
extraction (gain>0), (b) external-payoff (gain OUTSIDE the protocol: short/competitor/insider/griefer), (c) griefing
(gain≈0/negative, harm is the goal itself). **`attacker_profit ≤ 0` is NEVER a kill / never a loop-exit** — non-economic Critical
(freeze/halt/governance/censorship/data-leak) are fully valid.

**attacker-profit is NARROW, three roles:** (1) a realism check on the practicality refute (§2.1), (2) a tie-break in
the divergence ranking, (3) a down-guard against OUR OWN inflation (Templar). It is **never** a source of
magnitude (magnitude = protocol_loss, the victim side `[FIX-H2]`), never overrides the program rubric, never cuts
the non-economic.

**🔴 measure-don't-estimate (an organizing principle, an echo of "measure don't feel" one level down).** False refute AND
inflation grow from the same root — we *estimate severity/profit/practicality in prose*. Where you can MEASURE —
not by eye, in both directions: protocol_loss → fork output (T4-evidence/§3.1); practicality → profile+manufacture
(§2.1); severity → `magnitude_eval`. **Honest caveat `[FIX-H3]`:** measurement has LIMITS — an isolated
fork does NOT simulate competition (MEV/backrun/front-run) or liquidity aging; for competition/liquidity-
dependent value the fork number = a **ceiling, not a measurement**. Where physical measurement is impossible (latent/off-chain/binary,
competition-value) — mark it as an estimate/ceiling, don't pass it off as fact.

**🔴 THINK black-hat / ACT white-hat** — the central guardrail (§5). §0-NEVER is not weakened.

---

## 2. Core — two new entities (+ an incentive lens over Cat 22)

### 2.1 Attacker-Capability Profile (artifact + refute-realism)
The `attacker_profile.md` artifact: a per-chain baseline (flash-liquidity Aave/Balancer/Morpho, MEV/bundle,
multi-block, Sybil cost, mempool visibility) **+ program payout clauses** (flashloan/capital constraints on payouts
— sherlock-euler: a $100M exploit cut by the rules down to Low). **The source is public/static data**
(on-chain reads via a burner, DefiLlama, docs), **NOT active probing** (§5).

**Mechanism (fix for the recurring miss):** a practicality kill (`[DE-MINIMIS]`/`practicality`) must carry a
**structural field `profile-cleared: <ref>`** — the gate is on the STATE of the tag (modeled on `ledger_t4_claimed_but_unlogged`),
**NOT on lexicon** (broken 5× times). The implementation is an **extension of the existing**: the T4 Gate-3 amplifier list
(+flash-loan/MEV/multi-block/Sybil) and de-minimis→cold-T9 (`KILL_AUDIT_REASON`), not a parallel gate.

**Manufacturable-precondition (#2):** a refute of "requires a special state" (pool imbalance, nonce, empty reserve)
must check: does the attacker CREATE it cheaply via the profile (manufacture-scope × capability)? "Needs an imbalance"
→ a flashloan for $X, and NOT a refute. `profile-cleared` covers preconditions too, not just capital.

**🔴 SYMMETRY:** a confirm with severity based on "profitable with exotic capital" passes the same realism check —
it is netted against **payout clauses**, not raw $. The gate is bidirectional. **Corpus-first:** a hard block ONLY after ≥2
labeled false refutes (§6); before the corpus — a reminder/sentinel.

### 2.2 Motive-model (fixes the objective, §1)
The field `motive: extraction | external-payoff | griefing | insider-authority`. A de-minimis judgment must state the
motive; `extraction_profit ≤ 0` under griefing/external/insider ≠ "not a bug". Cheap (a field + prose in Cat 22),
it closes the core blindness.

### 2.3 Incentive lens over Cat 22 (NOT a new class — strengthened) `[FIX-H4]`
Cat 22 "Incentive Equilibrium Failure" ALREADY exists (game-theory, 6 subclasses) — §2.3 is not a new class, but **two
enforced wrappers over it**: (1) a **money-lead depth lens**, (2) a **fork-sim actor-payoff**. The gist of the class: where
a rational PARTICIPANT (LP/keeper/validator/voter), not a hacker, maximizes payoff while harming the protocol. We are
code-first → we miss it.

**🔴 Depth discipline (a condition — otherwise breadth, and rightly so) `[FIX-H/depth]`:** the Cat 22 class-header prescribes
"apply to EVERY incentivized action" = a built-in **breadth** lens. AOE OVERRIDES it: incentive-scan only on the
already-selected **money-lead thread**, and **depth is inherited by EVERY positive cell** of the actor-payoff (not a "node"): a cell
with `payoff_role>0 ∧ impact<0` must go down ≥5 OR present a proven equilibrium shift — otherwise it is not a
building block. (Implementation: patch the Cat 22 class-header to "money-lead-scoped, not an every-action sweep" — §9.)

**Delta wrappers (they stitch to #1/#3):**
- **(a) Actor-payoff matrix** on the money-lead edge (roles×actions); per-cell depth (above). Artifact `actor_payoff.md`.
- **(b) Rational-actor simulation** (= measure-don't-estimate): not "profitable" in prose, but a sim on the FORK (§3.1, §5.7)
  — **conditionally `[FIX-H/overhead]`:** only for path/liquidity/sequence-dependent payoff (bank-run/JIT/sandwich);
  for arithmetic (22.1 penalty<profit) a sim is redundant — the inequality suffices.
- **(c) Equilibrium-breaking** (2nd order, → §3): "what if ALL rational actors do this" (bank-run,
  LP-exit-cascade). **PoC ONLY on the fork** (§5.7); triggering a cascade live is forbidden.
- **(d) Cross-role collusion:** counted ONLY if `attacker_profile.md` shows that a SINGLE actor can take all the roles
  cheaply (Sybil+capital); otherwise "attacker + accomplice" = out of scope.
- **(e) Scope calibration:** protocol-harm vs user-harm (sandwiching a neighbor is often OOS) — don't inflate (rubric §3).

**Landing:** wrappers over Cat 22 + `actor_payoff.md` on the thread + a T9 axis. The delta to the taxonomy = ONLY
a depth-scoping header + collusion-to-profile (if not in 22.6). NOT a new class, NOT a breadth generator.

---

## 3. Reuse of the existing (mapping — the duplicate fix)

| v0 called it | What it really is | How it lands in AOE |
|---|---|---|
| Axis 1 value-map | walk-backward + samczsun 8c | A **section** `system_model.md` (T10, BEFORE code), the **reachable≠TVL** column; the $-rank at SELECT via an impact ceiling. NOT a new artifact |
| Axis 4 economic | `attack_ev_estimate.py` + `magnitude_eval` + Cat 22.1 | Extend the EV script with a capability-budget. **The program rubric WINS.** `profit_calc` = a CHECKLIST (flash-fee/gas/slippage-in/exit-liquidity/MEV-backrun/opp-cost), measured via fork-sim §3.1 — a missing component = a building block (anti-Goodhart) |
| §3.1 pre-mortem | T9 + samczsun 8c | A T9 axis, read-only + §0 in the prompt (§5.2) |
| §3.2 incident-replay | memory-trigger #3 + T6 | consult-when-matched (triggered by a code hook, NOT a corpus walk) |
| §3.3 temporal | Cat 22.4 + Cat 9 | the field "triggerable-now vs must-wait" (`verify-current-exploitability`) |
| §3.4 griefing | Cat 22.1/7.6/13.1 + hong | the persist-after-stop predicate (§5.3), DISABLED until locked |

**3.1 Fork-simulation profit-oracle (#1 — a reinforcement of T4-evidence, NOT "measuring for the first time") `[FIX-H3/T4-overlap]`.**
T4 ALREADY requires "severity numbers quoted from actual output, not assumed" + the Ehsan counterfactual. The AOE delta is
narrow: **the attacker-balance delta (before/after) as a mandatory input to the down-guard** — not a source of magnitude
(magnitude = protocol_loss, §1). **🔴 Limits (not a hidden inflator):** an isolated fork = counterfactual-alone,
NOT reality: (1) competition-dependent value (MEV/backrun/sandwich) — the fork number = **ceiling-not-measured**
(in reality it's a priority-fee auction, you lose the race); (2) liquidity-dependent — pin to the current block + flag "live may
differ", especially under stress §2.3(c); (3) the fork does NOT simulate that you get front-run/griefed. Landing — a concrete
web3 fork-PoC entrypoint (`scripts/web3/`; `onchain_poc_harness.py` lives in `dapphunt/wallet_test/` and does not compute the profit
delta — either generalize it, or raise the computation into web3 `[FIX-harness]`, §9).

**Severity components (fields/checklist, not techniques):** amplification (`effective = per_shot × iterations`),
exit-liquidity realizability (10M illiquid ≠ $10M), victim-aggregation/blast-radius, **contagion/second-order
(#3) `[FIX-H1]`:** a cascade into DEPENDENT protocols — severity by the **reachable-and-measured** cascade in B (NOT "total
funds-at-risk": that's theoretical-TVL, banned by the manifest), requires a **scope gate "is B in-scope / does the program pay
for external-protocol impact?"** (modeled on §2.3e) + a realism falsifier (§5.6); not measurable / out of scope →
`[LOW-DEFERRED]`, not a severity multiplier. insider-over-authority (undocumented power of a trusted role, IN scope),
pre-positioning/marination-cost.

---

## 4. Enforcement (symmetric · structural · corpus-first · depth-preserving)

- **`profile-cleared: <ref>`** — a structural field on a practicality kill (not lexicon).
- **Symmetry** refute ↔ confirm (§2.1) — netted against payout clauses.
- **magnitude = protocol_loss `[FIX-H2]`:** the source of magnitude is the measured protocol_loss (victim side);
  the fork-sim attacker-profit delta = an INPUT to the down-guard/realism (§1 role 3), **NOT** a source of magnitude.
  **Applicability `[FIX-H2/carve]`:** the rule bites ONLY on-chain extraction with `magnitude_eval.applies=true`;
  latent → differential-patched-build ([[feedback_latent_finding_patched_build_poc]]); binary/off-chain
  (freeze/DoS/web2) → manifest-skip.
- **incentive-depth `[FIX-depth]`:** depth is inherited by EVERY positive cell of the actor-payoff (not a node) — down ≥5 or
  a proven equilibrium shift. money-lead value = a tie-break WITHIN divergence-first (Mandate 0.9), NOT the primary
  driver of SELECT (don't substitute a $-ranking for D-NN/attention-gap).
- **money-lead-first depth** (the breadth fix): the first DRIVE = max-reachable-$ down ≥5; a second node is forbidden until
  depth-5 (analogous to `active_ledger_wide_but_shallow`; the gate itself — §9, not yet built).
- **corpus-first:** a hard gate only after ≥2 labeled cases (§6). The rule: **first the replay test, then the gate**
  ([[feedback_hook_must_prove_firing]]).

---

## 5. Guardrails (white-hat integrity)

1. **THINK ≠ ACT** — the center. §0-NEVER is not weakened.
2. **The pre-mortem/attacker-lens agent is a guardrail in the PROMPT, not only in the methodology.** A cold agent "steal the maximum"
   for live DeFi would produce "5000 Sybils / spam the mempool / flood the relayer" = §0-NEVER. The agent MUST have: (a) read-only
   tools, (b) §0-NEVER verbatim in the system prompt, (c) "model ONLY from public/static data, NO
   contact with live systems", (d) output = `modeled-not-executed`.
3. **Griefing DISABLED until the predicate is locked** (zero severity credit). **The predicate (decision B4):** "does the freeze
   survive the attacker STOPPING? persists → logical/OURS; requires continuous spend → flood/§0-not-ours" +
   a mandatory **external victim** ([[feedback_ton_self_destructive_severity]]).
4. **Profile realism from public data.** Active-only realism → `UNRESOLVED-needs-approval`; the gate does NOT force
   action ([[feedback_noprogram_active_testing]]).
5. **Disclosure-strip (extended `[FIX-playbook]`):** in the report to the team — the minimal on-chain bug + the PoC fact;
   modeled offensive links (Sybil/flood/social-eng) do NOT go **AND `actor_payoff.md` / the full multi-actor
   equilibrium recipe does NOT go** (a ready-made playbook = an infohazard).
6. **Kill-chain realism falsifier:** a modeled link that raises severity carries a falsifier (a historical
   precedent / a public datapoint); if none → severity at the executed-only floor.
7. **🔴 Live-magnitude interdiction (`[FIX-H5]` — the critical hole from the final review).** The magnitude of ANY
   incentive/MEV/cascade/governance finding is measured on the **FORK ONLY**. Any mutation of live state for measurement
   — **a probe-swap, triggering a cascade, a live vote, a real-mempool bid — is EXPLOITATION, forbidden regardless of
   size** (it is not "verification"). Reason: §0-NEVER does not list **market-manipulation/live-state-mutation**
   verbatim, and "we don't withdraw money" doesn't catch it — a flash-vote on a live proposal is irreversible. **Add
   market-manipulation + live-state-mutation to the §0 list inside AOE prompts.**

---

## 6. Metric (corpus-first, anti-Goodhart)

- **NOT "share of Crit ↑"** (perverse: inflation pushes it up, compounds with loop-exit).
- **YES:** severity-floor accuracy (`magnitude_eval` claimed→real) + PAID/ACCEPTED High-Crit after the fact.
- **"false-refute ↓" requires a labeled corpus — a PRECONDITION of the track.** Superform-reversal/Templar/Berachain →
  confirmed premature practicality refutes → `false_refute_eval:` in `regression_manifest.yaml`. Without
  a corpus — a reminder, not a hard gate (§2.1).

---

## 7. Decisions on open questions (closed)

- **Q1** the name AOE. **Q2** the core (2.1+2.2) + the lens (2.3) immediately; hard gates after the corpus. **Q3** in parallel with FDE.
- **Q4** the griefing/DoS boundary = the **persist-after-stop** predicate (§5.3) + an external victim.
- **Q5** pre-mortem — both forms (a read-only scout start in the Scout Fan-Out + a T9 axis), under guardrail §5.2.

---

## 8. What we do NOT do

NOT a new top-level compass (value = a tie-break WITHIN divergence). NOT a lexical refute gate (a structural field).
NOT a 3rd map artifact (a section of system_model). NOT profit-as-loop-exit/kill, NOT profit-as-source-of-magnitude
(magnitude = protocol_loss). NOT a hard gate before the corpus. NOT a new class under Cat 22 (wrappers). NOT
role-by-role breadth (a lens on the money-lead thread, per-cell depth). NOT theoretical-TVL contagion (reachable+scope). NOT
live measurement of magnitude (fork-only, §5.7). NOT passing a fork number off as measured where there is competition/aging.

---

## 9. Implementation order (once approved → sliced into SDD plans)

1. **Corpus (precondition):** labeled false-refute cases + a per-chain capability baseline table.
2. **Motive-field + objective-fix** (§1, §2.2) — a field + prose in Cat 22 (cheap).
3. **`attacker_profile.md` + T4 Gate-3 amplifier extension** — reminder mode.
4. **`profile-cleared` + the symmetric gate** — AFTER the corpus, a replay test.
5. **money-lead-first depth-gate** (does NOT exist today) + severity-checklist components — a replay test; separate it
   from divergence-first (value=tie-break).
6. **fork-sim profit-oracle** (§3.1): name the web3 fork-PoC entrypoint, raise the profit-delta into `scripts/web3/`
   (or generalize `onchain_poc_harness.py`); ceiling/stale flags; a sim test.
7. **Incentive lens** (§2.3): patch the Cat 22 class-header to "money-lead-scoped" + `actor_payoff.md` + per-cell depth +
   a conditional rational-actor sim.
8. **Contagion** (§3): reachable-measured + a scope gate + a dependency falsifier.
Every step: a replay test before the gate; re-score against the manifest (recall does not drop).

## 10. One-line summary

**AOE v2.1 = a narrow enforced delta under measure-don't-estimate, NOT a parallel engine: two new entities
(an attacker-capability profile with a symmetric refute-realism + a motive model) + method lenses over the existing machinery
(incentive over Cat 22 under per-cell depth; fork-sim as a down-guard input with ceiling caveats; contagion under
reachable+scope). magnitude = protocol_loss, live measurement forbidden (fork-only), everything landed in the existing
machine under guardrails and corpus-first. The goal — fewer false refutes AND more honest severity WITHOUT inflation.**
