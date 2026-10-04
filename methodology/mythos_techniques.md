# Mythos Techniques — Shared Hunt Methodology

**Source:** distilled from public descriptions of Anthropic's Claude Mythos (cybersec frontier model, Project Glasswing, restricted access). Techniques work on any model — what matters is the *discipline*, not the model. See [[reference-claude-mythos]] memory for context.

**Status:** Required reading for all three hunt skills (`/hunt`, `/deephunt`, `/dapphunt`). Each skill references this file at relevant phases instead of duplicating content.

---

## Technique 0 — Hunt Mandates (Read BEFORE every hunt)

**Purpose:** Override default model behavior of "explored, nothing found, let's move on". These are absolute directives. They are above any phase logic.

**Operating identity — SHERLOCK MODE (the frame for all mandates below).** You are a digital detective for web3 vulnerabilities (the operator = Watson, hands in the real world). Cling to the smallest anomaly as a clue (off-by-one, unchecked return, sibling asymmetry, `assign` without `copy`, a comment that says "should" while code doesn't enforce; and **absence** as a clue — the missing check / reload / guard = "the dog that didn't bark"). Reason by abduction: clue → most-likely underlying flaw → hypothesis → drive to PoC/Kill. **Audits are NOT evidence of safety** — bugs exist everywhere; you will find them. **Cross-thread synthesis (the core detective move):** two clues that look unrelated and harmless in isolation (different files / subsystems / bug classes), woven together, produce a NEW attack method outside any checklist — that is where the novel Critical lives. This is stronger than ordinary chaining ("A causally enables B"); it connects DISTANT dots nobody linked. See T6 for the protocol. **Two beats:** Sherlock = hunt/generation (aggressive, audits ignored, dig); cold T4 verifier = confirmation (ALWAYS, kills false positives before submission) — the harder Sherlock digs, the more the cold verifier matters. [[sherlock-detective]]

### Mandate 0.1 — Default exit = bug found, NOT timer/effort

- The hunt does NOT end when phases are walked. It ends when a **real finding** is documented OR the operator explicitly stops.
- "I explored everything, found nothing" = NOT an acceptable end state. Pivot to new angle, new file, new hypothesis class.
- "Time budget exceeded" = NOT an acceptable end state. Time is not the constraint.
- Returning to the operator with "found nothing, what next?" = forbidden by [[no-giveup-hunt]] memory. Standing instruction: "Don't report back without a bug-hunt result! I'm waiting for a result! Keep digging until there is one!"
- **"Hardened" is a FORBIDDEN FRAME, not a target property.** Calling a target "hardened / solid / well-audited → probably clean" is a framing error (an easy trap to fall into): the brain silently swaps "I haven't dug deep enough yet" for "there's nothing here". A surface with no finding = "not cracked yet", NOT "clean". Bugs exist everywhere — axiom. The Zcash Orchard Halo2 under-constraint is a public precedent: it survived years of review and multiple tier-1 audits. Never adopt the frame; when you catch yourself thinking "this code is too good", that is the signal to switch angle, not to stop.

### Mandate 0.2 — First-pass abort requires aggressive second pass

If after walking the standard phases you conclude "no findings":

1. **DO NOT report abort yet.** Mandatory second pass with these new angles:
   - Read ALL files in primary surface (not just T1 score-5; include score-3/4 you skipped)
   - Mock-vs-production state divergence check (do tests use elapsed-time=0? default state? fresh deploy state?)
   - Sibling-class enumeration (if any audit fixed a CLASS of bug — list all similar contracts and verify each)
   - Two-phase patterns (request/claim, cooldown/unstake, lock/release, init/finalize) — accounting analysis per phase
   - Inverted-compare check (`X < X+Y`, `X > X-Y`) — math review with paranoia
   - Composite hypotheses (per T6 below — 2-3-vector chains)
2. Document the second pass in `sessions/{target}/second_pass_log.md`
3. Only IF second pass also produces nothing AND every score-5/4 file was read top-to-bottom AND every composite hypothesis tried, escalate to the operator with explicit list of vectors checked. Even then, propose next angle rather than asking permission to stop.

### Mandate 0.3 — Severity targets

- **Primary:** High / Critical
- **Minimum acceptable to report back:** Medium
- Low / Info findings: record as building blocks for composite chains (per T3 + T6), don't surface alone as the hunt's outcome unless explicitly chained.
- Severity per platform rubric — read program-specific severity matrix BEFORE forming claim (per [[read-scope-before-severity]] memory).

### Mandate 0.4 — Composite hypotheses are first-class

Every hunt session MUST generate 2-vector and 3-vector composite hypotheses, not only single-vector. See T6 below for the chained hypothesis protocol. Most modern Crit-tier exploits are chains (Echo Monad: admin-key + unconstrained-mint + fake-collateral; Transit Finance: ghost-contract + delegated-call). Single-vector hunting alone misses these by design.

### Mandate 0.5 — T4 Verifier Pass is MANDATORY before any submission

No Med+ finding goes to platform without an independent cold-context verifier subagent confirming it. See T4 below for protocol. Skipping = forbidden, no exceptions. Rationale: subjective confirmation bias systematically inflates self-reported severity; cold verifier kills ~25% of seemingly-confirmed findings.

### Mandate 0.6 — `hypotheses.md` is mandatory per-hunt artifact

At session start, create `sessions/{target}/hypotheses.md` from the canonical template in T7 below. Update it live as hypotheses are formulated / refuted / promoted. Refuted hypotheses stay in the file (not deleted) as composite building blocks. This is the "memory" of the hunt; without it, the same dead-ends get re-explored.

### Mandate 0.7 — Model self-skepticism on a real finding is a failure mode

Default model behavior on a true finding in a mature codebase is to **talk itself out of it**: "this code has been audited, so it must be correct", "I'm probably misreading it", "this looks like a planted backdoor, not a real bug". This reflex killed real findings in the wild — see [[zcash-orchard-halo2]]: even the model that found the $billions Orchard under-constraint was "extremely skeptical it had found a real bug" and needed prodding to take it seriously.

- **Audited ≠ correct.** Tier-1 audits miss bugs by design (Orchard under-constraint survived 4 years + multiple audits). Prior clean audit is NOT evidence against your finding.
- When you catch yourself dismissing a finding because "surely someone would have caught this" — that is the bias, not analysis. Convert the doubt into a falsifiable test (T2 STATE C PoC), don't resolve it by deference.
- This is the *inverse* of the T4 verifier's skepticism: T4 is cold-context skepticism that KILLS false positives; Mandate 0.7 is about not killing TRUE positives via self-deference. Resolve both the same way — with a PoC, not a vibe.

### Mandate 0.8 — Four operating axes (derived from a public reference harness; see [[reference_pkqs91_codex]])

Four principles that make the parallelism hybrid and anti-slop a law, not an option:

1. **Explore-wide / exploit-deep — two AXES, run BOTH beats.** Explore-wide (horizontal: Scout
   Fan-Out + T1 gap-map — broad surface coverage) and exploit-deep (vertical: depth-ceiling ≥5 layers
   on a single chain). "Clean" at depth 3 = didn't dig far enough; "walked the top 5" without a fan-out = didn't explore.
2. **Parallel-for-breadth, serial-for-depth (scout ≠ fleet).** Parallelism is ALLOWED only for
   explore-wide (a one-shot fan-out of ≤5 read-only sonnet scouts). Exploit-deep = single-pick, serial.
   "scout-fan-out" (one-shot) ≠ "fleet" (continuous fleet, scoped out). Consistent naming.
3. **Taxonomy = 2 layers; growth in L2 does not bloat the walk.** Walk only Layer-1 mechanisms (Cat 1-14,16,17,
   22,26); Layer-2 domain/chain (15,18-21,23-25) = consult-when-matched. A new Cat MUST declare its
   layer; domain/chain increments go to L2, not to the walk axis. A Cat name without a code-grounded prediction = SLOP.
   Knowledge growth ≠ slop growth. (`hypothesis_taxonomy.md` "How to use".)
4. **Measure, don't feel.** A significant methodology/hook change → re-score against `regression_manifest.yaml`
   (`scripts/_methodology/regression_replay.py`): recall must not drop / precision must rise. Otherwise a change
   "feels like progress" but is unproven. Metric → `calibration_log.jsonl` (`type:regression`).

### Mandate 0.9 — DIVERGENCE-FIRST (where to dig is pointed to by an artifact, not by taste)

**The problem this mandate closes.** Depth is something we can do: a hunt can reach the Critical tier and still lose to duplicates and pay $0.
The miss is not in the number of layers but in the **originality of the entry point**. SELECT by "severity ×
confidence" is subjective: what LOOKS risky is exactly what looks risky to the crowd → duplicates by construction.

**The rule.** A single hypothesis source, "reading code", has a ceiling: I see the same thing as anyone
who reads the same code. Un-dup needs a source the crowd lacks — and there are **three such sources, all
objective** (computable from artifacts, not from a feeling):

1. **`D-NN` — divergence between an independent model and the code** (T10 manual / T11 machine). The model is built
   BEFORE reading the implementation; we look not for a "weird line" but for a **place where an invariant is not enforced**.
2. **Attention-gap** (T14) — where the auditor didn't look (inverting the audit map) and where the author didn't look
   (traces of haste in git). Works even where there is no corpus.
3. **Prediction miss** (T12) — `predicted ≠ observed` during the depth drive itself. The loop is closed:
   depth stops being a pure cost and itself generates new entry points.

**Intersection of sources = maximum priority**: a `D-NN` in an audit-map hole in a file with a trace of
haste is the best spot the system knows how to name mechanically. It outranks a lone `D-NN` of any severity.

**Ordering relative to DEPTH-LEAD-FIRST:** breadth finds the thread → **the model and the attention map point to the
PLACE** → depth opens it (≥5 layers, T12).

**Reading the metric (operator position, 2026-07-27):** zero `D-NN` over N hours means "**our detector didn't
fire**", NOT "the target is empty". The metric does not and will not have the right to end a hunt — that would directly
contradict the axiom "bugs exist everywhere". If the generator is silent → escalate the method (which one —
see the table in `depth_engine_plan.md` §10), and the silence is recorded in `blind_spots.md`.

**Tool-output-LAST (anti-anchoring, §40.1, 0xSimao — «analyze them at the end, so they don't bias my
judgement»).** Divergence-first disciplines the order between your model and the CODE (T10 above — the model
is built BEFORE reading the implementation). The same principle applies to the order between your analysis and the OUTPUT
OF TOOLS — scanners (`solodit_pattern_signals.py`, the code-signal → taxonomy lookup from T1 below),
public skills, fuzzers (Echidna/Medusa/`fizz`), `divergence_fanout`/scout fan-out results.
**Your own `D-NN` / hypothesis is built FIRST** (from the code + an independent model, T10); the scanner/skill output
is read **LATER, as a cross-check** — "the scanner found this too → confirmation", "the scanner missed it →
expected, a commodity pattern, not what we are looking for" — and **not as a seed for hypotheses**. Someone else's output, read
first, anchors judgment on "what the crowd/tool finds" — and exactly the un-dup core is lost (Mandate
0.9 as a whole). Applies to all three skills: a scanner/pattern-signal run is valid at any time, but
your OWN D-NN/hypothesis for a file is formulated BEFORE its output is read for that file, not
after. Enforcement: `scripts/hooks/model_first_nudge.py` (the same PreToolUse guard that enforces model-before-
fan-out explicitly names the "model/D-NN → tool-output" order in its REMINDER) — hard detection covers the
subagent channel (Scout Fan-Out, where scanners are usually run); a direct Bash scanner call in the main
thread is not matched by the hook (the matcher does not include Bash) — there the order is held by the prose of this mandate.

Technique specs: **T10** (`independent_model_first.md`) · **T14** (`attention_gap_mapping.md`) ·
**T13** (`system_model_template.md`) · primitives library (`methodology/invariant_library.md`).

### Mandate 0.10 — Objective = protocol_loss, not attacker profit; measure-don't-estimate (AOE §1/§6)

**THINK like a black-hat, ACT like a white-hat.** Model the maximum damage a real attacker would do — then stop at confirmation, per §0-NEVER (Mandate 0.11). The objective that RANKS severity is **damage to the protocol**, not the attacker's take.

- **`severity = f(protocol_loss)`, via ONE of three motives:** (a) **extraction** (attacker gain > 0), (b) **external-payoff** (gain is OUTSIDE the protocol — short / competitor / insider / griefer-for-hire), (c) **griefing** (gain ≈ 0 or negative — the damage IS the goal). A fourth ledger tag, **insider-authority** (undocumented power of a trusted in-scope role), rides the same rule. The `motive:` field is mandatory per-hypothesis (T7 template); prose lives in taxonomy Cat 22.
- **`attacker_profit ≤ 0` NEVER kills / never loop-exits.** Non-economic Criticals (freeze / halt / governance capture / censorship / data-leak) are full-severity by rubric, not by $-profit. attacker-profit has exactly THREE narrow roles: (1) realism-check of a practicality-refute, (2) tie-break inside divergence-ranking (Mandate 0.9), (3) down-guard against your OWN inflation (Templar). It is **never** the source of magnitude (magnitude = protocol_loss, victim-side), never overrides the program rubric, never cuts a non-economic finding.
- **magnitude source + applicability carve (§4).** The source of magnitude is the **measured protocol_loss** (victim-side); a fork attacker-profit delta (§3.1 / `scripts/web3/hypothesis/fork_profit_delta.py`) is an INPUT for the down-guard/realism check, **never** the source. This economic rule **bites ONLY on on-chain-extraction findings** (`magnitude_eval.applies=true`). A **latent** bug → prove magnitude via differential-patched-build ([[feedback_latent_finding_patched_build_poc]]), not fork-profit. A **binary / off-chain** impact (freeze / DoS / web2) → `magnitude_eval` skips; severity comes from the program rubric, not $. (Reflected in `attack_ev_estimate.py` `carve` field.)
- **Measure-don't-estimate (organizing principle, one level below "measure don't feel", Mandate 0.8).** False-refute AND inflation both grow from *guessing severity/profit/practicality in prose*. Where you CAN measure, measure — both directions: protocol_loss → fork output (T4-evidence); practicality → `attacker_capability_baseline.md` + manufacture-scope; severity → `magnitude_eval`. **Honest ceiling caveat:** an isolated fork does NOT simulate competition (MEV / backrun / front-run) or liquidity aging — for competition/liquidity-dependent value the fork number is a **ceiling, not a measured fact**; label it so. Where measurement is physically impossible (latent / off-chain / binary / competition-value), mark it estimate/ceiling — don't pass it off as measured.
- **Track success-metric (anti-Goodhart, §6): NOT "share of Crit ↑"** (perverse — inflation drives it up, compounding with loop-exit). Measure **severity-floor accuracy** (`magnitude_eval` claimed→real) + **PAID / ACCEPTED High-Crit post-facto**. Corpus for "false-refute ↓" = `false_refute_eval:` in `regression_manifest.yaml` (corpus-first: ≥2 labeled cases → hard-gate later; else reminder).

Full track spec: `methodology/adversarial_engine_plan.md`. Failure-mode this closes: *premature practicality-refute* (`blind_spots.md` BS-04 + `failure_modes.md`).

### Mandate 0.11 — THINK ≠ ACT: white-hat guardrails (§0-NEVER extended · live-magnitude interdiction) (AOE §5)

Modeling maximum attacker damage (Mandate 0.10) NEVER licenses touching a live system. These are §0-NEVER-tier, above any phase logic.

- **§0-NEVER extended (verbatim, alongside DDoS/DoS · phishing · RAT/C2 · mass-targeting · destruction):** **market-manipulation** and **live-state-mutation** are added to the NEVER list. Rationale (AOE §5.7): "we don't withdraw funds" does NOT catch them — a flash-vote on a live proposal is irreversible; a probe-swap moves a real market. Mirrored in the project `CLAUDE.md` §0 "Never:".
- **Live-magnitude interdiction (§5.7):** magnitude of ANY incentive / MEV / cascade / governance finding is measured on a **FORK ONLY**. Any live-state mutation to measure it — **a probe-swap, triggering a cascade, a live vote, a real mempool bid — is EXPLOITATION, forbidden regardless of size** (it is NOT "verification"). The fork is the ceiling read (Mandate 0.10 caveat); the live system is never the measuring instrument.
- **Kill-chain realism-falsifier (§5.6):** a *modeled* (not executed) link that RAISES severity must carry a realism-falsifier — a historical precedent or a public datapoint that the link is real. No falsifier → severity reverts to the **executed-only floor** (don't bank severity on an unfalsified model link).
- **Profile realism from public/static data (§5.4):** `attacker_capability_baseline.md` is built from public/static sources (on-chain reads via burner, DefiLlama, docs), NOT active-probing. A realism claim that would need active probing to settle → `UNRESOLVED-needs-approval`; the gate does NOT force the action ([[feedback_noprogram_active_testing]]).

---

### Mandate 0.12 — Audit lessons (2026-08-09)

Hunts can show near-perfect discipline by form (model-first, D-NN, T4, un-dup, ledger-first) and still **yield nothing payable**. The root is not the hunting method — it is **what we hunt** and **how we prove depth**. Five lessons, each now enforced (not just prose):

- **EV-ANGLE on handed targets (B1, `hunt_entry_gate` ev_note):** a handed target can be a max-crowded/hardened giant (multi-year, heavily audited, hundreds of hunters). `target_discovery.py` EV-scoring fired only for self-discovery, silent on operator-handed URLs. Fix — EV-recon reminder at entry. ⚠ NOT a give-up valve ("hardened/bad-EV" exit stays FORBIDDEN — Mandate 0.axiom "bugs are everywhere, including the over-hardened"): EV picks the un-dup **ANGLE** (freshest code / attention-gap / post-audit-drift / un-modeled subsystem — where the crowd didn't go), NOT whether to dig.
- **Executable-floor on non-forks (B2, `active_executable_floor_unrun` soft-nudge):** a hunt with 21 axes and **0 fork-PoC** has every depth-trace static — "scout ENFORCED" = recon-grade sold as depth-grade. The FORK-DIFF mandate required executable proof but armed only from `PARENT-FORK` (forks). The non-fork analog now nudges: ≥5 axes + 0 executable → run ≥1 strongest thread executably before more breadth.
- **Zero-D-NN escalates method (B4, `active_zero_divergence_unescalated`, Mandate 0.9 enforced):** model built, **0 D-NN** for the whole hunt, `blind_spots.md` untouched. Zero D-NN = "detector didn't fire", NOT "target clean" → switch generator (model-vs-live / commodity-subtraction / assumption-mining / negative-space) + log the silent generator. Was prose — now nudged.
- **Axis-count ≠ depth (B3, template `close-grade` field):** "17 depth-axes" where 14 are `scout-verified` and 1 is a real 5/5 = overstated exhaustion. Tag each closed axis `depth-drive | executable | scout-verified`; if well over half are `scout-verified` it is breadth-tilt, dig deeper yourself.
- **T4-checker must be COLD (B5, template `checker:cold-subagent`):** maker=cold-scout, checker=warm-main (max anchoring) inverts the rubric — riskiest OOS/de-minimis calls got the most-anchored reviewer. T4 = fresh cold subagent, not the lead.
- **Human exit ("we're leaving") no longer voids gates silently (B6, `_exit_diff`):** on RELEASE the gate now prints the still-open completeness gaps (Un-Dup Sweep / PRIOR-PATTERNS / EXPOSURE / D-NN) to stderr — not a block (leaving is the operator's prerogative), but the incomplete dig is recorded and does not slip away silently.
- **Paraphrase-give-up as an "honest final report" (8th bypass, `_paraphrase_giveup`, 2026-08-09):** the instance stopped writing "abort / giving up / pivot" (caught) and instead returned a polished *final report* to the operator with the forbidden frames in new words — "the target is really hardened / the un-dup surface is cleaned out / the pass is exhaustive / further EV only in a multi-day fork-PoC / wait for the next release" + handing back the wheel. `BREADTH_RE` needs "the whole scope", these phrases slipped past → not flagged `is_giveup` → the circuit-breaker released the loop after 30 min. Same root as earlier bypasses — can't win the synonym race pointwise, so we catch the CLUSTER (≥2 distinct give-up categories: hardened-frame / exhaustion / bad-EV-pivot / park-till-release / final-report / decision-Q) with a NEGATIVE continuation-override ("the loop continues / next axis / building wave-3" = still working, NOT a give-up). Held as `is_giveup=True` (the circuit-breaker cannot release it). ⚠ "hardened" about the WHOLE target + an exit context is forbidden; "the core/I-NN is hardened as expected, continuing" is a legitimate refutation, not a give-up.

**Meta:** a well-audited/crowded target is worth hunting (bugs live everywhere), but it demands **single-target mastery** (days + re-visits on each release, [[feedback_single_target_mastery]]), NOT a 2-4h breadth-sweep declared "exhaustively hardened".

---

## Hunt-Loop — Operating Spine (orchestrates T1→T9)

**This is the run-mode for EVERY hunt**, not an optional technique. It binds T1-T9 into one
self-iterating loop. Source: loop-engineering (verify-gate + state + single stop-condition). Mirror
of CLAUDE.md §1 «Hunt-Loop» — full spec lives here.

**AXIOM (core):** bugs exist everywhere — that is a fact. Therefore the loop has **EXACTLY ONE exit = a really
confirmed (T4-confirmed) HIGH/CRITICAL bug = the goal.** There is no exit on "tired / clean / hardened / bad EV /
diminishing returns / 30 min with nothing". **Severity — THREE tiers, all actively hunted (operator, 2026-07-28,
role symmetry — not "important vs aside"):** **High/Crit** = loop exit (≥5 layers, T4 immediately);
**Medium** = a FULL DRIVE target (go deeper right away, digging ≥3 layers is normal, NOT parked, takes part in SELECT
by severity×confidence on equal terms, push ceiling→High; $2-5K+ is solid, don't discard); **Low** = cost-gated
harvest (≤1 verification step → bank; digging ≥3 layers → `[LOW-DEFERRED]` building-block, not thrown away).
Confirmed Medium/Low → bank into the ledger section `## Banked Findings`, submission **batched at the end / on
operator request** (NOT immediately; T4 before submission). Medium/Low do NOT end the loop — the exit is only High/Critical
(in sync with the severity-priority "primary = Crit/High"). **Low $1k+ never-auto-de-minimis:** DE-MINIMIS on
Low requires proof that the impact is below the rubric's payable threshold, not a taste judgment. Surface exhaustion → T9 = **continuation**, not an exit. Park does not
exist. The only non-success exit is the operator EXPLICITLY writing "we're leaving" (their prerogative, NOT
encoded in the methodology; the hook catches it via RELEASE words).

**Entry (always-on, trigger = INTENT to hunt, NOT a slash command):** fires when the operator gives a
target / program link with the intent to hunt — including just "study <link>" in a new session
(the operator does NOT type `/deephunt` themselves). Entry steps:
1. auto-route to the right skill (CLAUDE.md §2 + `chain_detect.py`) — I invoke the skill myself (Skill tool);
2. **raise the marker** `bug-bounty-toolkit/sessions/{target}/.hunt_active` (enables the forcing hook
   `hunt_completeness_gate.py` — a structural guard against premature exit);
3. **stake out the ledger:** `cp bug-bounty-toolkit/sessions/_methodology/hypotheses_template.md
   bug-bounty-toolkit/sessions/{target}/hypotheses.md`, fill in the header (the file carries LEDGER RULES —
   every hypothesis is tagged, passed ones are moved, the pool is unlimited). If it already exists (RESUME) — do NOT
   overwrite, read Loop State and continue;
3b. **create the model:** `cp bug-bounty-toolkit/sessions/_methodology/system_model_template.md
   bug-bounty-toolkit/sessions/{target}/system_model.md` (the entry hook does this itself, **regardless of
   RESUME** — a hunt already in progress also gets the file). The sections `Corpus`…`Invariants` are filled **BEFORE
   reading the implementation** (T10). A target where T10 does not apply (small contract / dapphunt front end /
   web2) → `MODEL: N/A — <reason>` in Loop State;
4. enter the LOOP.
Covers all cases: explicit `/hunt|/deephunt|/dapphunt`, bare link + "study", ad-hoc "take a look at this contract".

**Unit = one iteration = one hypothesis (single-pick).** The cycle:

```
LOOP  (EXIT EXACTLY ONE = T4-confirmed HIGH/CRITICAL bug; Medium/Low — banked along the way, NOT an exit):
  1. SELECT — exactly 1 item by priority (🔴 DIVERGENCE-FIRST: the first THREE sources are objective):
       a1) an open `D-NN` — model↔code divergence (T10/T11): `SUBSTITUTED` > `pred:ENFORCED→actual
           ABSENT` > `ABSENT` > `ENFORCED-PARTIAL`; within a tier — by rank (value × paths × tests=0 ×
           convergence ÷ crowd-heat). Queue order: `cold` FIRST, `hot` — mandatory, but later
       a2) otherwise → attention-gap (T14): hole in the audit map / trace of haste in git.
           ⚠ INTERSECTION of sources (D-NN in a map hole in a file with haste) outranks EVERYTHING, including a1
       a3) otherwise → prediction miss `predicted ≠ observed` (T12, a by-product of DRIVE)
       a)  otherwise → the open hypothesis with the highest (severity-ceiling × confidence) that has not reached PoC/Kill
       b) otherwise → the next unread score-5 file (T1 gap-map) → spawns an H-NN
       c) otherwise → the next unread score-4 file → H-NN
       d) otherwise → T6 composite from refuted/contested building-blocks (cross-thread + sibling)
       e) otherwise ("the current axis is exhausted") → pop the head of `Axis-Queue` (a ranked forward queue of axes) = T9
           on a NEW axis → return to SELECT (NOT an exit; queue empty → regeneration by 3 modes, see below)
       ⛔ Source a1 CANNOT be declared worked-off while unvisited `hot` divergences remain.
          "It's crowded there" is not a falsifier and is not a kill (it is a queue, not a filter).
  2. DRIVE — drive the selected hypothesis through T2 (STATE A→B→C→D) + depth-ceiling:
       pull the thread ≥5 layers down (call→state→external→hook→settle), not "clean at layer 3".
       do NOT pivot mid-PoC (a new idea → _inbox.md, I'll return to it). STATE D = PoC / Kill / Park
       (Park = a time-bounded valve against endless DRIVE on one hypothesis → becomes a building-block).
  3. GATE:
       • refuted/killed → a CONCRETE falsifier is MANDATORY (file:line — what exactly kills it).
           No falsifier → this is NOT killed but `contested` → stays a building-block for T6.  → goto 1
       • reached D-PoC → T4 cold verifier (maker≠checker) + differential-confirm:
           – T4 kill / 2-tier-down / silent-precond / tautology → NOT a bug  → goto 1
           – T4 confirm, impact ≥ High → SUCCESS (exit candidate)  → step 4
           – T4 confirm, impact = Medium → bank in `## Banked Findings` + push the severity ceiling (up to High);
               Medium = a full DRIVE (can dig deeper, not parked); does NOT end the loop  → goto 1
           – T4 confirm, impact = Low → cost-gated: ≤1 step → bank in `## Banked Findings`; digging ≥3 layers
               → `[LOW-DEFERRED]` building-block; does NOT end the loop  → goto 1
           (⚠ Medium/Low are NOT submitted immediately — batch at the end / on operator request; T4 before submission.
            Low $1k+: DE-MINIMIS requires proof that the impact is below the rubric's payable threshold, not "it's minor".)
           (🔗 A5 banked × T6, Wave 1 2026-08-08: BEFORE batch-submit with ≥2 banked — a MANDATORY
            T6 pass over the BANK [Draw the Dependency over the bank, output→input]: banked = PROVEN
            building-blocks [more reliable than refuted], Low×Low pairs → precondition, Low+High → escalate to
            Crit, Medium×Medium → Crit. severity-boost + un-dup [the crowd submits one at a time = duplicates].
            Record `Banked T6-pass: DONE — chain:… / no chainable pairs`; the gate
            `active_banked_composite_unchecked` holds submission, reusing the chain-dependency guard.)
  4. SUCCESS (High/Critical) → push the severity ceiling (PoC/chaining one tier higher; T3/T6) → finalize
       → **EXIT (on ONE High/Crit finding, hand over to the operator).** The only exit. (Medium/Low do NOT lead here —
       they were already submitted along the way at the GATE step, and the loop continued.)
  5. After 3 EMPTY T9 axes → **surface status to the operator** (gap-map proof, axes 1/2/3 logged) →
       **CONTINUE on axis 4** (a new, orthogonal one). NOT park, NOT an exit.
```

**⛔ LEDGER-FIRST DISCIPLINE — the ledger = the working surface, chat = NOT a notebook (the default of EVERY session).**
During the hunt I write to `hypotheses.md` via Edit **CONTINUOUSLY, the moment something appears** — not at the end of
an iteration and not in chat. Write triggers (each → Edit immediately): (a) a new hypothesis → `H-NN` in Active
(prediction + `file:line` + falsifier); (b) a finding/confirmation → into the ledger; (c) **a hypothesis
refuted/unproven → straight into Refuted with a falsifier** (no falsifier → `[CONTESTED]` building-block);
(d) **scouts returned → the FIRST action = Edit the ledger** (leads → Scout table + Active `H-NN`), THEN
status; (e) end of iteration → `## Loop State`. **In chat — ONLY a short status (1-3 lines + a link to the
ledger).** A wall of reasoning/leads/refutes in chat = clogs context and loses work (a recurring
miss). **Enforcement (4 layers, not just prose):** entry-reminder ⛔
+ template **Rule 0** + the Stop gate `ledger-live` (blocks exit if findings are in chat AND the ledger is `thin` —
detection of an empty template, mtime-independent) + **PostToolUse `ledger_first_nudge.py`** (on Task return with a
`thin` ledger, a nudge "leads into the file first", debounce 120s). **Honest limit:** hooks fire on
events (start/pre-tool/post-tool/Stop) — they guarantee that findings WILL land in the file before the end of the turn, but
chat brevity IN THE MIDDLE of a turn is held by instruction, not a hard block.

**First-pick trigger — the loop starts on the FIRST Crit-capable hypothesis, NOT on a quota.** There is NO threshold "wait for
≥3 / ≥N hypotheses before starting DRIVE" (there is no such gate in the methodology — if an instance invented one,
it is an error). As soon as ONE hypothesis with a high `ceiling × confidence` has crystallized — SELECT it
and go to DRIVE. Pool generation is **concurrent** with processing, not a prerequisite to it: don't drain
recon/generation to the end for the sake of a count. Recon/fingerprint/scout = entry (fills the pool), but the first
loop iteration starts with the first worthy hypothesis, not with a "complete" pool. Anti-pattern: "the loop
really starts when 3 are collected" → recon is stretched for the sake of a number while a Crit-capable lead waits.
(Refill runs in the background — see below.)

**DEPTH-LEAD-FIRST — breadth finds the thread, DEPTH opens it (2026-07-06, companion to First-pick).** The root
miss: the instance maps the whole scope / spawns
H-NNs and NEVER drives ONE thread down ≥5 layers. Breadth (recon/scout) defers the risky commit
("what if this hypothesis is wrong") and *feels* productive, so it expands and fills all the time — and
DRIVE never happens. This is the CAUSE of false exhaustion (`BREADTH≠DEPTH`): "the whole scope
is covered" = file-level classification, not depth-exhaustion. **The rule:** after ONE recon/scout pass
the next committed action = **DRIVE the strongest thread (max severity×confidence) down ≥5 layers**
(call→state→external→hook→accounting, depth-ceiling). **A second breadth pass (more scouts / more
file classification / more H-NNs) is FORBIDDEN until at least one thread has a depth-trace ≥5.** Maintain the
`Depth-Lead:` field in Loop State (H-NN + layer counter). **Enforcement (not just prose):** the completeness-gate
`active_ledger_wide_but_shallow` catches "wide-but-shallow" (≥4 real H AND no thread ≥5 layers) and
REPLACES the forcing-reason with a depth order (escalating nudge: every turn of "breadth instead of depth" → the
order to go deep again; anti-FP — silent while a scout is PENDING, i.e. the first breadth pass is legitimate). The triad:
First-pick (start on the first worthy one) → depth-lead-first (drive IT deep to 5 layers) → single-pick
(one iteration = one hypothesis). The bug sits at the SEAM of layers, not in a single function at depth 2-3.
**The cycle repeats ON EVERY T9 axis:** a new axis / new wave of theories = a new ONE breadth pass
(scout → `PENDING`, the guard is silent per ordering) → build new hypotheses → **reset `Depth-Lead: none
yet`** → drive the strongest of the NEW ones deep ≥5. The reset is mandatory: otherwise the old `5/5` lingers and the guard counts
depth as "paid for" on the new axis. I.e. depth-lead-first ≠ "go deep once and done" — it is "breadth→depth"
on EVERY axis; each time breadth merely finds the thread and depth opens it.

**Hypothesis generation — UNLIMITED and CONTINUOUS (a corollary of the axiom).** The hypothesis pool has no ceiling
on count, and J0/Phase generation is only the FIRST batch, not the whole supply. "All my hypotheses are
exhausted/refuted" is NOT a reason to exit but a **trigger to generate new ones** (never exit, no park).
Three modes run constantly: **(1) build new** — gap-map score-5/4 files (SELECT b/c) + a cold
subagent on a new axis (e); **(2) build out** — refuted/contested → building-block → T6 recombination
(d) + depth-ceiling pulls one hypothesis down ≥5 layers + `_inbox.md` insights mid-PoC; **(3) rebuild**
— T9 cold restart completely changes the frame on a new axis (anchoring-break, not rephrasing). Generation
stops ONLY on success (confirmed High/Critical) or operator "we're leaving" (Medium/Low do not stop it —
banked along the way). **These 3 modes are the regenerators of the forward queue `Axis-Queue` when it is exhausted.**

**Hunt Strategy Layer — Thesis + Axis-Queue + Axes-Closed (2026-08-08, forward plan for axis changes).** The pain
"I forget where to go next" = there is no FORWARD ranked queue of axes. Three Loop State fields: **Thesis** — a strategic
reading of the target as a falsifiable predicate (≈ a top-level D-NN) with a mandatory undup angle (not "where is the bug",
but "where is the bug the crowd hasn't seen, and why"; grounded in an ARTIFACT — attention-gap / commit-archaeology /
composition-seam, not taste); written AFTER wave-1 of the model AND T14, re-assessed on EVERY axis-close;
soft-nudge (not hard). **Axis-Queue** — a RICH ranked forward queue of FUTURE axes (head = Depth-Lead;
top seeded from matched PRIOR-PATTERNS; rank = severity×confidence×undup; includes Medium axes). The head does NOT
wait for full population (first-pick preserved). Each item as a line `N) <axis> — src:<D-NN|T14-gap|score-4|
T6-pair|prior-pattern|T9-frame> · rank:<…>`. Exhausted → regeneration by 3 modes (above) → NOT an exit.
**Axes-Closed** — a backward proof log of exhausted axes (`src`/`outcome`/`proof`), NOT a duplicate of the machine `T9
restart axes used` (that one is a comma counter for `active_axes_without_waves`; §catch: proof text with commas would
break the counter → a separate field). An axis in Closed WITHOUT proof = soft-give-up (caught by FALSE-EXHAUSTION). `outcome:
finding` (incl. banked Medium/Low) → bank the fingerprint into `undup_pattern_library.md` → PRIOR-PATTERN
of the next target (**compounding loop: input↔output closed, the moat grows with every finding**).
**AXIS ≠ WAVE (operator, 2026-08-08):** an axis (T9-frame) = an attack angle, the unit of Axis-Queue; a wave (`## WAVE-N`,
≤12 I-NN) = a batch of invariants. A BROAD axis carries SEVERAL waves (`## WAVE-2/3…` under the SAME axis) if
12 I-NN is not enough — this is NOT an axis change, `T9 restart axes used` is NOT incremented, `active_axes_without_waves` will not
fire (waves>axes = normal). An axis change (pop) — ONLY on real exhaustion (all I-NN resolved AND 0
live H-NN AND 0 open D-NN). Staying long on one axis (12+ I-NN, dozens of H-NN, lots of DRIVE) is legitimate, no
gate triggers. Enforcement: the hard gate `active_axis_queue_empty` (axis closed + queue empty +
between axes [0 live H-NN, `Depth-Lead: none yet`] → holds the exit; mid-drive [a live H-NN / Depth-Lead is driving
a thread] = SILENT, doesn't disturb a broad axis; anti-gaming — a stub `N) TBD` without `src:` doesn't count; NOT
model-gated — the axis closes even on `MODEL: N/A`). All skills (deephunt/hunt-web2/dapphunt) — one principle.

**Refute-honesty guard (false-negative shield):** we cold-verify confirms (T4 kills
false-positives), so we symmetrically gate refutes too — a lazy "looks fine here" silently deletes a surface
and contradicts the axiom "didn't find = didn't dig deep enough". Killed without a concrete falsifier is not allowed →
`contested` → lives on as a building-block.

**maker ≠ checker (invariant):** the loop's main agent = maker (SELECT+DRIVE); the T4 cold subagent =
checker. "The model that did the work is too kind a grader of its own work."

**Iteration-ledger (state, resumable):** header in `hypotheses.md` (T7) — `iteration #`, `current pick`,
`restart axes used`, `last SELECT-branch`, **`Thesis` / `Axis-Queue` / `Axes-Closed`** (Hunt Strategy
Layer — RESUME reads them FIRST: strategy / where next / what is already closed, instantly, without reconstructing
from fragments). **Per-iteration forcing-trace:** at the end of EVERY iteration a mandatory line (which
SELECT branch + counter) — you cannot silently "fall out" of the loop (anti-Ralph-Wiggum).

**RESUME (session restart / after compaction):** a fresh `.hunt_active` + `hypotheses.md` → I read the
loop-state header and continue from the right SELECT branch, NOT from scratch.

**Per-finding vs target:** the loop exit = on ONE finding. Continuing the same target = a NEW loop
(single-target-mastery: many loops over one target). "Found a bug → dropped the target" is NOT it.

**Relationship to the skills' phases:** the loop = a PROCESSING layer on top of the phases. J0/Phase generation (fan-out,
seeded, threat-model) fills the candidate pool as a BATCH (generation is NOT single-pick); Hunt-Loop governs
how candidates are pulled through ONE at a time (processing is single-pick). No conflict.

### Explore-Wide Scout Fan-Out (parallelism ONLY on explore-wide; spec → `_methodology/scout_fanout.md`)

**Principle: parallel-for-breadth, serial-for-depth.** Explore-wide (filling the pool) is parallelized;
exploit-deep (single-pick DRIVE, depth-ceiling ≥5 layers) is NOT parallelized, it stays serial.
Scout-fan-out = **parallelization of the already-batch generation phase** (above: "generation is NOT single-pick"),
and NOT an exception to single-pick processing. It is NOT a "fleet" (a one-shot fan-out at the start + on each
new T9 axis, not a continuous fleet). A head start: native subagents (Agent tool), one account — the external reference harness
needed 6 accounts + a load balancer for the same thing.

**When:** a multi-subsystem / large surface (≳15 score-4/5 files OR ≥3 subsystems). A single
small contract → the `## Scout Fan-Out` section in the ledger = `N/A — single-contract`, straight to single-pick.

**Flow:** partition the surface by subsystems from T1 (accounting/oracle/access/state-machine/external-calls)
→ ≤5 **read-only** scouts (`subagent_type: general-purpose`, `model: sonnet`) in parallel, each
owning one partition → they return STRICT leads (`file:line` + trigger + Cat-cand + **prediction +
falsifier** + confidence; prose / "just Cat-N" is rejected by the anti-slop gate). The main agent (`opus`)
merges into ONE ledger: anti-slop → dedup → **cross-thread T6 pass over pairs of leads from DIFFERENT partitions**
(distant clues → a new vector, the core of cross-thread) → rank by ceiling×confidence → promote to H-NN.
A scout does NOT write the ledger / does NOT do PoCs — only the main agent writes (a single source of truth).

**Pre-mortem / attacker-lens scout (AOE §5.2 / B5)** — if the fan-out includes a pre-mortem scout ("what maximum would a real attacker extract?"), it carries the same guardrail as the T9 cold subagent: read-only tools, §0-NEVER verbatim (incl. market-manipulation / live-state-mutation, Mandate 0.11), "model ONLY from public/static data", output `modeled-not-executed`. It MODELS the attacker's moves, it does NOT execute them.

**Enforcement (takes effect in a new session):** the entry hook puts a `## Scout Fan-Out` section into every ledger
with status `PENDING`; the completeness-gate blocks exit while it is `PENDING` (neither filled nor N/A) —
like Loop State. After that — ordinary single-pick deep, SELECT/DRIVE/GATE/EXIT unchanged.

---

## Technique 1 — File Prioritization (Attack Surface Rubric)

**Problem this solves:** A repo can have thousands of files. Reading top-down or alphabetically wastes hours on business logic that has no attacker-reachable input. Our own TON C-phase burned 800 LoC reading `elector-code.fc` — mature business logic, low attack surface — and found nothing. The bug was in `bls.cpp` which is 335 LoC but high attack surface (parsing attacker-supplied bytes, no input validation).

**Rubric — score every candidate file 1-5 BEFORE reading:**

| Score | Criteria | Examples |
|---|---|---|
| **5 — Critical surface** | Parses attacker-controlled input. Crypto primitives. Deserialization. Network/IPC boundary. Auth gate. | `bls.cpp`, JSON/protobuf decoders, `verify*()` functions, signature checkers, multi-sig validators, oracle adapters |
| **4 — High surface** | Accepts external calldata. Token transfer logic. Bridge message handlers. Wallet adapters. Permission checks. | `transferFrom`, `executeMeta`, bridge `relay()`, `permit()` impls, EIP-712 verifiers |
| **3 — Medium surface** | Internal but reachable via privileged callers. Math libraries used in pricing. Slippage/fee logic. | Liquidity math, oracle aggregation, fee distribution, vault accounting |
| **2 — Low surface** | Pure business logic, gated by trusted caller checks. Admin functions. Setters. | Owner-only configuration, admin upgrades, parameter setters |
| **1 — No attack surface** | Tests, mocks, deployment scripts, comments, migrations, view functions over public state. | `test/`, `script/`, `mock/`, `IERC20.sol` interface files |

**Protocol:**

0. **Before ANYTHING — capture the PROGRAM SCOPE verbatim into the ledger header (2026-07-06, recon-mandate):**
   **(a) Assets in Scope** — the exact list of in-scope contracts/addresses/domains. **(b) Impacts in Scope** —
   the PROGRAM's per-impact severity rubric (what qualifies as Critical/High/Medium/Low for each
   impact) + explicit out-of-scope / known-issue impacts. Impacts in Scope is critical TWICE: it calibrates
   severity (overstate → rep-friction, understate → under-collection) AND defines WHAT to look for (in-scope impacts =
   targets, out-of-scope = don't burn time). **A systemic miss: instances capture Assets but FORGET Impacts
   — keeping them "in their head / in the report", not in the ledger.** Enforcement: the template header carries the sentinel `{IMPACTS-TODO}`;
   the completeness-gate `active_ledger_missing_impacts` blocks exit until the sentinel is removed (filled in with
   real impacts OR `N/A — no formal impacts list` for repo/no-program). [[feedback_impacts_in_scope]]
   **(c) Off-repo context — context-blindness pull (§40.5, 0xSimao).** Most of the context lives
   OUTSIDE the repo: client/API docs, status pages, the project's Discord/Telegram/Twitter, who actually holds
   the deploy keys / the infra operator. Read/record this in the recon phase (J-2/P-AM/P-SM — the same place where
   the scope is captured) **BEFORE finalizing the model/severity**, not just code + audits. Example: a staleness
   claim on an oracle requires knowing whether the publisher is alive RIGHT NOW (status page/Discord), not only
   that the last on-chain update is old — otherwise a false "permanent freeze" instead of "nobody was reading it".
   Recon without this step = a code-blind analysis of the repo that doesn't know what outside the repo actually keeps the
   system alive. `N/A — no off-repo surface (repo-only artifact, no live deploy/API)` is legitimate for a
   source-only target without deployed live infrastructure.
1. **Before** reading any source, do `glob/find` + classify every file by score.
2. Read top-5 highest-scored files first. Spend ≥60% of hunt time on score-5 files.
2b. **Partition for Scout Fan-Out:** on a multi-subsystem surface, group score-4/5 files by
   subsystem (accounting/oracle/access/state-machine/external-calls) → these are the partitions of the explore-wide
   fan-out (≤5 read-only `sonnet` scouts, see "Explore-Wide Scout Fan-Out" above).
3. Score-1/2 files: skim only if hypothesis specifically points there. Default = skip.
4. **Record the rubric output** in `sessions/{target}/attack_surface_rubric.md` so it's auditable later and shows what was deliberately deprioritized (defends against "you missed file X" criticism in post-mortem).
5. **Re-score after audit-mining (J-2/S-2 in /deephunt):** known audit findings in a file = bump score by 1; clean audit history with no drift = drop by 1 (drift cases are exception, see [[feedback-solana-hunt-reality]] memory).

**Scope-tier recognition (do this BEFORE scoring — decides WHICH surface and WHICH program):** classify the target type first, because it changes what "the code" even is (Immunefi-backtest lesson, 2026-07-05 — 5/7 crits lived below the contract layer):
- **(a) protocol contracts** — a dApp/DeFi repo or deployed addresses → scope = the contracts (the default, and our reflex).
- **(b) chain / appchain / node / alt-EVM engine** — the L1/L2/appchain ITSELF, with its OWN bounty (Aurora/Optimism/Moonbeam-class) → the **engine, precompiles, forked interpreter, runtime pallets, AND the consensus/P2P/mempool/ABCI node code ARE in scope** → map them at **PARITY** with any system contracts (`scripts/web3/checklists/client_node_hunting.md`). Two distinct classes live here, don't collapse to one: **alt-EVM execution divergence** (Cat 18.13 — precompile/opcode/truncation) AND **consensus/liveness DoS** (Cat 18.1-18.12 — ABCI panic, unbounded block-processing loop, loose-schema, quorum-survival, vote-dedup) — the latter *dominates real node payouts* (~25/90 in the Immunefi backtest), so when a chain is in scope run the node checklist's full 4-lens + PAT sweep, not just the alt-EVM patterns. Our contracts-only reflex silently drops this whole surface.
- **(c) bridge** — cross-chain attested-payload/message OR BTC/UTXO SPV → the parser + proof-verifier are the crown jewels (Cat 5/14/18/27).
- **(d) hybrid** — a protocol that ships its own chain/module (both layers in scope).
- **Scope-gate for (b):** if the target is a *protocol deployed on* an alt-EVM but the engine is a *separate program*, the engine is OUT of scope here — note it as a separate target ([[feedback_read_scope_before_severity]]), don't spend the current program's time on it. **NOT "engine over contracts" — engine at PARITY, only when in scope.**
- **EV note:** when the engine IS in scope, it's usually the LEAST-crowded surface (everyone audits the contracts; few read the forked go-ethereum/runtime diff) → an EV edge with less dup-risk — the within-target form of [[feedback_fresh_public_h1_is_crowded]].

**Impact-ceiling triage — prune paths-to-nowhere at SELECT, not after the PoC (WhiteHatMage "I don't bother looking into paths that can't lead to catastrophic effects", [[reference_whitehatmage_guide]]):** time on surface is the scarcest resource — don't burn a fork-PoC + T4 cycle to discover de-minimis at the end (Templar push→Critical then real Pyth conf 0.05% → honest Medium; Enzyme F-CURVE-01 REAL read-only-reentrancy but holdings ≈$760). Move the magnitude read to the front of the loop:

1. **Tag every hypothesis with an impact-ceiling at SELECT-time, before DRIVE:** `Crit-capable` / `Med` / `structurally-Low`. The question is *"if this fired at 100%, how much value moves / which invariant breaks?"* — answered from the value-flow, not after building the container.
2. **SELECT prioritizes by `ceiling × confidence`, not confidence alone.** A high-confidence `structurally-Low` path loses to a medium-confidence `Crit-capable` one. This operationalizes "Critical primary" ([[feedback_severity_priority]]) from a declared priority into an actual ordering rule.
3. **Read order = walk-backward from value-transfer** (where funds exit / get minted → trace back), NOT top-down by filename. Paths that never touch value-flow sink to the bottom of the queue. (Pairs with the state-change-as-hypothesis cost-to-break half below: cost-to-break × impact-ceiling = the full EV gate, `attack_ev_estimate.py`.)
4. **CARVEOUT — prune solo-paths only, never building-blocks.** Drop a `structurally-Low` path *only if it also has no chaining potential*. A bug that's harmless alone but composes into a Crit chain ([[feedback_protocol_family_bug_transfer]], cross-thread synthesis, T6) is sacred seed corn — it stays in `building_blocks.md`, not the trash. This is pruning the SELECT (which path to start), never the DRIVE (how deep to dig a chosen path) — persistence stays intact ([[feedback_no_giveup_hunt]]).

**Target-quadrant + hotspot lens (apply BEFORE scoring — WhiteHatMage guide, [[reference_whitehatmage_guide]]):** the rubric tells you *which files*; the quadrant tells you *what TYPE of bug* lives in this target. "Code quality tells a story."

*Quadrant (code-quality × audit-depth) → bug type to hunt:*

| Code | Audit | Where the bug sits |
|---|---|---|
| Good | Good | Novel exploit paths, **upgrades**, operational issues (← the Orchard quadrant — hardened ≠ clean, [[zcash-orchard-halo2]]) |
| Good | Mid | Complex paths around **known** security pitfalls |
| Mid | Good | **Audit-fix remnants** + weak-design leftovers (re-score those files +1) |
| Mid | Mid | Missed but non-extreme exploit paths |

Read the signals first: sloppy comments / inconsistent naming / multiple Criticals in past audits = mid-code. Pin the quadrant, then aim the hypothesis class accordingly.

*Test-maturity = the "audit-depth" axis read from the repo itself (pashov enumerate signal, [[reference_pashov_skills]] block H).* Don't take "audited" on faith — grep the test surface: presence of **invariant/property tests** (`invariant_`, Foundry `StdInvariant`), **fuzzers** (`echidna`, `medusa`), **formal/symbolic** (`halmos`, `certora`/CVL, `kontrol`), **fork tests** (`createFork`/`--fork-url`) = mature → push the target toward the **Good-audit** column → hunt the Orchard quadrant (novel paths, upgrades, what formal methods structurally CAN'T express — e.g. cross-contract economic invariants, off-chain/temporal assumptions). Conversely only unit tests with mocks, no fuzz/invariant, no fork = thin → Mid-audit column → the obvious-but-untested paths are still live (mock-vs-prod divergence, Cat 2.1). Maturity ≠ coverage: heavy `echidna` on the math lib says nothing about the un-fuzzed bridge handler — score per-area, not per-repo. (Optional detector `advanced/test_maturity_detector.py` — reuses `test_coverage_analyzer.py` file-walk; the signal is test-TYPE presence, not line-coverage %.)

**Regression-as-oracle (§57.2, recon-mining, cheap — inversion of [[feedback_check_project_tests]]).**
Same grep pass, opposite question: not "does a test exist" but "is a test **disabled**". Grep the
target's own test suite for `skip`/`xfail`/`@pytest.mark.skip`/`it.skip`/`.only`-siblings-excluded/
`TODO`/`FIXME`/`known-issue`/`// disabled` markers on a test that once asserted a security-relevant
property. Each hit is a **recognized-but-unclosed problem — a seed hypothesis**, not noise: someone on
the team already knew the invariant could break and either couldn't fix it, or fixed the code but never
re-enabled the test (drift risk). `[[feedback_check_project_tests]]` says "check the project's own
tests hold before you submit" (a passing test suite ≠ intended-behavior excuse); this is its mirror at
recon-time — "check WHICH tests were turned off, and why" — the disabled test names the exact assumption
worth attacking first. Cheap (one grep pass over `test/`/`tests/`/`spec/`), depends on OSS test visibility
(closed-source / no test dir → `N/A`), applies to all three skills wherever a target repo exists.

**Build-your-own stateful fuzz when the target is invariant-heavy but thin on fuzz (pashov `fizz`, [[reference_pashov_fizz]]) — TRIGGER.** If the per-area read above shows an invariant-heavy surface (vault / AMM / lending / staking — Cat 1/3/8) with NO own invariant/property/fuzz tests, that un-fuzzed accounting space is exactly where a multi-step call sequence breaks an invariant a targeted fork-PoC won't surface — fork-PoC proves a KNOWN hypothesis; Medusa/Echidna EXPLORE the call-sequence space we're otherwise blind to. On such a target, generate a stateful harness (`fizz` → `Properties.sol`/Handlers → Medusa) as an **explore-wide layer feeding hypotheses**, THEN fork-PoC + T4 the violations. This is the EVM twin of Trident-on-Solana; **build per-target** (harness is target-specific — don't pre-build). `fizz` is **cloned and ready** at `bug-bounty-toolkit/scripts/web3/fuzz_harness/fizz/` (entrypoint `fizz/SKILL.md`) — on a matching target grab it from there (+ the differential T8 engine alongside) and generate the suite under the target's contracts; dispatcher table in `fuzz_harness/README.md`. via-IR coverage gotcha + Docker-build in [[reference_toolkit_env]]; ingest notes [[reference_pashov_fizz]].

*Three bug-hotspot axes (bump score on a file that hits any):* **Complexity** (math-heavy, cross-chain/bridge, diamond proxy — stacked assumptions), **Innovation** (novel RWA/ZK/privacy, new yield mechanics, consensus tweaks, uncommon language/chain — fewer reviewers), **Optimization** ("many bugs originate from optimization": heavy assembly, gas-opt, manual memory mgmt, rewritten math — an assembly/rewritten-math block = automatic score-bump, edge cases hide there, especially post-refactor). These compose with the assumption-enumeration lens below.

*Complexity is also a crowd-thinness signal, not only a bug-density one (@_blockian/$1M Immunefi: "go into the most complicated part — the area most researchers avoid"):* the hairiest module is double-under-served — more bugs AND fewer eyes on it. This is the within-target analogue of program-level crowd-avoidance ([[feedback_fresh_public_h1_is_crowded]]): even on a crowded program, the part everyone skims past stays quiet. So the Complexity-axis bump carries an EV bonus (less dup-risk), not just a hit-rate one — deliberately steer toward what makes you think "this is too gnarly to bother", and chant the T0 axiom "there are always bugs" while you dig.

**Corpus note (crypto-primitive / ZK / cryptographic targets):** what you feed into context can matter MORE than which files you read or how you prompt. In the public Zcash Orchard Halo2 under-constraint case, the decisive difference was that the primitive's full **reference book** (the halo2 book) was seeded into context — not just the protocol spec / ZIPs. Before reading a crypto primitive's implementation, gather and seed its underlying reference material (the math/protocol "book" for the curve, proof system, hash, consensus primitive), not only the project's own spec. The implementation bug is often only visible against the primitive's ground truth.

**Assumption-enumeration reading lens (apply while reading any score-3+ file):** every *optimization*, *guard*, *cache*, and *early-return* is a **bet that some condition holds** — and the bet is usually undocumented. Don't read the body first; read the **assumption it encodes**, then ask *"who controls the variable that breaks this bet?"* A gas-opt `if (lastCheckpoint >= block.timestamp) return` bets "nothing changes the balance twice in one block" — but the attacker owns transaction-call ordering, so they compose `checkpoint → rebalance → deposit` to force the stale window (Tranchess 2026, Cat 9.6, $200K). Generalize: for each guard/opt, write the implicit assumption as a sentence, then find the actor + variable that falsifies it. Each falsifiable assumption = a seed hypothesis (→ T7). "The attacker owns call ordering inside one tx" defeats virtually every "this won't happen in the same block" assumption. See [[reference_bounty_case_studies]].

**Boundary-value instantiation lens (bugs cluster at state edges, not the happy path — 0xvivekd "boundary-obsessed", [[reference_0xvivekd]]):** never read a stateful/accounting function once on a *nominal* input. Re-instantiate it at the five boundaries and ask "what breaks here?" — the happy-path read is the least productive one. This is the unifying discipline behind our scattered share-bug classes (1.1/1.6/8.3/8.6); run it on every score-3+ function:
- **Zero-state** — `totalSupply==0`, empty pool, no deposits. Genesis OR a mature vault driven *back* to empty (burn/redeem-all). Division-by-zero, 1:1 price reset, donation/inflation re-entry (Cat 8.6 Thetanuts free-mint, [[project_thetanuts_hack]]).
- **Max-state** — max-uint, cap reached, full utilization, max positions. Overflow, cap off-by-one, rounding-at-scale, fee/interest saturation.
- **First-depositor / first-actor** — the actor who sets the initial ratio (Cat 1.6 donation/inflation; first oracle write; price-setting by the first LP).
- **Last-withdrawer / last-actor** — the actor taking the *final* unit/share out → `totalSupply→0` leftover-dust capture, rounding crumbs stranded or seizable, division-by-zero on the *next* op, "who eats the remainder". (Often-missed twin of first-depositor — name it explicitly.)
- **Dust-amount** — 1 wei / sub-minimal amounts → truncation-to-zero free mint, `fee==0` / `shares==0` bypass, donation seeding.
Pairs with the assumption-enumeration lens: the implicit "this won't happen" assumption almost always holds on the happy path and **breaks at exactly one of these five edges**. Each boundary that breaks something = a seed hypothesis (→ T7).

**State-change-as-hypothesis framing (0xvivekd "adversarial-first"):** extend walk-backward (which starts at value *exits*) to its exhaustive form — treat **every state write** as a hypothesis open until you've answered two questions: *(a) who can reach this write?* (reachability/auth trace) and *(b) what does it cost to push the written value past its intended bound?* (cost-to-break, not just "is it reachable"). A write that is cheaply reachable AND cheaply pushable past bounds is the finding; the cost half is what separates a real exploit from a theoretical one (and feeds the EV gate, `attack_ev_estimate.py`).

**Mental-tool reading protocol (anti-skim mechanism — binds the lens above to forced depth):** the assumption-enumeration lens tells you WHAT to surface; this tells you HOW to keep yourself from skimming past it. Three tools, each with a binding trigger→marker — when the trigger fires you **emit the marker in your working text before continuing** (full protocol: [`scripts/web3/checklists/hypothesis/mental_tool_reading_protocol.md`](../scripts/web3/checklists/hypothesis/mental_tool_reading_protocol.md); per-lens prompts in `scripts/web3/prompts/reading_lens_{feynman,socratic,inversion}.md`):
- **`[Feynman: <name>]`** — ALWAYS first on opening any function/contract: explain it in plain English, no Solidity jargon; wherever wording slips to a technical term you're papering over an assumption — bug hides there.
- **`[Socratic: <file:line> — why?]`** — on an unclear line: drill past "because that's how it's written"; first answer restates code, ask again until the implicit belief surfaces (this is the line-level form of the assumption lens above).
- **`[Inversion: <fn>]`** — on a path that reads clean / a guard that looks sufficient: three concrete attacker moves (specific addresses/values/states) to defeat it. On a bug conclusion → amplify, never refute ([[feedback_push_severity_ceiling]], Mandate 0.7).
Markers are greppable for self-audit: a score-3+ file read with zero markers = you skimmed, re-read. Markers live in reasoning text, not in the hypotheses.md / FINDING block. Adapted from pashov/skills senior-auditor SOP, [[reference_pashov_skills]] block B.

**Entry-point moves inside a score-4/5 file (top-hunter mental models, [[reference_hunter_mental_models]]; full set in `sessions/_methodology/hunter_mental_models.md`):**
- **Walk backward from value transfer** (Mudit): start at where value LEAVES — `transfer`/`transferFrom`/`call{value}`/`delegatecall`/`mint`/`burn`/`selfdestruct` — and trace backward through every reaching path, checking the control at each hop. Exit points are the crown jewels; don't read top-to-bottom.
- **Constraint-mismatch pass** (0xRajeev): enumerate sibling paths (deposit/withdraw, each handler, each message type, **single vs batch/multicall — 3.13**), list the guards each applies, **diff the set — the outlier that skips a guard its siblings have = the hypothesis.** This is the reading-procedure form of "the dog that didn't bark" (taxonomy 3.1). **Anti-FP gate first (Symmetry Sniper):** before judging any asymmetry, prove from docs/naming/events/interfaces/tests that the two sides are *meant* to mirror — the lens's dominant failure mode is inventing a symmetry the protocol never intended. Then diff on five axes: state written · assets moved · auth enforced · rounding · zero/boundary (taxonomy Cat 3 gate).
- **Memory-trigger pause** (samczsun): on any pattern that resonates ("I've seen this shape"), STOP and cross-check it against `hypothesis_taxonomy.md` + the `reference_*_hacks` memories before moving on — recognition finds more criticals than first-principles deduction (samczsun's $350M MISO was one Opyn association).

**Anti-pattern:** scrolling through repo file tree top-to-bottom. That's not exploration — that's tourism.

**Deployment-set / orphaned-TVL enumeration (scope the on-chain surface BEFORE scoping the repo):** the repo/in-scope list shows *current* contracts; an attacker enumerates *every* contract the protocol ever deployed. Deprecated/legacy contracts that still hold a residual balance run **old, pre-audit-era, unpatched code** (no inflation guard, old rounding, no reentrancy lock) on **live money nobody is watching** — the highest-EV surface for a known-class bug. This is the inverse of "deployed ≠ repo HEAD" ([[project_templar_hunt]]): here **deprecated ≠ value-free**. It is also the on-chain extension of single-target mastery ([[feedback_single_target_mastery]]): own a target → know its contract *graveyard*, not just its current deploys. **This is the single most validated June-2026 pattern — 4 of the month's exploits live here:** Thetanuts ($2.1M, migrated-from vault still held option-token TVL → 8.6 free-mint), **Aztec Connect ($2.19M, deprecated 3yr immutable rollup; the buggy V3 upgrade was never externally audited → 14.9)**, Raydium ($1.34M, deprecated AMM V3 pools), **Haedal ($915K, deprecated deposit *path* still callable post-upgrade → 10.5)**. Two extensions beyond "whole deprecated contract": (a) **deprecated PATH/function** — an old entry function still callable inside a LIVE upgraded protocol with changed accounting (Haedal, Cat 10.5/15.14); (b) **unaudited upgrade on a funded contract** — a later upgrade (often the actual bug) that skipped external audit because the contract was "old/deprecated" (Aztec V3). Whitehats rescued funds off these surfaces ($2M Thetanuts, 68 NFTs Flooring) — legit rescue play.
- **How:** for each known deployer/factory address, list all created contracts (Etherscan `txlist`/factory `Create*` events) → balance-check each (ERC-20 `balanceOf` + native) → any deprecated contract with non-trivial TVL = candidate → fetch its (old) source and run the full taxonomy against THAT version, not HEAD. Tool: `py -3 -X utf8 scripts/web3/detectors/orphaned_tvl_enum.py --deployer <addr> --chain eth`.
- **Scope nuance:** programs often declare these "out of scope" ("no relation to current products"). Still worth it: (a) many programs cover all deployed contracts — check the rubric; (b) legit white-hat rescue play (someone saved $2M here); (c) prime real-money surface. If out of scope for bounty, flag to the operator as a rescue/disclosure candidate, not a paid submission.

**Boundary-centric SELECT — the SECOND candidate stream (companion to file-scoring above; the July-2026 lens).** The rubric scores files by what they DO (code-centric). But the dominant 2026 loss pattern is bugs that live NOT in the target's own logic but on its BOUNDARIES — where it trusts something it doesn't validate. **6 of the 10 largest hacks of 15.06–11.07.2026 lived on a boundary** (Bonzo/Supra, Taiko, Polymarket, Summer.fi, Aztec, Thetanuts), and each target's audit stopped AT the contract perimeter (Bonzo: 3× Halborn, all clean — the bug was in Supra, a third-party verifier scoped OUT). **This is our edge, stated mechanically: audits scope the contract perimeter; the boundary is where the audit STOPPED = where it's rawest = our territory.** So SELECT draws candidates from TWO streams — code-centric (top-5 files) AND boundary-centric (below) — both feeding the SAME single-pick loop.

⚠ **BOUNDARY IS A DEPTH-LEAD SELECTOR, NOT A BREADTH CHECKLIST (read this before using it).** The failure mode is obvious and must be pre-empted: *"enumerate all 8 dependencies → 8 H-NN → check each shallowly → 'all deps verified, clean'"* = textbook false-exhaustion (the BREADTH_RE trap, [[feedback_hunt_loop]]). Boundary enumeration produces CANDIDATES; you then pick the ONE strongest boundary (max severity×confidence) and DRIVE it down ≥5 layers, exactly like any depth-lead. On Bonzo the depth path is: `Bonzo price-consumer → oracle interface → Supra verifier contract → BLS pairing call → precompile 0.0.8 → pairing INPUTS` (layer 6 = the bug). ONE boundary to the floor — NOT five boundaries at layer 2.
- **Enforcement (inherits existing gate, NO new breadth-gate):** listing boundaries without driving one ≥5 layers trips the SAME `active_ledger_wide_but_shallow` depth-order. A boundary written into `Depth-Lead:` counts as a driven thread; a bare dependency list does not.
- **Dismissal inherits the kill-taxonomy:** "dependency is audited / redundant multi-oracle / standard integration" = `[SCOPED-OUT]` lexicon (WEAKER than `[KILLED]`, [[feedback_hunt_loop]] FALSE-EXHAUSTION) → requires cold re-audit + a falsifier `file:line` in the verifier, NOT a free pass. Bonzo's Supra was marketed "redundant multi-oracle protection against manipulation" — and it was the single point of failure. A boundary is CLOSED only by a depth-trace to the primitive OR a falsifier in the verifier; "looks fine" = contested building-block.

*Three boundary sub-lenses (each generates depth-leads, not lists):*
1. **Trust-boundary map (recon):** enumerate every EXTERNAL thing the target trusts without owning its validation — oracle/price feed, bridge/attested message, TEE attestation, external token valuation, vendor script/frontend dep, signature verifier. For each: *"what if it lies / is forged / returns true on garbage?"* Pick the strongest → DRIVE. (Bonzo, Taiko, Polymarket.) Promotes hunter_mental_models "external-dependency pass" from afterthought to a first-class SELECT stream.
2. **Verifier-input / binding audit (syntactic — GREPPABLE, the most-cited half):** on EVERY `verify`/`pairing`/`attest`/`ecrecover`/`checkProof`/`isValid` call, ask two questions — *(a) are the INPUTS validated before the result is trusted?* (non-zero, subgroup, point-at-infinity, staleness — Cat 14.12) and *(b) is the RESULT bound to the recipient/action?* (recipient a proven public input, not attacker-supplied — Cat 14.13). This is the unifying meta-form behind 5.13 / 14.9 / 14.10 / 14.12 / 14.13 — the "verifier accepts what it shouldn't" family. Detectors: `verifier_binding_audit.py`, `bls_pairing_zero_input.py`.
3. **Temporal-state map (the orphaned-TVL block ABOVE is exactly this sub-lens):** the live↔deprecated boundary. Two catalogued forms: dead-but-funded contract/path (orphaned-TVL) AND paused/capped-but-still-in-formula component (Cat 3.15, Summer.fi). Detector: `orphaned_tvl_enum.py`.

**Code-signal → taxonomy lookup (TRIGGERS, ugwst-sec):** while scoring, treat certain imports/function names as *mandatory-class* triggers — seeing the signal obliges you to run that taxonomy Cat, not optionally. Complements the gap-map (it forces classes, the gap-map forces files). Non-exhaustive:

| Code signal seen | Mandatory Cat(s) |
|---|---|
| `latestRoundData` / `latestAnswer` / Chainlink import | 5.1 (freshness), 5.10 (L2-sequencer if L2) |
| `ERC4626` / `totalAssets` / `convertToShares` | 1.2/1.6 (rounding/donation), 8.3 (inflation) |
| `liquidate` / `seize` / `healthFactor` | 8 (liquidation), 5.2 (oracle manip), 21 if perp; **8.7** if health calc adds `pendingYield`/`unrealizedPnl` mid-liquidation, `accrue()` not paused symmetric with repay, `whenNotPaused` asymmetric repay-vs-liquidate, or `liquidate` self-callable (fairness/pause-symmetry) |
| `beforeSwap`/`afterSwap`/`unlockCallback` / PoolManager | 12.7 (hook-delta/privilege), 6 (reentrancy) |
| `fundingRate` / `markPrice` / `openPosition` | 21 (perps) |
| `buyCover` / `assessClaim` / parametric trigger | 20 (insurance) |
| greeks / `impliedVol` / `settle` / DOV roll | 19 (options) |
| intent / `quoteId` / Permit2 / Dutch-auction | 16.9/16.10, 5.8 |
| `<--` in `.circom` / `keccak256(proof)` | 14.7 (run `circom_underconstraint.py`) |
| BLS `pairing`/`ecPairing`/`e(` / aggregated-oracle or committee sig verify (Supra/DVN/threshold) — check for missing `!= 0` / subgroup / point-at-infinity guard on sig AND pubkey | 14.12 (verifier trusts result without input-validation — run `bls_pairing_zero_input.py` / `verifier_binding_audit.py`) |
| `escapeHatch`/`claim`/`withdraw`/`processExit` gates on `verify(proof)` but payout `recipient`/`owner` comes from calldata (not a proven public input); any `proofless*`/`fast*`/`legacy*` deposit-withdraw path | 14.13 (proof verified but not bound to recipient/action — run `verifier_binding_audit.py`) |
| `pause`/`cap`/`deprecate`/`offboard`/`retire` flag on a sub-vault/market/collateral that is STILL summed in NAV/`totalAssets`/`healthFactor`/quorum | 3.15 (paused-but-in-formula stale-inclusion — run `orphaned_tvl_enum.py`) |
| signed-report oracle: `ecrecover`/BLS recover + `authorized[signer]` gate, consumes a `reportTimestamp`/`publishTime`/`updatedAt` from the payload, but NO `reportTs <= block.timestamp (+skew)` upper-bound and NO price-plausibility band vs previous | 5.14 (future-dated / no-upper-bound oracle report — staleness checks OLD only, not FUTURE; run `oracle_report_timestamp_bound.py` — Ostium $18-24M) |
| stablecoin/pegged token where `mint`/`issue` reads a live price/oracle/CR but the inverse `burn`/`redeem`/`repay` pays collateral at a hardcoded peg (`* 1e18`/`PEG`/1:1) with NO price/depeg guard | 3.16 (redemption assumes the peg the mint path enforces — run `peg_check_asymmetry.py`; **first establish mint & burn are MEANT to mirror** — Cat 3 anti-FP gate; thin-pool amplifier 5.2 — Chi Protocol) |
| pause/circuit-breaker whose RE-ARM is time-gated after unpause/reset (`lastUnpause + cooldown > now` blocks `pause()`); esp. paired with an unchecked `router.call(data)`/`_swapViaRouter` (no target-validation) and dual registries (router-list AND account/whitelist over the same address) | 9.7 (breaker re-arm cooldown weaponized — bait-trip → team unpauses → attack inside the unprotectable window; composite with unchecked-call + dual-role — run `breaker_rearm_cooldown.py`; ArcadiaFi $3.6M) |
| `gasleft()` before `.call{gas:}` | 13.7 (1/64 rule) |
| `try ... catch (bytes memory ...)` / `returndatacopy(.,.,returndatasize())` on untrusted callee | 13.8 (returndata bomb DoS) |
| permissionless fn (`convert*`/`redeem*`/`process*`/`*Helper`/`*Router`/`*Converter`) takes a caller-supplied address, reads its `getStatus`/`winner`/`yesToken`/view-returns as truth, then `approve`s + `call`s it — with NO `manager.isActive*`/`factory.isPair`/`registry.contains` membership check | 4.8(c) (untrusted contract trusted as source-of-truth + approval drain — Trueo H-01; `nonReentrant` is placebo, theft is in the attacker's callback) |
| `abi.decode` tuple with skipped fields `(,,, x)` feeding a backing/surplus/collateral total | 3.12 (one-sided external read — dropped liabilities) |
| both a single-item path (`doX`) AND a batch/aggregate path (`doMany`/`*Batch`/`multicall`/`claimMany`/`*All`) mutate the SAME core state — diff the loop body vs the single entry for a dropped per-item `require`/modifier (`onlyX`/`whenNotPaused`/`nonReentrant`/cap/allowlist), per-item-vs-per-batch cap confusion, `msg.value`/nonce/sig reused across iterations, or failure-swallowing that still credits | 3.13 (batch-vs-single parity gap — Zero Cool "Symmetry Sniper" class). **First establish single=batch-of-1 is intended (docs/naming/tests) before judging** — the Cat 3 anti-FP gate |
| `WordCodec`/`insertUint`/packed slot | 2.8 (packed collision) |
| inlined/forked `SafeERC20`/`SafeTransferLib`/`Address` copy ("for gas") | 1.10 (diff vs upstream for a removed guard — kankodu Balancer) |
| `delegatestake`/operator/AVS/restaking | 5.11 (restaking economics) |
| `slash`/`penalty`/`bonus`/`reward` math, `liquidationBonus`/`seize`, emission-funded APR, auto-quoting off `movingAverage`/`twap` | 22 (incentive-equilibrium: penalty<profit, liquidator-collapse, superior-knowledge, OEV, death-spiral) |
| (geth fork) `tx.GasPrice() == 0` / `genesisContracts[` / `onlyCoinbase`/`onlySystem` as privilege gate | 18.7 (system-tx auth by side-channel), 18.6 (slash→jail monopoly) |
| target language = **Go** (`go.mod` present — Cosmos-SDK / geth fork / Tendermint / Heimdall / bridge-relayer / oracle daemon / sequencer) | run `scripts/web3/checklists/go_language_footguns.md` — language-substrate below Cat 18: typed-nil/stale-err silent error-swallow, value-receiver state-loss, slice-aliasing key-remnant, nil-map panic-DoS, build-tag-hidden tests. **Check `go.mod` version: <1.22 = loop-var/parallel-test capture traps live.** (Sigma Prime "Go for Security Auditors") |
| target language = **C/C++** (`*.c`/`*.cpp`/`*.h`, `CMakeLists.txt`/Makefile — Firedancer, powHSM, native daemon) | run `scripts/web3/checklists/c_cpp_footguns.md` — memory safety (UAF/overflow/realloc-dangling), `snprintf` return mishandling, signed-overflow-UB-deletes-the-check, `EINTR`/partial-read, lambda dangling capture, DLL planting; + Cat 26 for secret-handling code. (Trail of Bits `c-review`) |
| **DVT / distributed-validator** target — SSV (go-ssv / Anchor-rust), Obol-Charon, SafeStake, Diva; crate/module names `signature_collector`/`bls_lagrange`/`partial_signature`/`keysplit`/`validator_store`/`qbft`/`qbft_manager`; threshold-BLS partial sigs + Lagrange combine | 14.11 (threshold-BLS operational — conflicting-partial-sig tolerated/`continue`, share-length not asserted, Lagrange over unvalidated operator IDs, slashing-protection toggleable→double-sign) + 18.8 (QBFT round-change/quorum=`n-f`/justification gap). **Anchor(Rust)↔go-ssv = T8 cross-client differential (18.2).** No bounty on the node yet — disclosure-only, ingest-grade |
| **PoS consensus client** — ETH CL (Lighthouse/Prysm/Teku/Nimbus/Lodestar) or GHOST-derived L1; modules `fork_choice`/`proto_array`/`state_processing`; symbols `proposer_boost_root`/`PROPOSER_SCORE_BOOST`/`get_proposer_head`/`is_head_weak`/`unrealized_*_checkpoint`/`equivocating_indices`/`reorg_*_threshold` | 18.9 (fork-choice manipulation — ex-ante/ex-post reorg, proposer-boost misapply/non-expiry, unrealized-justification gap, equivocation not subtracted) + 18.2 state-transition divergence (epoch-processing edge vs pyspec → diff `state_root`). **EF bug bounty covers CL (real $, but crowded/mature). T8: same block+attestations through ≥2 clients, diff head/`state_root`.** |
| **consensus/full node** internals — config `disable_peer_scoring`/`*_rate_limiter_config: Option(None default)`/discv5 `filter_max_nodes_per_ip`; `beacon_processor`/work-queue/`work_reprocessing_queue`/`MAX_*_QUEUE_LEN`; engine-API `PayloadStatus`/`is_optimistic`/`latest_valid_hash`/`ChainHealth::Optimistic` | 18.10 (node DoS — off-by-default hardening / work-queue starvation / reprocess-queue exhaustion; read node DEFAULT config) + 18.11 (optimistic-sync CL↔EL payload-trust — bad optimistic import, `latest_valid_hash` mis-invalidation). Read DEFAULTS not just exposed knobs |
| `SgxVerifier`/`registerInstance`/`MrSigner`/`MrEnclave`/`mrTd`/`AutomataDcap`/DCAP quote parse / TEE-prover attestation verified on-chain | 14.10 (attestation verifier trusts signer-identity not program-measurement; + recon: grep prover repo for committed `*.pem`/`enclave-key` — Taiko Raiko $1.7M) |
| reward/airdrop/points eligibility gated on `balanceOf(msg.sender)==0` / first-time-caller / fresh-address, no claimed-mapping, no stake-cost, no identity binding (CREATE2-batchable) | 22.6 (Sybil-extractable permissionless reward — price "cost of N identities" vs "reward×N"; WUSD $200K) |
| public-input / `public_witness`/`make-public`/`<--`/`assign_advice` on a signal the on-chain settlement BRANCHES on — verify it's `===`-constrained, not merely published (any backend: Circom/halo2/TurboPlonk) | 14.7 (make-public ≠ constrain — Aztec EscapeHatch $2M; sibling 14.9) |
| `amountOutMin`=`0` / no-deadline swap inside a token `_transfer` hook / buyback / auto-LP / keeper any user can trigger | 22.2 (protocol sandwiches itself — ATM $243K) |
| tax/FOT token classifying transfer as add-liquidity-vs-sell off raw reserve delta w/o authenticated-router check | 11.1-B (fee-mode misclassification via reserve skew — DTXT/BOSS) |
| `isValidSignature`/`isValidSignatureNow` called on a signer address taken from calldata; `r`/`s`/`v` parsed from `msg.data` without offset bounds; Safe/Zodiac `Delay`/`Roles` module `*SignedBy()` | 14.5 (verifier-side EIP-1271 magic-value spoof — is the signer contract checked against an owner allowlist?) |
| `agentId`/`agentURI`/`agentWallet` / `IdentityRegistry`/`ReputationRegistry`/`giveFeedback` / `ACPCore`/`Evaluator`/`createJob`/`claimRefund` / x402 `PAYMENT-REQUIRED`/`paymentId` | 23 (agent economy — EIP-8004/8183/x402; **also tag the target `agent_economy` in `_tags.txt`** so `agent_economy_escrow_identity.yaml` fires) |
| `.cairo` files / `#[starknet::contract]` / `consume_message_from_l2`/`send_message_to_l1` / `replace_class_syscall`/`deploy_syscall` / `__validate__`+`__execute__` (AA) / Starknet OS `program_output` | 15.28 (Cairo/Starknet — does the bridge message hash bind sender+token+amount+recipient? is `replace_class` owner-gated? OS output commits class root? validate/execute state desync?) |
| **target program scope INCLUDES a chain/appchain/alt-EVM engine** (node/runtime/precompiles in-scope) — custom precompile registry / `ExitTo*` / native-asset-as-token (`OVM_ETH`) / u256→u128 balance conversion / forked `go-ethereum`/`revm`/Substrate `frame-evm` / custom opcode table | 18.13 — map the ENGINE at PARITY with contracts (T1 ranks both; don't default to contracts-only); run `client_node_hunting.md` Alt-EVM lens + T8/T8-B differential vs canonical. **Scope-gate:** engine = separate program (protocol-on-chain) → out of scope here, flag as a separate target |
| target parses **Bitcoin tx / SPV proof / script** — `OP_CHECKSIG`/`OP_NIP`/`OP_DROP`/`P2SH`/`P2WSH`/`witnessScript`/`redeemScript`/`scriptPubKey`/`merkleProof`/`SPV` / `BytesParser` over raw BTC bytes | 27 (Bitcoin/UTXO/SPV) + `learning_paths/bitcoin_utxo.md` — treat address/amount extraction as ADVERSARIAL: build scripts that fool the heuristic (`OP_NIP` stack tricks, pubkey-looking witness, trailing-byte malleability) |
| import/inherit `DN404`/`DN404Mirror`/`ERC404`/`BT404`; `uint32(id)`/`uint64(id)` cast on a tokenId; packed `Uint32Map`/`LibMap` ownership; large `unchecked{}` wrapping transfer with the balance check OUTSIDE | 11.7 (ERC404/DN404/BT404 dual-accounting — run `erc404_dual_accounting.py`) |
| rollup/proof settlement (`processRollup`/`submitBatch`/`verifyAndExecute`) whose loop bound (`numTxs`/`realCount`) comes from calldata; bulk-hashed public inputs (SHA256/keccak over fixed buffer) with a variable subset acted on | 14.9 (ZK proof↔settlement scope mismatch — committed-but-unvalidated gap slots) |
| (Sui/Aptos Move) upgraded package where a prior-version `entry fun deposit`/`mint` lacks `assert!(version==CURRENT)`/`Version` shared-object/`AdminCap` gate; old+new modules over same `Shared` object | 15.14 / 10.5 (cross-version path arbitrage — old-mint × new-redeem) |
| permissioned/RWA token markers: inherit `ERC1400`/`IERC1400`/`ERC3643`/`T-REX`/`ERC1404`/`IModularCompliance`/`IIdentityRegistry`; `byPartition`/`partitionsOf`/`operatorData`; `canTransfer`/`isVerified`/`canTransact`/`DefaultCompliance`; `forcedTransfer`/`controllerTransfer`/`recoveryAddress`; NAV/`proofOfReserve`/redeem-fires-offchain | 24 (RWA permissioned-token — run `rwa_permissioned_token.py`; enumerate EVERY balance-changing path for a compliance call (24.3), check `Σ partitions == total` (24.1), verify bound compliance ≠ `DefaultCompliance` (24.4); **also tag `rwa`/`permissioned_token` in `_tags.txt`** so `rwa_permissioned_token.yaml` fires) |
| (Move/Sui) `.move` source: `public fun <T>(...)` over a coin/value; `struct ...Receipt/Loan/Obligation has drop`; `table::add` without `table::contains`; `sender: address` param in an `assert!`; tuple getter `get_reserves(): (u64,u64)`; live `reserve`/`get_amount_out` spot read in a `public fun` (PTB-composable); `Move.toml` `[dependencies]` on an upgradeable package; randomness from `tx_context::digest`/`object::uid`/`epoch`; checkpoint/`advance_epoch` reachable only AFTER an `assert!` that can perpetually fail; capability gated on a generic `<T>` with no concrete-type assert | 15.15-15.20 + **15.25** (Move/Sui safety — **run `scripts/move/move_safety_scanner.py`**; type-confusion / drop-debt / hot-potato / table-DoS / sender-spoof / PTB atomic manip / dependency-upgrade contagion / digest-randomness / abort-before-checkpoint deadlock / phantom-type role bypass) |
| (Solana/Anchor) `spl_token::transfer`/`transfer(` where the mint may be Token-2022 (no `transfer_checked`); collateral math on `TokenAccount.amount` without `amount_to_ui_amount`; authority instruction with no `Clock`-based expiry (durable-nonce-replayable); positional `remaining_accounts[i]`/ALT-indexed account without a key assertion; `calculate_fee`/`calculate_inverse_fee` round-trip assumed exact; `ExtensionType`/space math before all extensions pushed; same token-program `AccountInfo` reused across `transfer_checked` legs; `AccountState::Frozen`/`default_account_state` unhandled; `close_account`→`initialize_mint` on same key | 15.21 / 15.22 / **15.24** (Token-2022 hook-bypass + raw-amount mispricing; durable-nonce stale-submit + ALT positional forgery; Token-2022 lifecycle — fee-inverse drift / extension-sizing underflow / multi-leg CPI reuse / confidential-proof truncation / frozen-trap / close-reinit — note compute-DoS/reinit/type-cosplay already have dedicated `scripts/sol/hypothesis/` scanners) |
| (TON/FunC) `.fc`/`.func` contract: `~load_uint(32)` field reads with no trailing `end_parse()`; bounce branch not skipping the `0xFFFFFFFF` prefix; `recv_internal` opcode dispatch with no terminal `throw` | 15.23 (FunC message-parse integrity — trailing-byte injection / bounce-offset corruption / silent unknown-opcode; node-level TON is separate in `scripts/ton/`) |
| `tstore`/`tload`/`transient` with a hardcoded (un-`keccak`-derived) slot — esp. a reentrancy-lock / callback-flag reachable via `delegatecall`/multicall/hook; OR `tx.origin == msg.sender` / `msg.sender.code.length==0` / `isContract`/`extcodesize` used as a security gate; OR EIP-7702 delegation auth with `chainId==0` / no per-chain nonce | 25.2 (transient-slot collision — SIR.trading $355K) / 25.1 (EIP-7702 broken-EOA auth — cross-chain delegation replay, EOA-runs-code) |
| singleton-hook callback (`beforeSwap`/`afterSwap`/`before/afterAddLiquidity`/`_after*`) on an independently-deployed `public` hook with NO `require(msg.sender == address(poolManager))`; attacker-supplied `hookData` consumed as trusted | 25.3 (singleton-hook auth bypass — Cork $11M; complements 12.7 hook-delta — here the hook's OWN auth gate is missing) |
| (C/Rust/ZK node, signer, HSM, wallet, key-mgmt daemon) secret/key/nonce/seed buffer cleared with `memset`/`=0`/manual loop instead of `zeroize`/`explicit_bzero`/`SecureZeroMemory`; Rust secret in `Vec`/`String`/`[u8;N]` w/o `Zeroizing`/`#[zeroize(drop)]`; `==`/`memcmp` on a MAC/token/secret (vs `subtle::ConstantTimeEq`/`constant_time_eq`); secret-indexed array or secret-dependent branch/division | 26.1 (compiler-elided zeroization — confirm at MIR/assembly) + 26.2 (non-constant-time secret op — timing side-channel). Trail of Bits `zeroize-audit`/`constant-time-analysis`; relevant to Firedancer/Lighthouse/SSV/powHSM |
| CI/repo plane: `pull_request_target` + `actions/checkout` of PR head with secret access; `${{ github.event.issue.title/body/pull_request.* }}` inside a `run:` step or an AI-action prompt; AI-tool/model output passed to `bash -c`/`run:`; over-broad `permissions:`/`GITHUB_TOKEN` on a fork-triggered workflow | 23.10 (agentic CI/Actions workflow injection — expression/env-var/eval-of-AI-output/wildcard-allowlist; Trail of Bits `agentic-actions-auditor`) |
| (Aptos Move, `Move.toml` Aptos addr / `aptos_framework`) `public entry fun … &signer` with no `signer::address_of(..) ==` stored-authority check; `SignerCapability` in a non-gated struct; a fn returning `ConstructorRef`; `&mut Coin`/`&mut FungibleAsset`/`|...|` closure params w/o post-callback re-validation; `has key` struct fields reordered/retyped on upgrade; both `coin::*` and `fungible_asset::*` for one token; `fun test_`/`setup_for_testing` without `#[test_only]` | 15.26 (Aptos resource/capability/upgrade family — unchecked-signer / resource-account privesc / ConstructorRef leak / function-value+mem::swap reentrancy / struct-layout upgrade break / FA-vs-Coin desync / prod-test-fn). NO Aptos engine yet → whole class high-value on first Aptos target |
| (Solana) `realloc(` without `zero_init=true`; `clock.slot` AND `clock.unix_timestamp` in one time-gate; timestamp field default 0 used in `+grace`/`<`; mutable global `reward_rate`×elapsed with no per-position snapshot; yield paid from principal acct; bonding-curve `buy` not clamped to remaining capacity / no post-clamp slippage recompute; PDA `init` with no `close` on terminal path or vault-PDA with no withdraw ix | 15.27 (Solana operational lifecycle/accounting — realloc dirty-read / clock-unit mismatch / sentinel-zero ts / retroactive-rate / rewards-from-principal / bonding-curve solvency / zombie-PDA freeze) |
| TARGET IS A BLOCKCHAIN NODE (Go/Rust/C++ client repo, not a contract): P2P/RPC handlers, consensus glue, vote/validator-set code | 18.12 (node-client impl attack-pattern sweep — **read `scripts/web3/checklists/client_node_hunting.md`**: batch break-vs-continue, vote-dedup composite-key, non-determinism→split, RPC panic, pay-once amplification, module-wiring/mock-startup, replay, non-canonical serialization, charge-order, memory/concurrency; apply 4 lenses + Zero-Trust Message Check + Cross-Subsystem Boundary scan) + 18.1-18.11 for consensus logic. Differential-fuzz 2 clients (T8) = highest EV on mature node |
| a value-bearing field has a SECOND representation in state (array + bitmap, `before`+`after` settlement, migration-side + unstake-side, on-chain total + per-account sum) and an enable/switch/migrate fn changes which is authoritative; increment on one twin with no matching decrement on the other; two similarly-named amount vars (`x` vs `xAfterSettlement`) across half-phases; batch id-array with no already-processed flag | 3.14 (dual-representation desync / double-count — assert `rep_1 == rep_2` across EVERY transition that mutates either; pivot to the complementary fn when the target reads clean). Highest-frequency accounting family: Notional $1M / Polygon $75K / Synthetix $150K / Redacted $560K |
| `permit(`/`selfPermit`/`delegateBySig`/`*BySig`/EIP-712 sig-consume called UNCONDITIONALLY at the top of a multi-step external fn (`permit(); deposit();`) with NO try/catch-then-check-allowance fallback | 7.6 (signature/permit front-run griefing — attacker copies mempool sig, front-runs standalone `permit()` → nonce consumed → victim's bundled tx reverts → DoS; permanent if no fallback). General template `A;(A;B;C)* ≠ A;B;C`: any front-runnable prerequisite step. Trust Security "Permission denied" $50K/15 projects. **Meta:** mine OLD widely-used EIPs for a hidden assumption = one bug × 100+ codebases |

Bulk-run the code-level signals at once: `py -3 -X utf8 scripts/web3/hypothesis/solodit_pattern_signals.py --target <src>`.

**Attack-tree lookup (per protocol-type):** once the target's protocol type is known, walk the matching tree in `bug-bounty-toolkit/attack-trees/` (`_INDEX.md` maps tree→Cat) top-down; each leaf you can't immediately refute = an H-{NN} candidate. This is the structured *where-to-look* companion to the taxonomy's *what-kind-of-bug*.

### Addendum — Post-Run Coverage Gap-Map (turns "found nothing" into "here's what I didn't read")

Source: asymmetric.re "Understanding Agents: Code Coverage" — empirical finding that AI audit agents read **probabilistically** and cover a fraction of the codebase; *what the agent didn't read, it didn't check*. "Coverage ≠ absence of bugs." This is the operational form of the [[no-giveup-hunt]] mandate and the [[zcash-orchard-halo2]] corpus lesson.

**Protocol (runs at the end of any pass that concluded "no findings", before reporting that):**
1. List the score-5 and score-4 files from the T1 `attack_surface_rubric.md`.
2. For each, ask: *did I actually read it this session, or just classify it?* (Be honest — classifying ≠ reading.) A file you scored 5 but never opened is a coverage hole, not a cleared surface.
3. Every uncovered score-4/5 file = a **mandatory** new H-{NN} in `hypotheses.md` (Mandate 0.2 second pass starts here).
4. **External-dependency check (MiloTruck, [[reference_hunter_mental_models]] #5):** before "clean" stands, explicitly read the external libs the in-scope code leans on for security-critical ops (OZ/Solady/Uniswap-periphery at the *pinned* version) — a forked/old/patched dep is live surface (his Arbitrum find was a replay bug in OZ `GovernorUpgradeable`, missed because nobody read outside scope). An unread security-relevant dependency = a coverage hole, same as an unread score-5 file.
5. Only after every score-4/5 file AND its security-critical deps are genuinely read may a "no findings" verdict stand — and even then, propose the next angle (Mandate 0.1).
6. **Miss-risk grade per uncovered item (DarkNavySecurity `recon-agent`).** Don't just LIST what you didn't read — grade each unread score-4/5 file / dep with a miss-risk `HIGH` / `MED` / `LOW` (how likely a bug hides there given its role) plus the open question it leaves. This turns the gap-map from a flat list into a prioritized second-pass queue: HIGH-miss-risk holes are read first. "Discovery confidence + miss risk + unresolved entry-point questions" is the honest form — never mask a gap as cleared.
7. **BREADTH ≠ DEPTH gate — a "whole scope covered" claim is NOT an exhaustion verdict.** "deployment checked on all 4 chains / every collateral feed checked / end-to-end / certainty HIGH" after *hours* on a multi-chain / 100+-market target is a **breadth sweep** (file-level classification), physically incapable of being depth-exhaustion — same false-exhaustion as "checked all 40 contracts in 30 min" ([[no-giveup-hunt]]). Before any "no High/Crit" verdict on a broad surface, three DEPTH obligations must PASS, not just breadth: **(a)** depth-ceiling ≥5 layers on the *strongest* thread (ONE market down `feed→aggregator→band→liquidation→accounting`, not 79 markets skimmed); **(b)** T6 composite pass over the latent defects; **(c)** multi-deploy target → T8 cross-chain differential is **mandatory coverage**, not optional. **≥2 latent defects found = the surface is FERTILE, not "clean":** where 5 latents are each "dead alone", the 6th live bug sits DEEPER or in a PAIR (T6) — never conclude "all latent → pivot". A **config/band divergence between chains** (band present on chain A, absent on B) is a `deployed<audited` defense-regression = a **live lead to pull down**, not a "latent Medium". Enforcement (structural, not lexical): completeness-gate `BREADTH_RE` + `FORK_RE`/`DECISION_Q_RE` + REASON point (7).

This pairs with T4: T4 kills false positives (cold verifier), the gap-map kills false negatives (unread surface). Both resolve doubt with evidence, not vibe. *(Optional future tooling: asymmetric-research/agent-coverage parses Claude Code session files into a coverage map; not integrated — manual gap-map is the standing discipline.)*

---

## Technique 2 — Hypothesis → Isolated Container → PoC Strict Loop

**Problem this solves:** Loose hypothesis discipline = digging in 4 directions at once, never finishing any of them, mistaking "I looked at it" for "I ruled it out". Mythos formalizes this as a hard state machine: one hypothesis active at a time, must be killed or PoC'd before pivoting.

**Protocol (state machine, no skipping states):**

```
STATE A: HYPOTHESIS FORMULATION
  - Write hypothesis in ONE sentence with attacker action and observable outcome:
    "If attacker calls X with Y, then Z observable effect on chain/in storage/in response."
  - BAD: "Maybe there's a reentrancy issue somewhere in the vault."
  - GOOD: "If attacker calls vault.deposit() with rebasing-token A and re-enters via
           A.transfer hook to call vault.withdraw(), then their shares > deposited assets."
  - File: sessions/{target}/hypothesis/{H-NN}_one-liner.md
  - Required fields: hypothesis, target file:line, attacker prerequisites, success signal, kill signal,
    marker-trail (the [Feynman:]/[Socratic:]/[Inversion:] markers from T1 reading that surfaced it).
  - A hypothesis with no marker-trail is a coverage gap masquerading as a check — go back and read the
    file with the mental-tool protocol before promoting it (T1 reading protocol).

STATE B: ISOLATED CONTAINER SETUP
  - Sandbox MUST be reproducible offline: local TON node, Foundry fork pinned to block,
    solana-test-validator with --clone, anvil --fork-url + --fork-block-number.
  - NO mainnet calls. NO testnet calls. NO live RPC against shared infra.
    Per [[feedback-onchain-autonomous-policy]] memory — burner is OK for read; for write only with hard caps.
  - File: sessions/{target}/hypothesis/{H-NN}/sandbox.sh (script that brings up env from cold).

STATE C: POC ATTEMPT (BOUNDED)
  - Set a time/effort cap UP FRONT: e.g. "2 hours, then transition to STATE D-kill or D-escalate".
  - Iterate on PoC inside the sandbox only.
  - Log every iteration in sessions/{target}/hypothesis/{H-NN}/iterations.md
    (input → result → next hypothesis adjustment).

STATE D: RESOLUTION (mandatory transition)
  - D-PoC: success signal observed → write up finding, transition to submission flow.
  - D-Kill: provable refutation (code path doesn't reach hypothesis, invariant holds,
            external constraint blocks). Document in {H-NN}/killed.md WITH the killing evidence.
  - D-Park: bounded-time cap hit, neither PoC nor kill. Document open questions, move H-NN
            to sessions/{target}/hypothesis/_parked/ and pick next hypothesis. Re-visit only
            if new evidence emerges.
  - FORBIDDEN: "kinda looked at it, moving on" without filling D-Kill or D-Park doc.
    Per [[feedback-no-cheating-on-verification]] memory — this is the cheating mode.
```

**Pivoting rule:** new hypothesis emerges mid-PoC? Write it to a parking lot file (`{target}/hypothesis/_inbox.md`), DON'T context-switch immediately. Finish current STATE C/D first. Per [[no-giveup-hunt]] memory — this prevents flaky 30-min pivoting; the inbox is the place hypotheses wait their turn.

**Why this is strict:** the discipline IS the technique. Mythos's "agentic scaffolding" is essentially this loop run by the model; we run it manually with the same rigor.

**Read-time anti-false-positive gates (samczsun, [[reference_hunter_mental_models]] 8a/8b) — apply at STATE A before promoting, and before claiming D-PoC:**
- **Compensating-controls check (STATE A gate):** a missing access-control / missing check is NOT yet a hypothesis — *"developers are unlikely to make such an obvious mistake"*. First hunt for the guard ELSEWHERE (another modifier, caller-side check, upstream invariant). Promote to H-{NN} only if no compensating control exists. This kills phantom bugs early — but the instant a control is genuinely absent, escalate, don't argue it away (Mandate 0.7).
- **Calculator heuristic (pre-D-PoC gate, #1 anti-hallucination for an AI hunter):** if the hypothesis rests on a "known" EVM/language/protocol property (CALL returns true on an empty account, transfer reverts on failure, this mulDiv rounds down), VERIFY it explicitly against the spec/reference before recording either D-PoC or D-Kill — *"verify 2+2 on a calculator even though you're sure it's 4"*. Most confident-but-wrong refutations and false PoCs die here. Do not trust recalled knowledge as the load-bearing step.

**Targeted-pass + variance discipline (STATE A formulation):** a generic hypothesis ("audit this circuit/contract for bugs") and a targeted one ("audit the variable-base scalar-mul gadget for missing constraints enabling inflation/double-spend") have wildly different hit rates on the SAME target. In [[zcash-orchard-halo2]] the generic prompt surfaced the bug in only ~1/4 runs even on a capable model; the targeted per-component prompt found it reliably even on a weaker model. Two consequences:

- **Formulate per-component, not per-repo.** STATE A hypotheses should name a specific gadget / function / invariant, not "the system". A vague hypothesis is a coverage gap masquerading as a check.
- **Re-run, don't single-shot.** Model output has run-to-run variance; a single "found nothing" pass on a high-value component is NOT a kill. For score-5 components, run the targeted pass multiple times (and/or at higher effort) before recording D-Kill. This is the per-component analogue of Mandate 0.2's aggressive second pass.

**Spec-to-code compliance pass (STATE A generator — Trail of Bits `spec-to-code-compliance`).** When the target ships a spec/whitepaper/NatSpec/README, run an explicit alignment pass over each top-5 file and classify every spec'd behavior into one of six buckets: `full_match` / `partial_match` / `mismatch` / `missing_in_code` (spec says it, code doesn't enforce it) / `code_weaker_than_spec` / `code_stronger_than_spec` (code does MORE than documented — possible backdoor/hidden path). The three productive buckets — `missing_in_code`, `code_weaker_than_spec`, `code_stronger_than_spec` — are hypothesis factories; this is the mechanical form of the T0 "comment says *should* but code doesn't enforce" instinct. **Extend the pass to UPSTREAM / external specs, not just in-repo docs** — a forked node inherits documented invariants from the standard it re-implements (Cosmos SDK module invariants, ERC MUST-clauses, a chain's consensus spec, the audited upstream a fork diverged from) that are NOT restated in the fork's own README. The single highest-value node bugs in the backtest were exactly this: an upstream-documented invariant silently dropped in the fork (Evmos $150K — Cosmos SDK `x/bank` module-account blocklist not enforced after the fork; Wormhole guardian expiry). When the target re-implements/forks a known standard, load THAT standard's spec as the source-of-truth for the pass.

**Provenance tag — SHOULD-HOLD vs EXPLORATORY (STATE A classifier, pashov `fizz`).** Tag every hypothesis/invariant with its source of guarantee AT formulation time, with a citation:
- **SHOULD-HOLD** — guaranteed by docs/whitepaper, a standard the contract claims (ERC MUST-clause), or a closed-form math/accounting identity. A violation of a SHOULD-HOLD property is a **confirmed bug by construction** — no separate "is this intended?" review needed, only PoC + T4 reachability/impact. Tag SHOULD-HOLD ONLY with specific cited evidence (`file:line` of the spec/comment, the ERC clause, the formula).
- **EXPLORATORY** — inferred from code/naming/general DeFi patterns but NOT promised anywhere. A violation is a LEAD that needs human review before it's called a bug.
- **Default to EXPLORATORY.** No citable evidence → EXPLORATORY. This is the provenance link feeding T4 (SHOULD-HOLD shortcuts the "was it intended?" question; EXPLORATORY routes to LEAD) and pairs with the spec-to-code pass above — its `missing_in_code` / `code_weaker_than_spec` buckets ARE the SHOULD-HOLD violations.

**Reverse-mode assertion (STATE C anti-bias — finite-monkey-engine).** Forward framing ("is there a Source→Sink path without a sanitizer?") leaves the bias "maybe the existing guard is enough." After a forward pass, run one reverse pass per live hypothesis: **assume the bug exists and construct the full attack narrative** — name the actor, the call sequence, the exact numbers. If you cannot build a coherent end-to-end narrative, that's evidence toward D-Kill; if you can, you have the PoC skeleton. Pairs with the `concrete-actor-action-amount` submission gate.

---

## Technique 3 — Exploit Chaining Discipline (Severity Stacking)

**Problem this solves:** A finding rated Low/Med in isolation can chain with another Low/Med to produce Critical. Hunters who report findings atomically leave money on the table — bug bounty pays for *demonstrated impact*, not isolated weaknesses. Echo Monad ($816K, 2026-05-19) was admin-key + unconstrained-mint + fake-collateral chained; Transit Finance 2026 was ghost-contract + delegated-call chain.

**Protocol — apply at TWO points:**

### Point A: After Hypothesis Confirmation (STATE D-PoC of Technique 2)

For EVERY confirmed finding, before writing it up, ask:

1. **What ELSE does this enable?** Not "what is the bug" — "what attacker capability does the bug grant".
   - E.g. "bypass slippage check" → attacker capability = price the swap arbitrarily within block.
   - E.g. "missing access control on setOracle" → attacker capability = control oracle price feed.

2. **What ELSE in the system depends on the absence of that capability?** Grep the codebase for assumptions that are now broken.
   - Slippage bypass + AMM that assumes honest slippage = drain liquidity.
   - Oracle control + lending market that uses oracle for liquidation = trigger liquidations at attacker-set prices.

3. **Can the two combined form a Critical-tier exploit chain?** If yes, the SECOND bug is your finding's leverage point. Write up the chain, not the individual bug.

### Point B: Before Submission (Pre-Submission Sanity Check)

For each finding draft, before sending:

- [ ] Have I checked if this finding chains with ANY of the open findings in this session?
- [ ] Have I checked if this finding chains with any DOCUMENTED past finding in this protocol (audit reports, prior disclosures)? Past findings the team fixed might leave a partial-fix gap that completes a chain.
- [ ] Have I checked if this finding chains with any *protocol-level assumption* documented in their whitepaper/docs that's no longer true given this bug?

If yes to any: rewrite finding as a chain (X → Y → Z impact). Severity goes up by 1-2 tiers. Payout goes up proportionally per [feedback_hunt_all_severities].

**Negative case to avoid:** chaining two unrelated bugs into a fake "chain" to claim higher severity. Reviewers see through this immediately and it costs reputation per [[feedback-check-project-tests]] memory. Real chain = the second step is impossible WITHOUT the first.

🔴 **Draw the Dependency (FDE Plan 6, §27 — added 2026-08-07).** Two findings on the SAME target that merely *co-occur* — listed side by side ("Composite candidates: BB-08, BB-10", or two Building Blocks noted together) — are NOT a chain. Co-occurrence is a location fact ("both live in this session"); dependency is a causal fact ("B cannot happen without A"). Before writing `X → Y` in a Composite Chain, name the concrete transfer: what value/state/permission does step A's output produce that step B's input actually consumes? If you cannot point at a specific field/variable/state that A creates and B reads, you have two observations, not a chain — keep them as separate Building Blocks and don't inflate severity on their proximity. `hunt_completeness_gate.py`'s completeness-gate (Stop hook) enforces this structurally: a `Composite candidates:` claim or co-occurring `BB-NN` pair without an explicit output→input statement nearby triggers a soft nudge ("co-occurrence is not dependency, draw the dependency") — it doesn't hard-block, but it won't let the claim sit unaddressed either.

---

## Technique 4 — Two-Agent Verifier Pass

**Problem this solves:** confirmation bias kills bug bounty submissions. After 2-3 hours digging a hypothesis, the brain (and the model) is invested — every ambiguous signal reads as confirmation. Mythos achieves its 90.8% true-positive rate (per Anthropic CVD dashboard, 2026) through one specific mechanism: a SECOND independent agent re-derives every finding from cold context, with no access to the discoverer's reasoning. If verifier disagrees → finding gets killed or downgraded before submission. This is THE single technique behind Mythos's signal-to-noise ratio.

🔴 **Panel of lenses — WITHOUT majority vote (decided 2026-07-27, depth-engine plan §7).** When there are
several verifiers, they go through **different lenses** (correctness/guard · exploitability/severity · dedup-vs-audit/scope),
not three copies of the same question. **A kill counts ONLY on a hard `file:line` falsifier from any
ONE lens.** "Two of three said it doesn't look right" is `[CONTESTED]`, not a kill.

**Why majority is forbidden:** a "2 of 3 refute → kill" rule systematically kills exactly our target
class — cross-thread and depth-ceiling findings where **each clue taken alone is harmless**. The Orchard bug
lived for 4 years for exactly that reason. Majority drops recall, and that is forbidden by the measure-don't-feel rule
(Mandate 0.8). Precision is gained by a falsifier, not by voting.

**Protocol — runs after every T2 STATE D-PoC success, BEFORE T3 chaining or report draft:**

```
TRIGGER: A hypothesis just reached STATE D-PoC (Technique 2). About to write up or chain.

STEP 0 — AUDIT/KNOWN-ISSUE DEDUP **FIRST**, before any T4 verify cycle (HARD ORDER):
  WHY: a cold verifier has NO audit context — it will happily "confirm" a bug that an audit
  already published as a known/acknowledged finding → wasted verify cycle + near-submission of
  an out-of-scope dup. Real ≠ in-scope. (Example: a PoC and T4 both confirmed
  a REAL bug that was verbatim audit M-04 "Users can be unfairly liquidated", Acknowledged →
  out of scope. Whole liquidation+pending area was mined out; a 2-min grep at hypothesis time
  would have killed it before the PoC. [[feedback_check_project_tests]])
  DO THIS THE MOMENT a hypothesis looks real (ideally at T2 STATE B, at latest before T4):
    1. pdftotext -layout every audit PDF in the repo (audit/, audits/, docs/) → _txt/
    2. grep the txt for the finding's CORE NOUNS (function names, mechanism words —
       e.g. "liquidat", "pending withdrawal", "preLiquidate", the vulnerable fn name)
    3. Also grep project docs + Solodit for the protocol + Immunefi "known issues" list.
    4. ANY match describing the same root cause (even Acknowledged / unfixed / different severity)
       = OUT OF SCOPE per program rules ("all issues covered by previous audits ineligible").
       KILL the hypothesis, log dedup-kill in hypotheses.md, do NOT spawn T4. Move on.
  Only if STEP 0 is CLEAN → proceed to STEP 1. This is the same `previously-disclosed` gate from
  submission_checklist.yaml, pulled EARLIER so it runs before the expensive PoC+verify investment.
  SUBMIT-TIME FRESHNESS RE-CHECK (Plan 9 T5e): banked findings AGE — a bug clean at discovery can be
  disclosed / patched / duped before you file. Re-run this dedup (steps 1-4 above) a SECOND time at the
  moment of submission for any finding that was banked earlier (Med/Low batch-submit, or a High held
  while chaining): re-grep new audit publications / project docs / Solodit / platform "known issues"
  AND confirm the code is still live and vulnerable (deployed ≠ repo HEAD,
  [[feedback_verify_current_exploitability]]). A fresh match / patched-away path = KILL before filing,
  not after a triager duplicates or closes it.

STEP 1 — Snapshot finding artifacts:
  - Finding one-liner (attacker action → observable effect)
  - PoC script / sandbox setup
  - Code path: file:line of vulnerable function
  - Claimed severity + impact narrative
  - EVIDENCE ARTIFACT (mandatory, brutecat evidence-linking [[reference_brutecat_ai]]): the ACTUAL
    raw output the PoC produced — fork tx-hash + trace, cast/anvil stdout, container log, on-chain
    receipt — NOT a prose reconstruction of "it should return X". The verifier (STEP 2) is handed THIS
    artifact, not the narrative. No artifact = it's a LEAD, not a finding (can't ship a re-told exploit).
    Severity-critical numbers (loss, balances) MUST be quoted from this output, not assumed.
    - For routing / swap / slippage / MEV findings, two cheap artifact techniques (Ehsan Aave×CoW
      [[reference_ehsan_aave_cow]]): (a) **forensic replay** — pull the venue's reserves at the prior
      block, apply the AMM math (`x*y=k`) to the input, confirm it reproduces the executed output → proves
      WHICH venue/pool was used; (b) **counterfactual best-execution at the SAME block** — compute what the
      correct venue would have returned at that exact block → that delta IS the loss magnitude (real, not
      assumed; 52,404 vs 331 AAVE = 158× in the Aave case). Feeds severity ceiling honestly.
    - For on-chain-extraction findings, a third measured input (**AOE §3.1 fork-sim profit-oracle**,
      `scripts/web3/hypothesis/fork_profit_delta.py`): the attacker's **actual balance delta (before/after)
      on the fork** — `onchain_poc_harness.py fork-up`, do the exploit sends, snapshot before & after, diff.
      This STRENGTHENS the "numbers from actual output, not assumed" rule above; it is a **down-guard /
      realism input, NOT the source of magnitude** (magnitude = protocol_loss, victim-side — Mandate 0.10).
      🔴 Honest ceilings (the oracle prints these marks WITH the number, so it is not a hidden inflator):
      competition-dependent value (MEV/backrun/sandwich) = **ceiling-not-measured** (an isolated fork has no
      competing searchers → over-states it); liquidity-dependent = **stale** (single-block snapshot, live may
      differ under stress); the fork does NOT simulate you being front-run / griefed.
      🔗 **A1 — one run, two outputs (fork-run × T12 fan-in, Wave 1 2026-08-08).** The fork is already
      standing with the affected state loaded, so the same run MUST also emit the **T12 `fan-in`** of that
      state — grep every OTHER writer of the touched slot/vault/balance (mythos T12 DEPTH-TRACE). A writer
      from a DIFFERENT subsystem = a free second clue for T6 cross-thread synthesis (Sherlock's «dog that
      didn't bark» — another actor touches this balance and no one asked). Zero extra cost: the snapshot is
      already up. Carry `fan-in:` into the finding artifact / `attacker_profile`; it stitches the fork-run
      (a severity-down-guard) to the depth-trace `fan-in` field that `active_depth_t12_incomplete` already
      enforces at ≥3 layers — A1 does not create a new field, it wires two existing mechanisms together.
  Save to sessions/{target}/hypothesis/{H-NN}/finding_snapshot.md

  **AOE severity-components (§3 — magnitude realizability; feed the ceiling honestly, they are NOT free multipliers):**
  - **amplification** — `effective = per_shot × iterations` (a $1 leak callable 10⁶× is not a $1 bug). Modeled in `attack_ev_estimate.py --iterations`.
  - **exit-liquidity realizability** — 10M of an illiquid token ≠ $10M; haircut nominal profit to what thin exit liquidity actually clears (`--exit-liquidity`).
  - **victim-aggregation / blast-radius** — per-victim dust × N reachable victims can cross a tier; count reachable victims, not one.
  - **insider-over-authority** — undocumented power of a trusted **in-scope** role IS a finding (motive `insider-authority`, Mandate 0.10), not out-of-scope-by-assumption.
  - **pre-positioning / marination-cost** — capital locked while waiting for the setup = the opportunity_cost term (`--hold-days × --rate`); a real cost, not free.
  - **contagion / second-order (`[FIX-H1]`)** — a cascade into a *dependent* protocol B raises severity ONLY by the **reachable-AND-measured** loss in B (theoretical-TVL is BANNED — `magnitude_eval`: reachable, not TVL). MANDATORY **scope-gate: is B in-scope / does the program pay for external-protocol impact?** + a realism-falsifier for the dependency (§5.6). Not-measurable or out-of-scope → **`[LOW-DEFERRED]`**, NOT a severity multiplier.

STEP 1.5 — SELF-STEELMAN (finder writes the case AGAINST the finding, BEFORE handoff; Plan 9 T5d):
  Before the finding goes to the verifier, the DISCOVERER writes the single strongest argument that
  this is NOT a valid / in-scope / severity-X bug — the case a hostile triager would make to reject or
  downgrade it (e.g. "a guard on line N already blocks this", "this needs a precondition no real user
  hits", "the loss rounds to dust", "this is documented intended behavior"). Write it as concrete
  points, each carrying file:line or a named precondition — not vague doubt.
  This artifact is HANDED to the verifier (STEP 2), which MUST rebut each point one-by-one with
  evidence. Any point the verifier CANNOT rebut → the finding is downgraded / parked on that point,
  NOT submitted. No self-steelman written = the finding is not T4-ready (it still carries the
  discoverer's confirmation bias).
  ⚠ Merge-guard (Plan 9 R4): this is the VERIFY-side steelman ("argue against MY finding") — DISTINCT
  from the Technique 6 intent-steelman at hypothesis BIRTH ("is this behavior intended?",
  scoped-to-DRIVE). Different artifact, different phase; do not collapse the two into one.

STEP 2 — Spawn independent verifier subagent with COLD CONTEXT:
  - Use research subagent (no shared reasoning with discoverer)
  - Hand it ONLY: target repo path, file:line, PoC script
  - DO NOT hand it: discoverer's hypothesis text, narrative, severity claim
  - Verifier prompt template (use verbatim):
      "Read this code path: {file}:{line}. Run this PoC: {poc_path}.
       Independently determine:
       (1) What does this code do?
       (2) What does the PoC demonstrate? Does it actually exploit anything?
       (3) Is there any precondition the PoC silently relies on (cheat
           addresses, modified state, fixture quirks)?
       (4) What's the realistic attacker scenario in mainnet conditions?
       (5) What severity tier does the demonstrated impact warrant?
       Be skeptical. If this is not a real bug, say so."

  **P10 — HOSTILE-TRIAGER STANCE (Plan 9 R3/T5a, mdp_sec disprove-culture; the SAME one verifier
  adopts this stance — NOT a third agent):** the verifier judges the finding AS a hostile platform
  triager whose default is to reject.
  - It may NOT invent a new angle / re-frame the impact to RESCUE a weak report — it judges the
    finding AS SUBMITTED. If the finding survives only under an angle the discoverer never claimed,
    that is a KILL of the submitted finding (log the salvage-angle as a fresh LEAD for its own DRIVE),
    NOT a pass.
  - It MUST pick the EXACT platform severity classification the report will be filed under — read the
    program's own rubric ([[feedback_read_scope_before_severity]]), not a generic Crit/High/Med tier.
  - Its verdict is exactly one of: **PASS** (submit at the named tier) · **DOWNGRADE** (to the tier
    the VERIFIED evidence actually supports) · **BLOCK** (silent precondition / fixture cheat / fresh
    residual state — STEP 2.5 gates + STEP 2.6) · **REJECT** (not a valid / in-scope bug). "Probably
    real, ship it" is not a verdict.

  **Multi-axis quality check (0xSimao §40.3/§40.4/§48.2 — same verifier pass fills these in
  alongside the (1)-(5) determination above; profile-agnostic set, ONE verifier, not three
  separate agent runs):**
  - **PoC-checklist (§40.3):** are the addresses / call-path in the PoC REAL (not placeholder /
    copy-pasted)? Does the assertion ACTUALLY fail when the bug is reverted — differential against
    a patched build, [[feedback_latent_finding_patched_build_poc]] — rather than an assertion that
    would pass regardless? Does the PoC run against real state, or a mock (a PoC against a mock is
    worth nothing — it proves the mock, not the target)?
  - **severity-economic (§40.4):** who loses, under what conditions, does the loss compound, is
    make-whole possible — a reasoned economic answer, NOT "the model guessed a number." Coordinates
    with `scripts/web3/hypothesis/attack_ev_estimate.py`'s net-profit checklist (`REQUIRED_COMPONENTS`:
    flash-fee / gas / slippage-in / exit-liquidity / MEV-backrun / opp-cost) — cite/run that script,
    do NOT re-derive its formula here.
  - **`undup_origin` (§48.2):** mandatory verifier output field — what source produced this finding
    that a crowd of other hunters wouldn't have had? Same vocabulary as the `undup_origin` column in
    `system_model.md`'s D-NN table (composition-seam / docs-runtime-gap / ui-hidden / commodity-cold /
    assumption-gap / negative-space / interrupted-path / third-party-seam / single-boundary-obvious).
    Empty / `{TODO}` / weak (`single-boundary-obvious`) → the finding is likely-dup — see STEP 3.

STEP 2.5 — Verifier applies 4 SEQUENTIAL GATES (pashov judging.md; structured replacement
           for a subjective "is this real + what tier" verdict). A finding must pass ALL
           four IN ORDER; failing a gate resolves it (reject/demote) without checking later gates:

  Gate 1 — ATTACK EXECUTION: does a guard / require / state-update on the path interrupt the
           attack BEFORE harm lands? If a real guard stops it → reject. (A merely *speculative*
           interruption you can't show fires → clears the gate.)
  Gate 2 — REACHABILITY: is the exploited state actually reachable? structurally impossible
           to reach → reject; reachable only by a privileged actor → demote (carry to Gate 3).
  Gate 3 — TRIGGER: can an UNPRIVILEGED actor trigger it? If the trigger requires admin /
           privileged role → REJECT — UNLESS an unprivileged AMPLIFIER is named, one of:
             • race  (admin tx front-runnable / sandwichable into harm)
             • retroactive-sweep  (admin action re-prices in-flight/pending value)
             • asymmetric-formula  (privileged setter feeds a formula users can't symmetrically exit)
             • access-gap  (the "privileged" guard is actually reachable / mis-scoped)
             • flash-loan-capital  (AOE §2.1 — the "unaffordable" capital precondition is borrowed &
               repaid in one tx; net against attacker_capability_baseline.md, not raw "$ too big")
             • MEV-bundle  (AOE §2.1 — atomic private orderflow manufactures the ordering/atomicity
               a naive read assumed only an admin/sequencer could arrange)
             • multi-block  (AOE §2.1 — the state the trigger "needs" is set up across ≥2 controlled
               blocks where the chain model permits it — L1 proposer-luck / short-block chains)
             • Sybil  (AOE §2.1 — the "one privileged/new identity" gate is a proxy an attacker
               manufactures N-fold cheaply via CREATE2 clones + gas)
           Named amplifier → finding survives at the amplifier's (unprivileged) severity. This is
           the `unless` that mirrors submission_checklist `severity_cap.admin-access-required`.
           **AOE symmetry (§2.1/§4):** a `[DE-MINIMIS]`/practicality kill here is not clean until it
           carries `profile-cleared: <ref>` netting the dismissal against the attacker-capability
           profile (the 4 capability-amplifiers above); the completeness-gate holds the exit otherwise.
  Gate 4 — IMPACT: is there material harm to someone other than the attacker? self-harm only
           → reject; dust / sub-threshold loss → demote (see severity_cap.rounding-dust).

  Safe-patterns whitelist (do NOT raise as findings): `unchecked` where overflow is impossible,
  MINIMUM_LIQUIDITY first-deposit, SafeERC20 wrappers, nonReentrant-guarded, two-step admin
  transfer, protocol-favoring rounding. (= shared-rules "do not report" + our auto_invalid.)

  FINDING vs LEAD: a finding with no concrete proof is a LEAD, not a failure — default to LEAD
  over dropping (it's calibration, feeds T6 building blocks), but a LEAD does NOT submit.
  PROVENANCE shortcut (pashov fizz): if the violated property was tagged SHOULD-HOLD at T2 STATE A
  (cited docs / ERC-MUST / closed-form identity), a passing PoC is a confirmed bug by construction —
  the 4 gates assess reachability/impact, NOT "was this intended". An EXPLORATORY violation (no cited
  guarantee) stays a LEAD until a human confirms intended behavior, even post-PoC.

STEP 2.6 — FRESH-RUNTIME RE-PROVISION (kill residual-discovery-state PoCs; standalone, Plan 9 T5b/R6):
  A PoC that passes only because it reuses leftover state from the discovery session is a false
  positive. The verifier MUST re-run the PoC against RE-PROVISIONED runtime state and record the
  result in the verifier-log:
    • EVM / fork — fresh fork at a CURRENT block (NOT the block discovery ran on); reset any cheatcode
      state (deal / store / prank) and re-derive it through the real protocol pipeline.
    • on-chain / burner — fresh burner nonce + allowances re-set from zero (no residual approve() left
      over from the discovery session), [[feedback_verify_current_exploitability]].
    • web2 / dapp — fresh session / token + a NOT-previously-touched object / account (no object the
      discoverer created earlier in the session standing in for a real victim's object).
  Verifier-log MUST record: "re-provisioned <what>; PoC PASS / FAIL on fresh state". FAIL on fresh
  state = KILL — the bug lived in the discovery session's residue, not in the target.

STEP 2.7 — PRECONDITION NEGATIVE-CONTROL MATRIX (falsify each precondition one-at-a-time; Plan 9 T5c):
  For every precondition the finding STATES it needs, the verifier flips it OFF one at a time and
  re-checks — each row is a PASS / FAIL entry in the verifier-log:
    • precondition removed → exploit STILL fires  = the precondition was NOT actually required (the
      finding is broader/stronger than claimed, or the claim is imprecise — reconcile before filing).
    • precondition removed → exploit no longer fires = the precondition is genuinely load-bearing
      (belongs in the report's reachability / likelihood section).
  Then surface UNSTATED-BUT-REQUIRED preconditions: what did the PoC silently rely on that the writeup
  does not name (cheat addresses, pre-funded balances, a specific caller, an oracle value, tx
  ordering)? Each unstated precondition found → add it to the report, or it becomes a triager's KILL.
  Log the full matrix (stated preconditions × PASS / FAIL + the unstated-surfaced list) in the
  verifier-log.

STEP 3 — Compare verdicts (after the 4 gates produce the verifier's tier):
  - Verifier confirms (passed all gates) + severity within ±1 tier of discoverer → PROCEED to T3 / submission
  - Verifier confirms but severity differs by 2+ tiers → DOWNGRADE to verifier's tier
    (verifier saw fresh, less invested in upside)
  - Verifier confirms but `undup_origin` is empty / `{TODO}` / weak (`single-boundary-obvious`) →
    DOWNGRADE to likely-dup (§48.2): do not submit until an adversarial re-read answers "what did
    every other hunter miss that I didn't" with a stronger origin (composition-seam /
    docs-runtime-gap / ui-hidden / commodity-cold / assumption-gap / negative-space /
    interrupted-path / third-party-seam)
  - Verifier identifies silent precondition / fixture cheat / non-exploitable path / gate-1 or gate-3 reject
    → KILL finding, move to {H-NN}/killed_by_verifier.md, do NOT submit
  - Verifier flags partial uncertainty → resolve via a third pass with sharper PoC
    OR park finding (DON'T submit ambiguous)
  - Verifier could only confirm under a NEW angle the discoverer never claimed (P10 salvage) → the
    submitted finding is KILLED; re-file the salvage-angle as a fresh hypothesis for its own DRIVE.
  - Verifier's tier is NOT expressed as an exact platform-rubric classification → not submit-ready;
    map it to the program's own rubric first (P10 stance above).
  - Verifier-log missing a fresh-runtime PASS (STEP 2.6) or the precondition matrix (STEP 2.7) → not
    submit-ready; the finding is incompletely verified regardless of the tier.

STEP 4 — Log discrepancies for calibration:
  - Every discoverer/verifier disagreement → log to
    sessions/_methodology/verifier_calibration.jsonl
  - Long-term: if discoverer is systematically overoptimistic by N tiers, future
    self-calibration can adjust default severity claims downward.
```

**Confidence quantification (pairs with the 4 gates).** After the gates pass, attach a confidence score, not just a tier: start 100, −20 if the attack path is only partially shown (no end-to-end PoC), −15 if it works only in a bounded input range, −10 if it needs a specific reachable state you must separately create. **≥80 → write up + submit; <80 → it's a LEAD, sharpen the PoC or park it, don't spend reputation.** Full rule + the `severity_cap.admin-access-required` `unless`-amplifier list in `sessions/_methodology/submission_checklist.yaml` (`confidence_gates`). Source: pashov judging.md, [[reference_pashov_skills]] block C.

**Verifier rigor add-ons (DarkNavySecurity `adversarial-review` / `verifier-agent`):**
- **V/R/U claim marking.** The verifier marks EVERY factual claim it relies on as `VERIFIED` (checked against source), `REFUTED`, or `UNVERIFIABLE`, and recomputes severity using ONLY `VERIFIED` facts — assumed mitigations and unverified preconditions are excluded, not given the benefit of the doubt. "Trust neither discoverer nor narrative — trust the code." Kills the "there's probably a guard somewhere" hand-wave in both directions.
- **`contested` as a fourth outcome** (besides confirm / kill / sharpen). A finding where a guard demonstrably EXISTS but the verifier cannot prove it fully blocks the path → `contested`, not killed. Park it for the aggressive second pass (Mandate 0.2) as a building block, don't discard — the bypass may surface when chained (T6). Distinct from a clean Gate-1 reject (real guard provably stops it).

**Differential confirmation — the anti-tautology gate (adshao/flounder `confirm`).** A PoC is `confirmed-executable` ONLY if it runs through a real test-runner (forge/cargo/pytest), never an inspection/print command no matter the output. Promote to `confirmed-differential` ONLY when the fix round-trips: (a) the exploit reproduces against the *pristine* source, (b) you apply a minimal candidate fix and the exploit is now BLOCKED, (c) the test otherwise still passes, (d) restore the source. If a PoC "passes" only because it asserts against a mocked verifier / pinned oracle / hand-fed return value — that's a *tautology*, mark it `disputed`, NOT confirmed. This catches the failure mode where the PoC proves its own setup, not the bug. Run it before any Med+ submission whenever the target has a buildable test harness (fork PoC counts).

**Refutation pass — seek the counter-invariant, don't re-confirm the argument (flounder `refutation.ts`).** The standard verifier re-checks the discoverer's argument FOR the bug. The refutation pass is the inverse: a blind subagent (no sight of the original research) re-derives the module's invariants from scratch and actively tries to find one that makes the exploit IMPOSSIBLE. If it surfaces a blocking invariant → kill/downgrade. Single-test findings that survive refutation but lack a differential round-trip → downgrade to `suspected`; differential-confirmed findings that get refuted → `disputed` (execution outranks argument, keep but flag). Frame the subagent prompt as "prove this CANNOT happen," not "check whether it happens."

**Fix-equivalence dedup (flounder `confirm_equivalence`).** When a session has multiple related findings, before writing them up: two findings are the SAME bug iff one minimal fix neutralizes both, in both directions. If so → one report with a composite description, not N reports. Prevents self-inflicted duplicate spam and the rep hit from triagers merging your own findings.

**Why this works:** the verifier has none of the sunk-cost emotion, none of the "I want this to be real" bias. Cold context = honest read. In practice this kills 20-30% of confirmed-looking findings before they reach the platform. Each killed finding is a saved reputation hit per [[feedback-submission-strategy]].

**When to skip:** NEVER for any Med+ finding going to submission. Per [[no-giveup-hunt]] Mandate 0.5: T4 is a hard pre-submission gate, no exceptions. For Low/Info findings the verifier pass is optional but recommended on the first 3-5 findings of a session to calibrate.

**Hard gate:** if verifier kills, downgrades by 2+ tiers, or flags silent precondition — finding does NOT submit. Period. Override by the operator only — never self-override.

**Anti-pattern:** running verifier with shared context ("here's what I found, confirm it"). That just produces an agreement reflex. Verifier MUST be cold. Use the verbatim Step-2 prompt template in this technique — do NOT paraphrase.

---

## Technique 5 — Patch-Diff Hypothesis Seeding

**Problem this solves:** "find a bug in this codebase" is too open-ended. The most exploitable bugs in production protocols live in the delta between the last audit and current mainnet — post-audit drift, hot-fix patches, last-minute parameter changes, recently-merged features that haven't yet seen incident pressure. Mozilla's planned evolution of their Mythos pipeline is exactly this: patch-based scanning instead of file-based scanning. Big Sleep (Google) already starts with commit diff as the hypothesis seed. This produces higher precision AND targets the highest-Crit zone.

Verified pattern from our memory: [[echo-monad-hack-2026]] ($816K) and [[transit-finance-2026-hack]] ($1.88M) were both post-audit drift bugs. Per [[feedback-solana-hunt-reality]] this hunt mode is explicitly preferred for well-audited targets.

**Protocol — runs BEFORE T2 STATE A on targets that have audit history or recent merges:**

```
TRIGGER (apply if ANY true):
  - Target has at least one public audit report (Cantina/Spearbit/Trail-of-Bits/etc.)
  - Target has merges or commits within last 90 days post-audit-date
  - Target is a fork of a well-audited protocol (Compound/Uniswap/Curve fork class)

STEP 1 — Establish diff baseline:
  - audit_commit = git commit hash at the date of last public audit
    (find via audit report cover page, or git log --before=<audit-date>)
  - head_commit = current main/master HEAD
  - If multiple audits: use the most recent one's commit
  - Save to sessions/{target}/diff_baseline.md with the chosen commits + rationale

STEP 2 — Extract the diff:
  git diff {audit_commit}..{head_commit} -- '*.sol' '*.fc' '*.rs' '*.move' \
      > sessions/{target}/post_audit_drift.diff

  Filter to security-relevant files only (apply T1 attack surface rubric):
  - Drop test/, mock/, script/, deploy/ changes
  - Drop pure comment/whitespace/docstring changes
  - Keep: function-body changes, signature changes, access-control changes,
    new external entry points, constant reassignments (param changes)

STEP 3 — Seed-hypothesize from each diff hunk:
  For each surviving hunk, draft a hypothesis using this template:

    "Pre-audit, code at {file}:{old-line} did X (auditor signed off on this).
     Post-audit, code at {file}:{new-line} does Y.
     If Y silently breaks invariant Z that the auditor relied on, then attacker
     can {observable effect}."

  Common drift classes to look for explicitly:
  - Auditor's recommended fix INCOMPLETE (partial patch, edge case missed)
  - New function added (not audited at all) calls into audited surface
  - Parameter constant changed (e.g. slippage threshold, fee, oracle decimal)
  - Access control loosened ("just for testnet" comment that survived to mainnet)
  - State variable type/size changed (storage layout drift, upgrade-broke)
  - External call target changed (oracle replaced, token whitelist expanded)

STEP 4 — Feed seeded hypotheses into T2 STATE A:
  Each diff-derived hypothesis enters Technique 2 as a STATE A formulation.
  Then proceeds B → C → D normally.

  Priority order in T2 queue: diff-seeded hypotheses go FIRST (highest expected
  Crit ROI), then generative hypotheses from cold-read.
```

**Applicability matrix:**

| Target type | Patch-diff seeding ROI |
|---|---|
| Smart contracts post-audit (Solidity, Move, Anchor, FunC/Tolk) | **Very High** — primary Crit zone |
| TON Core C++ recent merges (Simplex, recent tolk versions) | High — narrow surface but real |
| Forks of well-known protocols (e.g. yet-another-Uniswap-v3) | Very High — known baseline + drift |
| Fresh deploys (no audit yet) | **N/A** — skip, fall back to generative T2 |
| dApp frontend (minified bundles, no clean diff) | Low — skip unless OSS contract repo available |
| Web2 monolith with no audit history | Low — skip |

**When NOT to use:** un-audited fresh deploys (no baseline = no drift). Generative T2 is the right tool there.

**Anti-pattern:** treating diff-derived hypotheses as automatically real. They're STATE A seeds; they still need to survive STATE B→C→D and the T4 verifier pass before submission.

### Addendum — Fix-verification lenses (is the patch real?)

T5 above seeds hypotheses *from* a diff. This addendum is the dual: when a diff is a **fix**
(auditor's rec, our prior finding's patch, or a published remediation), don't assume it closed
the bug — a fix is itself a code change that can be incomplete, wrong, or bypassable. Apply three
lenses to every fix hunk (source: ugwst-sec `methodology/fix-verification-patterns.md`):

1. **Incomplete fix** — the patch added a check but only on ONE path/sibling (added `require` to
   `deposit` but not `mint`); or narrowed a range without covering the boundary. → run Cat 17.1
   sibling-enumeration on the fix.
2. **Fix creates a new bug** — the patch fixes X but its new code introduces Y (e.g. a new
   external call → reentrancy; a new cap → DoS; a clamp → rounding). Read the *added* lines as
   fresh attack surface, not as proven-safe.
3. **Fix bypassed by edge-case** — the fix holds for the demoed exploit but a parameter twist
   evades it (TWAP window set to **1 second** instead of 30 min "satisfies" a TWAP rec but is still
   spot-manipulable; a `!= address(0)` check bypassed by a contract that becomes 0-code later).

**Seeding priority #1 — the patch written IN RESPONSE to a security report.** Code added to fix a
known bug is the single highest-yield diff to re-attack: it's fresh, written under time pressure, and
NOT in the original audit scope. Canonical case: kankodu reported Euler's first-deposit bug ($50K);
Euler's fix added `donateToReserves()`; that very function — seeding assets without minting shares —
became the unbacked-collateral leg of the **$197M** 2023 hack ([[reference_kankodu_findings]], Cat 1.6/8.5).
So when triaging diffs, rank "remediation of a prior finding" ABOVE routine feature commits, and run all
three lenses on it. (kankodu's own lens: *"a fix for a reported bug is new attack surface, not a full stop."*)

This is why **audited ≠ fixed** ([[reference_grego_ai]] UniV4: OpenZeppelin flagged the path, the
"fix" survived and the bug stayed). Especially load this when hunting deployed code where a HEAD
fix may not be deployed, or a re-audit window opened ([[feedback_model_release_reaudit_window]]).

---

## Technique 6 — Composite Hypothesis Generation (2-3-vector chains)

**Problem this solves:** auditors and self-hunters generate single-vector hypotheses ("function X has bug Y") and miss compositions. The expensive bugs of the last 3 years are chains: Echo Monad ($816K) was admin-key + unconstrained-mint + fake-collateral; Transit Finance ($1.88M) was ghost-contract + delegated-call + token-approval-leftover. T3 (chaining post-hoc) is reactive — T6 is proactive: chain candidates BEFORE confirming individual vectors.

Per [[chained-hypothesis-hunt]] memory and Mandate 0.4. Standing instruction (2026-05-28): "apply more hypotheses, especially two-to-three-party ones, where one vulnerability can lead to another, and that one to yet another and/or they are all interrelated".

**Protocol — runs during T2 STATE A (hypothesis formulation) and again after every D-Kill:**

### Step 1 — Enumerate building blocks

After T1 file prioritization, list every observed "weak signal" in `sessions/{target}/building_blocks.md`:

- Allowance leftovers, partial state changes, asymmetric guards, unchecked returns
- Mock-state assumptions, two-phase state-delta patterns
- Admin powers that are not strictly necessary
- External-call paths where caller assumptions can drift
- Math edge cases (rounding, overflow, decimal)
- Time-based assumptions (cooldowns, deadlines, accrual)
- **Optimization/guard assumptions** — each gas-opt / cache / early-return as the sentence "this bets that {condition}"; record who controls the breaking variable (T1 assumption-enumeration lens)
- **Infra/off-chain layer signals** — node-config defaults (`max_body_bytes`, RPC/gossip caps, gas limits), off-chain service behavior, transport limits, punishment/slashing handlers (T6 actor-pipeline mapping)

Each block alone may be Low or even Info — do NOT discard.

### Step 2 — Combinatorial chain generation

**Cross-thread synthesis first (Sherlock's core move — see T0).** Before the affinity templates below, deliberately pair the DISTANT, non-obvious building blocks: two clues from different files / subsystems / bug classes that look unrelated. Ask not only "does A enable B?" but "what NEW attack emerges if these two — which nobody connected — are true at once?" Most affinity pairs are already in auditors' mental models; the novel Critical lives in the pair that crosses subsystems. If a cross-thread pair yields an attack that fits NO taxonomy class, that is the highest-priority candidate (potential novel class), not a reason to doubt it.

**Orchestration — ONE reasoner over the WHOLE pool (do NOT partition it like scout-fanout).** Cross-thread synthesis is a whole-pool operation: the pair you are hunting spans DISTANT subsystems, so a single reasoner must hold ALL building blocks at once. If you delegate T6 to subagents, exactly ONE agent receives the ENTIRE pool. Do NOT spawn one agent per subsystem (agent-A = EP-side, agent-B = rate-side) the way scout-fanout partitions the surface — that is the OPPOSITE reflex: partition-by-subsystem splits the cross-pair (the EP-side × rate-side clue lives BETWEEN the two agents), so neither can see it and the composite is destroyed by construction. Scout-fanout PARTITIONS to explore-wide (find NEW places, blind workers); T6-synthesis UNIFIES to compose (chain KNOWN blocks, one reasoner) — same tool (subagents), opposite topology. The only valid multi-agent T6 shapes: (a) `divergence_fanout` reduce-phase = one senior-tier agent over the WHOLE batch; (b) one cold cross-thread agent handed the full `building_blocks.md`. Want redundancy? Run the SAME whole-pool synthesis N times with different seeds — never split the pool. (enzymefinance 2026-08-19: hunter first fragmented T6 into A74 EP-side × A75 rate-side non-overlapping agents → the cross-pair was un-findable; corrected to one agent holding all latents together.)

**Depth-ceiling traversal (the VERTICAL companion to cross-thread — GregoAI thesis, [[reference_grego_ai]]).** Cross-thread is horizontal (far-apart subsystems); depth-ceiling is vertical: human auditors hit a cognitive wall at ~4-5 levels of interacting systems, and the criticals that survive multiple audits live BELOW that wall. So pick ONE building block and trace its chain DOWNWARD layer by layer — `entry-call → state-mutation → external-call → callee-hook → accounting-settle → re-entry/next-block read` — counting depth as you go. The bug usually sits at the SEAM between layer 5 and layer 6, not in any single function. Operational rule: **a "looks clean" verdict reached at depth ≤3 is not a verdict — it's "I stopped digging early."** Don't conclude a path is safe until you've either traced it ≥5 interaction levels or hit a hard boundary (trust gate / value sink) that terminates the chain. Build an explicit interaction-depth map for the top-3 prioritized entrypoints; the deepest unexplored layer is a mandatory hypothesis (ties to T1 coverage gap-map and the Orchard below-ceiling lesson). This is GregoAI's "Deep Invariant Analysis": map every module → every interaction → trace execution paths for an invariant that holds at the surface but breaks ≥5 layers down under specific conditions.

**Actor-pipeline boundary mapping (the audit boundary ≠ the contract boundary).** The richest cross-thread pairs cross LAYERS, not just files — and most hunters never leave the contract layer, so that seam is unaudited. For each privileged actor (validator / sequencer / relayer / keeper / oracle pusher / off-chain signer), map their FULL operational pipeline end-to-end: `observe → compute → serialize → transmit (transport) → on-chain tally → punishment`. At EVERY layer ask: (a) what default/limit lives here (node config, RPC `max_body_bytes`, gossip cap, gas/compute cap)? (b) what is attacker-inflatable in size/timing? (c) what happens on failure — graceful degrade or silent hard-fail? (d) does the punishment side have a systemic-failure / quorum-survival guard? Then compose a clue from one layer with a clue from another. Axelar 2026 ($1B halt, $50K): an *infra-config* clue (Tendermint `max_body_bytes=1MB` → attacker-inflated vote payload fails) × a *contract* clue (no quorum guard before punishing missed votes) → mass validator removal → halt. Neither layer alone is the bug; the seam is. Building blocks from node config / off-chain services are first-class — add them to `building_blocks.md` alongside contract signals. See `checklists/specialized/cross_layer_resource_limit.md`, [[reference_bounty_case_studies]].

**Defense-by-actor-competition collapse (single-actor lens).** When a protocol's real safety comes from MANY actors competing/agreeing (solvers tightening a fill, validators reaching quorum, relayers racing, keepers undercutting), ask: *what executes if exactly ONE actor participates?* The nominal guard (a weak minOut floor, a low quorum, a default timeout) is normally masked by competition; with one actor it becomes the SOLE constraint and the disaster it permits actually fires. Aave×CoW 2026 ($50M): solver competition normally forces good routes — one solver included the order, so the weak signed floor was the only thing left and it cleared via a toy pool. Mirror of Axelar quorum-survival (Cat 18.6). Add the "single participant" scenario as an explicit building block for every multi-actor mechanism. [[reference_ehsan_aave_cow]]

**Gap-lens seam vocabulary (systematic cross-thread, pashov gap-hunters).** Cross-thread synthesis above is the mindset; the **three gap-lenses** give it a checklist of named seams to run mechanically. See `hypothesis_taxonomy.md` → "Gap-Hunter Lenses": **numerical-gap** (precision×invariant / boundary×precision / boundary×invariant), **trust-gap** (access×economics / economics×asymmetry / access×asymmetry), **flow-gap** (execution×periphery / periphery×first-principles / execution×first-principles). For each found-or-suspected single-lens item, walk its three seams; a finding that needs two lenses to even state = composite candidate. Same discipline as below: if it's expressible with ONE lens, it's a single-category job, not a chain.

Apply the chain templates:

**2-vector chains (try systematically — pick any two building blocks, ask "does A enable B?"):**

| Pattern | Combine | Critical-tier outcome |
|---|---|---|
| Capability + Reach | "Bug A grants attacker capability X" + "Function B trusts that X is impossible" | Drain / privilege escalation |
| State + Trigger | "State X can be set by attacker" + "Function Y reads X without validation" | Forced behavior |
| Drift + Guard | "Mock test passes, prod state differs" + "Guard relies on test-state invariant" | Silent DoS / drain |
| Asymmetry + Composition | "Sibling A has guard, sibling B doesn't" + "Caller composes A + B" | Bypass via B |
| Phase + Accounting | "Phase 1 changes state X" + "Phase 2 reads X' (drifted)" | Accounting drift |

**3-vector chains (rare but Critical):**

| Pattern | Building blocks | Real example |
|---|---|---|
| Admin + Mint + Collateral | Compromised admin key → arbitrary mint → fake collateral on lending | Echo Monad $816K |
| Ghost + Delegate + Approval | Contract that looks dead → delegatecall to attacker → reuse leftover approvals | Transit Finance $1.88M |
| Oracle + Liquidation + Flash | Oracle manipulation → trigger liquidation cascade → flash-loaned to amplify | Multiple 2022-2024 protocols |
| Phase1 + Phase2 + Phase3 | Init-phase weak → Mid-phase relies on init → Finalize-phase rewards based on mid | Various staking/restaking |

### Step 3 — Sibling-class enumeration (mini-chain class)

For every finding (refuted, plausible, or confirmed) ask: **"If this exists here, does it exist in any sibling contract?"**

- Audit fixed a bug in `IntegrationHookA.sol` → grep for `IntegrationHookB.sol` ... `Z.sol` and verify each
- Bug class `mock-vs-prod` found in one place → audit every contract whose tests use mock state for the same primitive
- Bug class `two-phase usedShares=0` → audit every two-phase pattern
- This is where audit remediation gaps live — auditors fix instance, miss class.

### Step 4 — Triage composite candidates into T2 queue

Each composite chain → write up as a single hypothesis in T2 STATE A format. Priority order in queue:
1. T5 patch-diff seeded
2. T6 confirmed-block × confirmed-block chains
3. T6 confirmed-block × suspected-block chains
4. Single-vector hypotheses
5. T6 suspected × suspected (lowest priority)

### Step 5 — Re-run on every D-Kill

When a single-vector hypothesis dies (T2 STATE D-Kill), don't discard. Add the refuted vector as a building block (it told you something about the contract's invariants). Re-run Step 2 — the dead hypothesis may chain with another.

**Anti-pattern:** stretching unrelated bugs into a fake "chain" for severity inflation. Reviewers see through this and it costs reputation per [[feedback-check-project-tests]]. Real chain = the second step is impossible WITHOUT the first.

**When to skip:** never. Composite generation is cheap (mental exercise + grep). Skipping it = missing the highest-payout vectors.

---

## Technique 7 — Canonical Hypothesis Tracking (per-hunt artifact)

**Problem this solves:** without a live registry of hypotheses, the same dead-ends get re-explored, refuted vectors get forgotten (so T6 building blocks vanish), and the hunt's audit trail for severity defense disappears. The artifact also doubles as the file the verifier subagent reads to cold-check the session.

**Protocol — create at session start, update on every state change:**

### Step 1 — Create `sessions/{target}/hypotheses.md` at session start

**Canonical schema lives in ONE file:** [`sessions/_methodology/hypotheses_template.md`](../sessions/_methodology/hypotheses_template.md).
At hunt ENTRY, **`cp` it** to `sessions/{target}/hypotheses.md` and fill placeholders — do NOT improvise the
schema (it's used by tooling for calibration-log generation, and the template carries the LEDGER RULES
block: every hypothesis MUST carry a status, processed ones MOVE to their section, pool is unbounded).
If the schema needs changing, edit the template FILE (single source of truth — this T7 points to it, does
not duplicate it). The template's sections: Loop State (resumable spine) · Building Blocks · Active
Hypotheses (live only) · Refuted (`[KILLED]` w/ mandatory falsifier + `[CONTESTED]`) · Parked · Composite
Chains · Verifier Log.

### Step 2 — Update live

- **A-formulating** added → new H-{NN} entry, fields filled to extent known
- **B-sandbox-setup** → update state, note fork block / fixture choices
- **C-PoC-attempting** → log iteration count in entry (don't bloat — point to `hypothesis/{H-NN}/iterations.md`)
- **D-PoC confirmed** → state=D-PoC, trigger T4 verifier pass, then T3 chain check
- **D-Killed** → MOVE entry to "Refuted" section, fill `Residual signal` (this is the T6 building block)
- **D-Parked** → MOVE entry to "Parked" section

### Step 3 — Use as second-pass input (Mandate 0.2)

When a first-pass concludes "no findings", the SECOND pass starts by:
1. Reading `hypotheses.md` Refuted section — every killed hypothesis is a T6 building block
2. Running T6 Step 2 (chain generation) across every Refuted + Active combination
3. New composite candidates added as fresh H-{NN} entries

### Step 4 — Submission prerequisite

Before any submission, hypothesis MUST be in state D-PoC AND have a verifier log entry AND have passed T3 chain check. If any of these missing → not ready for submission, regardless of how confident the finding feels.

**Anti-pattern:** improvising hypothesis files per-session ("for this one I'll just keep notes in a notepad"). The template IS the discipline. Skipping fields = skipping the discipline.

---

## Technique 8 — Differential / Involution Fuzzing (cross-client divergence)

**Problem this solves:** the entire consensus-layer / cross-client bug class is invisible to single-implementation review. An auditor reads ONE parser, concludes "correct per spec", and never sees that a SECOND implementation of the same format disagrees on an edge byte — which is a chain split. Source: asymmetric.re "Finding Fractures" (JSON `0x0B` divergence between `json-rust` and `serde_json`) + "Ghost in the Block" (SSZ ghost regions, Prysm vs Lighthouse, block-production halt). Maps to taxonomy **Cat 18**.

**When to apply (TRIGGER — any true):**
- Target is a multi-client L1/L2 (Ethereum CL clients, geth/reth, any chain with 2+ clients).
- One client imports two libraries that parse the same wire format (SSZ, RLP, borsh, BCS, JSON, protobuf, TL-B).
- Target has a custom serialization/deserialization path on attacker-reachable input (P2P messages, blocks, txs).
- **Re-implementation of a known standard/library/fork** — alt-EVM engine (Cat 18.13), alt-BTC parser (Cat 27), inlined/forked `SafeERC20` "for gas" (Cat 1.10), or a fork of an audited protocol. **Meta-axis:** diff the re-implementation against its canonical reference — this is the single lens behind 5/7 of the Immunefi-backtest crits (a re-implemented standard almost always diverges somewhere).

**The two properties (break either → consensus-divergence finding):**
1. **Differential:** `accept_A(x) == accept_B(x)`, and equal canonical form when both accept. One accepts, the other rejects = fork.
2. **Involution / injective:** `deser(ser(x)) == x`; `ser(a)==ser(b) => a==b`. A lenient decoder that accepts a byte stream and re-encodes it differently (ghost region, alternate offsets) breaks involution while keeping `hash_tree_root` (and the signature) valid.

**Protocol:**
```
STEP 1 — Enumerate every (de)serialization impl per wire format in scope.
STEP 2 — Find where 2+ impls parse the SAME format (cross-client, or two crates in one client).
STEP 3 — Build the differential harness:
         - Use scripts/web3/fuzz_harness/differential_harness.rs.template (LibAFL).
         - Fill parse_a / parse_b (each: Ok(canonical) on accept, Err on reject).
         - Reproduce a KNOWN divergence first (json-rust 0x0B) to prove harness+toolchain (M2 of
           learning_paths/differential_fuzzing.md). Never trust a "no findings" from an unproven harness.
STEP 4 — Seed ./corpus from fuzz_harness/corpus_seeds.md (0x0B, negatives, empty, max-nesting,
         ghost-offset, trailing bytes). Coverage-guided mutation does the rest.
STEP 5 — Any saved crash = an input where A and B disagree (or A breaks round-trip).
         Confirm on a multi-node devnet (one client accepts the block/msg, the other rejects → halt).
```

**Static pre-fuzz signal (cheap first pass):** SSZ/RLP/borsh decoders validating relative offsets only (no `sum(variable_lengths) == total_variable_section_size`) → ghost regions possible. Same repo importing two parsers of one format → guaranteed-worth-fuzzing.

**Checklist:** `scripts/web3/checklists/hypothesis/serialization_divergence.md`. **Path:** `sessions/_methodology/learning_paths/differential_fuzzing.md`. **Targets queue:** `sessions/_methodology/live_targets_consensus.md`.

**Why this is NOT Trident/invariant fuzzing:** Trident (and property fuzzing) breaks an invariant in ONE implementation. T8 compares TWO implementations (or one impl against its own round-trip). Different tool, different bug class.

**Anti-pattern:** running the harness without first reproducing a known divergence — you can't distinguish "format is sound" from "my harness is broken".

### T8-B — Own-conformance-test differential + rare-opcode instrumentation (differential oracle = your own known-good tests, not a second parser)

Source: Saurik / Optimism ($2M OVM_ETH duplication). Use on a new/forked chain or alt-EVM engine (Cat 18.13) where no second live implementation is handy but a **canonical reference behavior** exists.
```
STEP 1 — Differential via YOUR tests: run your battle-tested unit/integration suite (that passes on
         canonical chains) against the new/forked chain. Any divergence in result (balances, state_root,
         event set) = a seed anomaly. Your known-good tests ARE the "second implementation".
STEP 2 — Instrument rare/high-value opcodes/paths: log EVERY SELFDESTRUCT / CREATE2 / DELEGATECALL /
         precompile-call. Rare opcodes = a narrow search space where custom accounting most likely diverges.
STEP 3 — On-chain forensic trigger hunt: search mainnet/testnet history for a real tx that already
         triggered the anomaly. A real trigger proves reachability AND gives an exploit template
         (Saurik found the one user who did it on Christmas Eve and hadn't realized it was exploitable).
STEP 4 — Safe confirm via eth_call state-override BEFORE any disclosure — prove the exploit without
         moving funds (ties to immunefi_poc_standard.md fork-preferred).
```
**When:** alt-EVM / forked-client / new-chain target (Cat 18.13) with a canonical reference but no second live client to diff against. Complements T8 (two parsers) — here the two "implementations" are {new chain} vs {your conformance expectation}. Companion mental-model bullet in `sessions/_methodology/hunter_mental_models.md`.

---

## Technique 9 — Cold Restart (anchor-break after a hopeless impasse)

**Problem this solves:** after a long hunt my context fills with a mental model of "where the bug is" — and that same model blinds me. A "hopeless dead end" is usually not "no bugs exist" but "I'm trapped in one interpretation and can't see past it" (anchoring / tunnel-vision / sunk-cost). The ordinary second-pass (Mandate 0.2) says "dig new angles without giving up" — T9 is the *deeper, last* tier: when even the second-pass is exhausted, **reset the accumulated frame** through a fresh context. Distinct from second-pass (that = more angles in MY head; T9 = a genuinely fresh head). Source: the operator's design, validated against samczsun fresh-eyes-on-old-code + [[feedback_model_release_reaudit_window]] (a fresh reader sees what the anchored one systematically missed).

**Entry gate (ALL THREE true — proves the impasse is real, not fatigue):**
1. Coverage gap-map passed — every score-4/5 file actually READ, not just classified (T1).
2. Ordinary second-pass with new angles came up empty.
3. T6 composite recombinations of refuted hypotheses came up empty.

Only with all three = a true impasse → Cold Restart allowed. Without them it's premature surrender (Mandate 0.2: first-pass "nothing" is systematically premature).

**Manual override:** if the operator *explicitly and clearly* writes "cold restart", run it immediately — even before the gate, even early. Only on a clear written instruction, not implied.

**After 3 dry axes — surface, then CONTINUE (NOT park).** Under the Hunt-Loop axiom (bugs are
everywhere; the loop's only exit is a T4-confirmed High/Critical bug — Medium/Low are banked in
`## Banked Findings` & batch-submitted at hunt-end / on operator request, but do NOT end the loop), 3 dry Cold-Restart axes are NOT a
park/abort signal. When axes 1/2/3 come back empty: **surface a status to the operator** (gap-map proof +
the dry log of axes tried) and **CONTINUE on axis 4** (a new orthogonal axis). The loop never
self-exits on exhaustion. The only non-success way out is the operator explicitly writing "we're leaving" — their
prerogative, NOT encoded as methodology (the completeness-gate hook recognizes it via RELEASE words).
Park / transfer-candidate as a *loop exit* does not exist; a refuted hypothesis still becomes a
cross-target transfer-candidate per [[feedback_protocol_family_bug_transfer]], but that's a note, not a leave.

**Mechanism (cold subagent — NOT self-reset, because I am physically anchored by my own context):**
```
STEP 0 — Anchoring audit (I do this first): "what assumption did I hold the ENTIRE hunt as
         given, never once questioned because it felt obvious?" That unquestioned premise is the
         most likely blind spot — use it to aim the new axis.
STEP 1 — I ASSIGN the new axis (the subagent in a clean context doesn't know what's been tried).
         The axis must be structurally different, not a reworded old one. Examples:
           by-file pass   -> walk-backward from value-transfer (Mudit)
           cross-thread (horizontal, distant subsystems) -> depth-ceiling (vertical, one chain ≥5 layers)
           switch the taxonomy categories swept
           builder->breaker switch / external-dependency pass
STEP 2 — Spawn a cold subagent with a DRY digest (not my narrative): (a) code facts — what each
         component does, what's been read; (b) refuted-hypotheses list, marked "DO NOT repeat
         verbatim; MAY recombine as building blocks"; (c) the new axis.
STEP 3 — Subagent builds ORTHOGONAL hypotheses on the new axis + does first-pass kill/keep triage,
         and returns ONLY the selected LIVE hypotheses with a one-line "why still alive" each.
         (It must NOT dump raw ideas — raw ideas re-anchor me as I filter them with the old frame.)
STEP 4 — I run C->D (PoC) on the live hypotheses, using my deep code knowledge — my old anchor is
         now overwritten by the subagent's new frame. Exception: a fully self-contained hypothesis
         may be delegated to a separate agent for its PoC too.
```

**🔴 White-hat guardrail on any attacker-lens / pre-mortem cold subagent (AOE §5.2 — applies HERE and to the Scout Fan-Out pre-mortem scout, B5).** A cold agent told "steal the maximum from this live DeFi system" will happily model "5000 Sybil / spam the mempool / flood the relayer" = §0-NEVER. So such an agent's **system-prompt MUST carry:** (a) read-only tools only; (b) §0-NEVER **verbatim** (incl. the Mandate 0.11 market-manipulation / live-state-mutation additions); (c) "model ONLY from public/static data — NO touching any live system"; (d) output tagged **`modeled-not-executed`**. Pre-mortem runs in BOTH existing forms — a read-only scout in the Scout Fan-Out (start) and a T9 axis — prompt-only, no new mechanism.

**Dual accounting of the impasse (the core trick — separate MOOD from DATA):**
- **Mood — forget it.** Operate as if the dead end never happened. Drop the "it's clean / I'm tired / nothing here" frame — that frame is the poison that makes you quit early. Start the restart fresh-spirited.
- **Data — keep it.** In `hypotheses.md` log the dry fact ("pass N, axis = <X>, impasse, H.. refuted"); after the hunt, in `calibration_log` note "what blinded pass N". The next restart reads this to know which axis NOT to repeat, and I learn from the pattern. Boxer forgets the lost round (fresh for the next), the coach records what failed (data for review) — same person, two functions.

**Where it runs:** `/deephunt` only (it's the High/Critical deep mode); at J9 when COMPLETENESS-GATE + gap-map pass yet 0 valid findings, OR on the operator's manual override at any point. Highest tier of `sessions/_methodology/stop_signals.md` — a continuation mechanism, not an exit (park does not exist under the Hunt-Loop axiom).

**Anti-pattern:** "cosmetic restart" — rephrasing the old hypotheses and arriving at the same place via a different route. The forbidden-verbatim rule alone does NOT prevent this; the *axis change* (STEP 1) + *cold context* (STEP 2) are what force a real shift. A restart on the same axis is not a restart.

---

## Technique 10 — Independent Model First (model BEFORE code → divergence)

**One paragraph.** Build a model of the system **before reading the implementation** and look not for a "weird line" but for a
**place where an invariant is not enforced**. The bug lives in the divergence between model and code. Public precedent — Zcash Orchard:
a researcher took the halo2 book as the reference model of the primitive and checked it against the implementation; `assign_advice()`
without `copy_advice()` is the **absence** of a constraint, i.e. something that is NOT in the code. 4 years under tier-1
audits. The full operational checklist: `sessions/_methodology/independent_model_first.md`.

**Beats:** (1) corpus without code → (2) `I-NN` as formulas → (3) read the code and mark enforcement →
(4) rank `D-NN` → (5) feedback into the model.

**Five enforcement statuses** (`ENFORCED` / `ENFORCED-PARTIAL` / `IMPLICIT` / `ABSENT` / `SUBSTITUTED`):

- 🔴 `ENFORCED-PARTIAL` — **the main class**, not decoration: real-world bugs are rarely fully `ABSENT` — the check
  exists, but not on every path. A three-status scheme would miss the whole class.
- 🔴 `SUBSTITUTED` — **the canonical mechanism is replaced by a home-grown one**: the check is in place, the lifecycle
  is visually correct, but it stands on a different foundation. Earned by the phase-0 blind test (2026-07-27);
  mock-vs-prod divergence is exactly this class. Priority **higher** than a plain `ABSENT`.

**Three operators** (without them the statuses are set on faith):

1. **"On all paths?"** — for each `ENFORCED`, list the paths EXPLICITLY (if branches, sibling functions,
   batch-vs-single, mint-vs-burn, ETH-vs-token).
2. 🔴 **"Is the mechanism canonical?"** — look not at the calling code (it looks canonical), but at
   **what backs the data source**. Check against `fingerprint:` in `methodology/invariant_library.md`:
   functionality present + fingerprint absent = `SUBSTITUTED`. The more canonical a mechanism is in the spec, the more readily
   it is taken for granted — by both the model and the auditor. That is where audit-surviving criticals live.
3. 🔴 **`pred:` ↔ fact.** `pred:` (the expected status) is set BEFORE the code. `pred: ENFORCED` → fact
   `ABSENT`/`SUBSTITUTED` = **the highest rank**: a place that EVERYONE considers closed, un-dup by construction.
   The reverse (`pred: ABSENT` → fact `ENFORCED`) = my domain model is wrong → fix the model.

**Beat-4 ranker:** `value-weight × path-count × (tests==0) × convergence ÷ crowd-heat penalty`.
**Convergence** of several independent `I-NN` on one `component:` is a pointer to the place stronger than any
single status. **crowd-heat is a queue, not a filter** (`cold` first, `hot` mandatorily later).

🔴 **Specificity limit: ≤12 `I-NN`, no more than half non-`ENFORCED`.** A blind stage without a limit
produces a shotgun (in phase 0 — 11 of 13 and 15 of 19 were flagged risky). The excess → `## Long Tail`,
not into the trash. 🔴 **The blind stage runs on the SENIOR model**, not on the scout tier.

**Test-Inversion** (fills `## Missing Negatives`): from each written test derive the
unwritten negative along the axes **repeat · order · actor change · boundary value · interrupted path**.
The set is mechanically enumerable and maps one-to-one onto the path list for operator 1. A bug can
sit INSIDE a project's own test.

**T10-B — Family Invariant Diff.** A fork / family member → don't build the model from scratch, **diff the guards
against the reference**. Difference from `protocol_family_bug_transfer`: that one transfers a FINDING (post factum), T10-B
transfers an INVARIANT — it works BEFORE a finding. **🔗 A8 engine (Wave 1 2026-08-08):** mechanized via
`differential_observation.py` — `identify_parent(fingerprints, code)` recognizes the canonical parent
of a fork by the machine fingerprint from `invariant_library.md` (the Machine Fingerprints bank), then
`family_fork_diff(parent_ctx, fork_ctx, target)` = `differential(canonical parent, fork)` through
`ContractDriver` → the delta = where the fork broke the canonical invariant = the bug surface. A triple intersection of
differential × T10-B × invariant_library; it hits our bread and butter (most of DeFi is forks, the bug is in the DELTA from
the reference, not in the copied audited code).

**Anti-anchor:** the model is filled in by a cold subagent from the corpus without access to the implementation; the digging is done by the main
instance. The same technique that gives T4 its strength, but applied at the INPUT.

**When NOT to apply:** a small single contract (<~300 LOC) · `/dapphunt` front end and web2 · a re-visit by
`wave_delta` (the model is extended, not built). → `MODEL: N/A — <reason>` in Loop State.

## Technique 11 — Harness as Generator (a fuzzer as a generator, not as a verifier)

Today fizz/Echidna/Medusa/Trident/fork-PoC are switched on **when a hypothesis already exists** — to
confirm it. An invariant fuzzer that is given the `I-NN` from T13 and let loose finds a **call
sequence** that reading can never reach in principle — and that is exactly where un-dup lives, because the crowd reads and does not
run.

**Protocol:** take the `I-NN` from `system_model.md` (that is why T10 goes first) → encode as a property
(fizz/Echidna/Medusa · Trident · proptest/quickcheck · differential T8) → run **BEFORE a
hypothesis appears** → the found sequence = a `D-NN` of machine origin → into SELECT.

**Anti-tautology (mandatory):** the invariant is taken from the independent model, NOT from the code. An invariant copied from the
implementation makes the fuzzer prove that the code does what it does.

**The trigger is not taste but a detector (a harness is expensive — hours).** The "take/skip" decision is made by the system
ITSELF at the `J-M` phase (right after the T10 model — T11 consumes its `I-NN`), by running
`scripts/_methodology/t11_applicable.py <target_dir>` (not a hook — a phase check inside the skill). Three
objective conditions, all YES → APPLICABLE:
1. **BUILD** — the codebase compiles (`foundry.toml`/`hardhat`/`Anchor.toml`/`Cargo+proptest`) → the script
   picks an engine (Foundry-invariant/Echidna/Medusa · Trident · proptest);
2. **STATEFUL** — invariant-heavy value accounting (≥3 signals: balances/shares/reserves/supply/
   deposit/withdraw…) — there is something to preserve;
3. **MOVEMENT** — ≥1 `I-NN` in `system_model.md` that cannot be checked by reading (multi-step / order-dependent /
   cumulative) — exactly what the fuzzer generates.

Verdicts (exit code): **APPLICABLE** (0) → build a harness from the order-dependent `I-NN`, run it BEFORE a hypothesis;
**MAYBE** (2) → BUILD+STATEFUL present, but the model has no order invariant → finish T10 and re-check (NOT a
skip — this is T11's home); **SKIP** (3) → no BUILD (web2/front end/docs) OR not STATEFUL (a stateless parser →
that is **T8 differential**, not T11). Detector test: `t11_applicable_replay.py` (14/14).

## Technique 12 — Predictive Boundary Crossing (a layer counts only with a prediction)

**The problem.** We have a depth METRIC and no depth METHOD: `call→state→external→hook→accounting` inside
a single file = "5/5", the gate is satisfied, there is no understanding of the system. That is Goodhart on our own gate.

**A layer counts only if BOTH conditions are met:** (1) a **representation boundary** is crossed;
(2) a **prediction is made BEFORE the crossing and checked AFTER**. Five reads in a row in one file = ONE
layer. A crossing without a prediction = ZERO layers (that is movement, not understanding).

**Boundary types (each leaves an artifact):** static→runtime (run log) · module A→module B (path +
commit) · spec→implementation (corpus quote + `file:line`) · deploy A→deploy B (two addresses + diff) ·
code→live on-chain state (`eth_call`/RPC output).

**Four mandatory layer fields:**
```
L3  boundary:  static → runtime (fork run)
    predicted: redeem() will return 99 ETH, fees will grow by 1e18
    observed:  revert ERC721IncorrectOwner  ← forge log, line 214
    fan-in:    fees ← redeem() :179 · redeemNative() :190 · withdrawFees() :261  (3 writers, 1 on the thread)
```

🔴 **`predicted ≠ observed` — a GENERATOR, not an accounting error:** (a) the system behaves unexpectedly →
immediately a new top-priority `D-NN`; (b) I didn't understand the system → dig THIS SAME layer, the counter does NOT
grow; (c) the model was wrong → fix `system_model.md`. A miss must not be swallowed silently.

🔴 **`fan-in` (who ELSE touches this state).** Our depth-ceiling is strictly vertical along ONE thread,
but an auditor's failure is more often not "didn't go deeper" but "didn't ask who else writes to the state at layer 3".
Depth without fan-in is a tube, not a cross-section. It is filled by **grep** (all writers and callers), not by judgment.
This is the point where cross-thread synthesis MEETS depth. As a side effect: `fan-in > 1` with `ENFORCED` on
my branch = a direct suspicion of `ENFORCED-PARTIAL` (the guard stands on my path — but what about the paths of the others?).

**A caveat against a new Goodhart:** a heavy artifact (run/fork/harness) is mandatory for a claim about a
layer ≥3 and for any claim ≥5. On early layers `predicted/observed` may rest on reading — but
it must be written down BEFORE. A retroactive "I thought so" does not count; it is the first thing the gate checks.

**Side effect:** the "code → live state" boundary makes the live-current check early rather than
post-PoC — it directly cures the "latent / precondition closed" bucket.

## Technique 13 — `system_model.md` (the model's carrier)

An artifact next to `hypotheses.md` in `sessions/{target}/`, created by the entry hook from
`system_model_template.md`. **Why a separate file:** "everything is clean at depth 3" is not laziness but
**working-memory degradation**: by the fifth layer I no longer hold precisely what was at the first. The ledger stores
HYPOTHESES, but does not store the MODEL. The fifth layer must rest on what is written down, not on what is recalled.

Sections: `Corpus` · `Actors & Trust` · `Value Flows` · `State Machine` · **`Invariants`** (`I-NN` with
`check:`/`component:`/`pred:`/status/`file:line`/`tests`/`crowd-heat`/`lib:`) · `Missing Negatives` ·
`Long Tail` · **`Divergences`** (`D-NN`) · `Attention Gaps` · `Depth Trace` · `Model Revisions`.

**Divergences live ONLY here**; the ledger has a counter in `MODEL:` and a link. One source of truth.

**Two classes of invariants — economic ones are on equal footing with state ones.** Big hacks often break an economic
invariant that cannot be seen by reading functions ("the attack costs more than it wins" · "no risk-free cycle" ·
"the price doesn't move for free" · "an honest participant's costs are below revenue"). We have `J4: Economic
Model Analysis`, but it is late and optional — it comes AFTER hypothesis generation from code. 🔴 **A filter
against cheap `ABSENT`:** an economic `I-NN` goes into `D-NN` only if a concrete
permissionless sequence that breaks it is named; otherwise `Long Tail` (in phase 0, 9 of 19 were such junk).

**`invariant_library.md` (cross-hunt capital).** A model that dies inside a hunt makes T10 forever
expensive. A library keyed by **primitive** (`ERC20Votes` · `Wormhole-NTT` · `UniswapV2-fork` ·
`Anchor-PDA` · `Pyth-pull` · `halo2-gadget` · `QBFT`) stores the invariant + how the REFERENCE enforces it
(`ref:` with `file:line`) + 🔴 the canonical mechanism's **`fingerprint:`**. Three effects: T10 gets cheaper,
T10-B becomes a machine (a diff against the record), `ENFORCED` stops being thrown-away work.
Appended at the exit of EVERY hunt — only primitive `I-NN`, not business logic.

## Technique 14 — Attention-Gap Mapping (where the auditor didn't look / where the author didn't look)

A bug lives where **nobody looked**. Both techniques are machine-computable and **orthogonal to T10** —
they work even where there is no corpus. Checklist: `sessions/_methodology/attention_gap_mapping.md`.

**T14-A — the audit report as an INVERTED coverage map.** We read audits to dedupe findings —
post factum. The reversal: the report = a map of where the CROWD looked. A hole in the map = priority; a covered zone =
a rank penalty. Script: `scripts/_methodology/audit_coverage_invert.py` (phase `J-2`), output `crowd_heat.json`
is joined to the `I-NN` table. A class with zero mentions = a **class-level** hole, stronger than a file-level one.

🔴 **`crowd-heat` — a QUEUE, not a filter (operator amendment 2026-07-27).** `hot` ≠ "closed": the crowd
looked and did NOT follow through — real bugs have lived in well-discussed places; Orchard lived 4 years under
tier-1 audits. A veto by crowd-heat = a voluntary blind spot, exactly the forbidden frame "they looked here →
it's clean here". Order: `cold` first → `hot` **mandatory, but later**, with a dedup check of the spot before DRIVE.
Only a spot where a **concrete report with the same mechanism** was found counts as an expired `hot`.

**T14-B — Commit Archaeology.** Git shows where the AUTHOR didn't look: edits after the audit date ·
`quick fix/temp/TODO/revert/hotfix/wip` · churn · a commit without tests · the last commit before release.
Script: `scripts/_methodology/commit_archaeology.py` (phase `J-1`). Difference from `wave_delta.py`: that one is about
"what changed since my last visit", this one is about traces of haste in the history, it works on the FIRST visit.
🔴 **Requires the FULL history:** our default `--depth 1` kills the signal (5 of 6 session repos have a single
commit). The script itself detects a degenerate history and refuses to produce a ranking — the refusal is the result.

**Honest limitations:** a report does not list everything the auditor looked at and found nothing in ("a hole" ≠ "nobody
looked") → a rank bonus, not a guarantee of un-dup; the git signal is noisy alone (an active file can be
the core of the product) → take it **in intersection** with another source.

---

## Per-Skill Integration Map

| Skill | T0 Mandates | T1 File Prioritization (+ coverage gap-map) | T2 Hypothesis Loop | T3 Exploit Chaining | T4 Verifier Pass | T5 Patch-Diff Seeding | T6 Composite | T7 Hypothesis Registry | T8 Differential Fuzzing |
|---|---|---|---|---|---|---|---|---|---|
| **`/hunt`** | Read at session start, ALL mandates active | Phase 2.5 step 1; gap-map before any "no findings" | escalation path mid-scan | Phase 9 (report draft) | Phase 9 MANDATORY gate before submission (Med+) | Phase 2.5 step 0 if audit history exists | Phase 2.5 throughout + mandatory second-pass | Phase 2.5 — create at session start, update live | N/A unless target is multi-client/serialization |
| **`/deephunt`** | Read at J-2, ALL mandates active | J0 step 1 + re-score after J-2 audit mining; gap-map at J9 before NO-FIND | J0→J5 (this IS the loop) | J8.5 + J7 severity calibration | between J5 and J7 MANDATORY gate (Med+, no exceptions) | J-1 phase when audit reports found in J-2 | J0 + every D-Kill triggers re-run | J0 — create + maintain through J9 | J3+ when target parses a wire format / has 2+ clients (Cat 18) |
| **`/dapphunt`** | Read at Phase 0, ALL mandates active | Phase 2.5 step 1; gap-map before report | Phase 2.5 throughout | Phase 11 pre-submission | Phase 11 MANDATORY gate before report (Med+) | Phase 2.5b (OSS contract repo) | Phase 2.5 + Phase 7 retrospective | Phase 2.5 — create + maintain through Phase 13 | N/A (frontend) |

**T10-T14 (divergence-first layer — where they are enabled):**

| Technique | `/deephunt` | `/hunt` | `/dapphunt` |
|---|---|---|---|
| **T10** Independent Model First | **phase `J-M`** (between J-2 and J-1); check against code in `J1` | optional when entering with a repo | `MODEL: N/A` (the place is indicated by endpoints/auth) |
| **T11** Harness as Generator | gate `t11_applicable.py` at `J-M` (after T10) → APPLICABLE launches `J2` Invariant Break | N/A | N/A |
| **T12** Predictive Boundary Crossing | DEPTH-MAP on any depth claim | — | — |
| **T13** `system_model.md` | created by the entry hook on entry | the same file, if the hunt grew into a deep one | `N/A` |
| **T14-A** audit-map inversion | `J-2` (Audit Reports Mining) | when reports exist | when reports exist |
| **T14-B** commit archaeology | `J-1` (Deep Recon) | recon phase | if there is an OSS front-end repo |

**T9 Cold Restart (not a table column — it's a tier, not a phase):** `/deephunt` only. Fires at J9 when the entry gate (gap-map pass + second-pass empty + T6 empty) holds yet 0 valid findings, OR immediately on the operator's explicit manual override. Max 3, each a different I-assigned axis. See Technique 9.

---

## Related memory

Memory linking uses `[[name]]` convention — Claude resolves these via the user-home memory index, not via filesystem path (memory lives outside the project tree).

- `[[reference-claude-mythos]]` — what Mythos is, why we can't use it directly
- `[[feedback-no-cheating-on-verification]]` — anti-cheating discipline that powers Technique 2
- `[[no-giveup-hunt]]` — powers T0 Mandates 0.1–0.2 (don't give up, second-pass triggers)
- `[[chained-hypothesis-hunt]]` — powers T0 Mandate 0.4 and T6 (composite hypothesis protocol)
- `[[echo-monad-hack-2026]]` — chain example for Technique 3 + T6
- `[[transit-finance-2026-hack]]` — another chain example for T6
- `[[feedback-solana-hunt-reality]]` — audit-history-as-priority-signal source
- `[[feedback_cold_restart]]` — powers Technique 9 (Cold Restart: anchor-break via cold subagent on a new axis)
- `[[read-scope-before-severity]]` — powers Mandate 0.3 severity calibration
- `[[zcash-orchard-halo2]]` — powers Mandate 0.7 (model self-skepticism), T1 corpus note (seed primitive reference book), T2 targeted-pass+variance note; canonical public ZK under-constraint case
- `[[model-release-reaudit-window]]` — new-model-release = re-audit window for known-clean/audited targets (audited-clean ≠ bug-free across model generations)
- `[[hypothesis-taxonomy]]` (toolkit-side reference: `methodology/hypothesis_taxonomy.md`) — canonical bug-class catalog used as sweep checklist by T2 STATE A and T6 building-block enumeration
