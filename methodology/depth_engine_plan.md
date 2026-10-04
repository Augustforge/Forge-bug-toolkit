# Depth Engine — upgrade plan (accepted 2026-07-27, the operator)

> Status: **PLAN. Implementation has not started** — we start on a separate go-ahead from the operator, in phases.
> Related: `mythos_techniques.md` (T0-T9) ·
> `hypothesis_taxonomy.md` · `scout_fanout.md`

---

## 0. Problem statement (the operator's wording, 2026-07-27)

> "We know how to go deep. What we lack is the **non-obviousness of the angle**, the **mechanism** itself, and
> **where to dig that depth, at which spot**. The system must learn to detect these divergences and weak
> spots — and then dig into them in depth."

The diagnosis in three points:

1. **We have depth, we don't have un-dup.** We have reached high-severity findings (depth was there) → they
   turned out to be DUPLICATES, $0. So the miss is not in the number of layers but in the **originality of the entry point**.
2. **We have a depth METRIC and no METHOD.** Depth is defined as a layer counter (DEPTH-MAP
   L1→L5) — and a counter gets padded formally: `call→state→external→hook→accounting` inside a single file
   = "5/5", the gate is satisfied, there is no understanding of the system. The `DEPTH-MAP SINGLE-SUBSYSTEM` patch fixed the metric,
   not the absence of a method. This is Goodhart on our own gate: the loop optimizes "5 layers",
   not "understanding of the system".
3. **SELECT is subjective.** A thread is chosen by "severity×confidence" by eye, i.e. by what
   *looks* risky. Exactly the same thing looks risky to the crowd → duplicates. We need an **objective**
   source of entry points.

### Buckets of unpaid findings (why "dig deeper" does not cure everything)

| Bucket | Typical cases | The real cause | The cure |
|---|---|---|---|
| DUPLICATE | an angle the crowd also took | originality of the angle | **T10 + T11** (divergence-first) |
| Known / acknowledged | well-audited targets, issues already in audit reports | late dedup | dedup-before-verify (exists) + T10 (an audit = an entry into the model corpus) |
| Latent / precondition closed | findings that need a precondition that live state never reaches | we dug into code, not into live state | T12 (a layer = a boundary crossing, live state is mandatory) |

---

## 1. The core of the solution: DIVERGENCE-FIRST

**Thesis.** The only source of hypotheses today is reading code. Hence the ceiling: I see the same as
anyone who reads the same code — and the crowd reads it. Un-dup requires a source the crowd
does not have.

**Such a source is the divergence between an independent model of the system and its implementation.** A divergence
is objective (it either exists or it doesn't), it is rankable, and — most importantly — it points to a PLACE. This is
the answer to "where to dig".

Four techniques combine into one machine:

```
        T13 system_model.md          ← the carrier (model + invariants + divergences)
              │
      ┌───────┴────────┐
  T10 manual        T11 machine     ← TWO generators of divergences
  (spec→code)      (invariant→fuzzer)
      └───────┬────────┘
              ▼
        D-NN divergences             ← objective entry points, ranked
              ▼
        SELECT (new priority 1)
              ▼
        DRIVE downward, where a layer counts only via T12 (boundary crossing)
```

- **T13** — the storage (without it T10/T11 have nowhere to be kept).
- **T10** — the manual generator of divergences.
- **T11** — the machine generator of divergences.
- **T12** — the depth quality gate (so that a found divergence is dug into for real).

---

## 2. T10 — Independent Model First

### The essence

Build a model of the system **BEFORE reading the implementation** and look not for a "strange line" but for the **place where
an invariant is not enforced**. A bug lives in the divergence between the model and the code, not in suspicious code.

Precedent: Zcash Orchard. Taylor Hornby did not read halo2 more carefully than the auditors — he took the **halo2 book
as a reference model of the primitive** and compared it against the implementation. `assign_advice()` without `copy_advice()` is
the absence of a constraint, i.e. something that is NOT in the code. Our lesson "the corpus matters more than the prompt" was recorded as prompting
advice; here it becomes a mandatory beat of the loop.

### Protocol

1. **Assemble a spec corpus** (do NOT open the implementation): README, docs/whitepaper, NatSpec comments,
   **the project's tests** (an executable spec of intent), audit reports (they describe intended behavior),
   the spec of the parent primitive (an ERC standard, Lido, the halo2 book, QBFT, VIP/ZIP).
2. **Write out invariants `I-NN`** in `system_model.md` — as formulas, not prose:
   `Σ metadata.balance(ETH-gems) + ethFees ≤ address(this).balance`
   `∀ token: the payout asset on redeem == the asset deposited on mint`
   `∀ role R: R can X ⟺ <a condition from the docs>`
> 🔴 **SPECIFICITY LIMIT (earned in phase 0, mandatory): ≤12 invariants, and no more than half
> with a status other than `ENFORCED`.** Without the limit the blind stage produces a shotgun — in phase 0
> the modelers marked 11 of 13 and 15 of 19 as risky, and a hit at such breadth is partly
> guaranteed by the sheer spread. With the limit, precision **rose**, not fell (rerun C: 6 of 12
> were deemed reliable — and the precise hit came exactly there). The blind stage yields CANDIDATES;
> ranking is done by the beat-4 ranker, which does not exist yet without code.
>
> 🔴 **The model is built by a SENIOR model, not a scout tier.** In phase 0 `sonnet` missed case C,
> the senior model on the same corpus hit. Saving on the tier here costs a missed bug.

3. **Only now read the code** and for EACH `I-NN` answer: **where is it enforced?** — five statuses:
   - `ENFORCED` — an explicit `require`/`assert`/type, **on all paths** → closed
   - 🔴 `ENFORCED-PARTIAL` — a check EXISTS but is incomplete/wrong: it holds on path A and does not hold
     on path B; the wrong operand; off-by-one; the guard sits after the use → **`D-NN`, top priority**
   - `IMPLICIT` — follows from the structure but is not checked → `[CONTESTED]`, a candidate
   - 🔴 `ABSENT` — not enforced anywhere → **`D-NN`, top priority**
   - 🔴 `SUBSTITUTED` — **the canonical mechanism is replaced by a home-grown one** (the check is in place and the
     lifecycle looks correct visually, but it stands on a different foundation) → **`D-NN`, top
     priority, above a plain `ABSENT`**

   > **`SUBSTITUTED` is the 5th status, added after phase 0 (2026-07-27).** The blind test showed:
   > "the mechanism is replaced by a home-grown one" is neither `ABSENT` (a check exists) nor `ENFORCED-PARTIAL`
   > (the defect is not in the incompleteness of a check but in the foundation). There was no slot — the modeler was forced
   > to pick the nearest label. A check against our own experience: **a mock-vs-prod divergence = exactly `SUBSTITUTED`**,
   > we have called this "divergence" for years with no place in the schema. The real phase 0 case: voting power
   > was derived from a home-grown accounting subsystem instead of the canonical per-block checkpoints — the governor
   > looked correct as a whole.

   🔴 **The OPERATOR "is the mechanism canonical?" (mandatory, earned in phase 0).** For every
   invariant that the corpus describes as "the standard way", ask: **does THIS implementation use the
   standard mechanism or did it build its own analogue?** Why it is mandatory: in phase 0 the modeler
   marked the canonical mechanism as `ENFORCED` — "hard to get wrong" — and built all the risks ON TOP of
   the assumption that it was in place. The mechanism was not there at all. **The more canonical a mechanism is in the spec,
   the more readily it is taken for granted — by the model and by the auditor alike.** That is exactly where the criticals that survived audits live.

   🔴 **CONVERGENCE as a rank signal.** If several independent `I-NN` converge on ONE component —
   that is a pointer to the place stronger than any single status. It is counted mechanically (a counter of `I-NN` per
   component). In phase 0 three `PARTIAL` and one `ABSENT` converged on the source of voting power — and that is where
   the real defect was.

   > **`ENFORCED-PARTIAL` is not decoration but our main class.** A check against our own history:
   > a charge that **excludes** proved work while the reward **includes** it, an inverted
   > check in a repay hook, a fee computed in BOTH branches but withdrawn in ONE,
   > a floor that reads a pre-finalize NAV. None of the four is `ABSENT` — all are `ENFORCED-PARTIAL`.
   > A three-status scheme would have missed our main class entirely.
   > The search operator: for every `ENFORCED` ask "**on all paths?**" — enumerate the paths
   > explicitly (if branches, sibling functions, batch-vs-single, mint-vs-burn, ETH-vs-token) and check each.

4. **Rank `D-NN` objectively** (not "by eye" — that is the same disease we are treating). Rank =
   the product of three machine/semi-machine-checkable components:
   - **value-weight** — how much value passes through the invariant (walk backward from transfer/mint/burn)
   - **path-count** — how many paths bypass it (`ENFORCED-PARTIAL` is the more dangerous the more branches there are)
   - 🔴 **test-coverage = 0** — **the invariant is covered by no test of the project**. The strongest and the
     cheapest component: we have to read the tests anyway (the rule "always check the project's own tests"),
     but we count LINE coverage, not **invariant** coverage. An invariant that nobody tested
     is an invariant that nobody checked.
   - 🔴 **crowd-heat (a penalty, not a veto)** — from T14-A/§5-bis: whether this `I-NN` was discussed in audit reports.
     Hot = later in the queue, but **must be walked through**. The rule is in §6.
   - 🔴 **convergence** — how many DIFFERENT `I-NN` converge on one component (see the convergence signal above).
     It is counted mechanically from the `component:` field in the `I-NN` table; **without this field there is nothing to count
     a component from and the signal is dead** — the field is mandatory in the T13 template.

### 🔴 Idea C — Test-Inversion (the missing negative as an enumerable set)

`test-coverage = 0` answers "is the invariant covered at all". Test-inversion answers **"which path
is not covered"** — i.e. it yields concrete branches for the `ENFORCED-PARTIAL` operator, not a general flag.

The mechanics: from EACH written test derive its unwritten negative/repeat/permutation.
`test_UserRedeem` implies the missing `RedeemTwice`, `RedeemAfterTransfer`,
`RedeemCeasedGem`, `RedeemZeroFee`. The set of negatives is enumerable mechanically from the names and bodies of
existing tests, and maps one-to-one onto the list of paths that the "on all paths?" operator requires checking.

The enumeration axes (they cover most cases): **repeat** (twice in a row) · **order** (A→B vs B→A) ·
**actor change** between steps · **boundary value** (0 / max / first / last — meshes with the
boundary-value lens) · **an interrupted path** (step 1 without step 2).

Confirmation from experience: a defect can sit **in the project's own test** — `_createGem(2, 5e18, 1e17, …)`
created a gem that is unredeemable by construction, and no test ever redeemed it. The negative
"and a redeem of this gem?" is derived from the test mechanically.

Cheap and needs no new corpus: the tests are already read by a mandatory rule. The artifact is the section
`## Missing Negatives` in `system_model.md`, each negative referencing the test that generated it.

5. **Feedback `D-NN` → model (a mandatory beat).** If DRIVE showed that the model was wrong
   (the docs lie / the primitive behaves differently) — **feed the correction back into `system_model.md` immediately**,
   before continuing. Otherwise the remaining `I-NN` stand on sand and the whole `D-NN` list is contaminated. The loop is
   two-way: model → divergence → DRIVE → **a refined model**.

### When there is no corpus (a fresh client, fresh deployments, private forks)

A three-line README is no reason to skip T10. The model is built from a surrogate corpus, in order of
preference:

1. **An analogue/reference** — a related protocol, a canonical standard (ERC/ZIP/VIP), a previous version
   of the same code, a direct competitor → see **T10-B** below (the cheapest and most accurate path).
2. **The project's tests** — exist almost always and are an executable spec of intent.
3. **Economic meaning** — "if I were building this, which invariant MUST hold for the protocol
   not to go bankrupt". Weaker than the first two, but better than zero.

### T10-B — Family Invariant Diff (transferring an invariant, not a finding)

If the target is a fork or a member of a family (Uniswap forks, Wormhole-NTT, OZ-based, Cosmos SDK, Anchor templates):
**do not build a model from scratch — take the reference and diff the guards.** What the parent has and what is absent
here = a ready-made `ABSENT`/`ENFORCED-PARTIAL` almost for free.

The difference from our existing `protocol_family_bug_transfer`: that one transfers a **finding** (post-factum,
after a bug has been found elsewhere). T10-B transfers an **invariant** — it works BEFORE a finding,
and therefore is stronger. A Wormhole-NTT fork was exactly this case.

### Anti-anchor: the model is built NOT by the one who digs

`system_model.md` is filled in by a **cold subagent from the corpus without access to the implementation**; the main
instance digs. Then the model physically cannot be fitted to code already seen. It is the same trick
that gives T4 its power, but applied at the INPUT. It costs pennies and drops straight into the workflow.

### When NOT to apply T10 (otherwise it burns time for nothing)

- a single small contract (< ~300 LOC) that is read in full faster than a model is built;
- `/dapphunt` frontends and web2 targets — there the place is indicated by other signals (endpoints, auth providers);
- a re-visit by `wave_delta` (the model already exists from the previous visit — **extend it, do not rebuild**).

### Why this works for un-dup

`ABSENT` is an **absence**, "the dog that did not bark". The crowd reads what is written; the absence of
a check is visible only to someone who knew in advance that a check should exist. The knowledge comes from a model
built BEFORE the code.

### The critical requirement

Item 2 is performed **before** reading the implementation. Otherwise the model is contaminated by the code, and I will "prove" that the code is right —
the same disease that cold-context treats in T4, only applied at the INPUT rather than at the output.

### Retro-check (a worked example)

The invariant "a gem is redeemed by the asset it is backed by" is written out from the README in a minute. The enforcement check:
the unit of measurement of `metadata.balance` is **stored nowhere** → `ABSENT` → a Critical
and a High fall out immediately, BEFORE reading the function bodies. Reaching them by reading and a symmetry scan
takes longer and is not guaranteed.

---

## 3. T11 — Harness as Generator (a fuzzer as a generator, not as a verifier)

### The essence

Today fizz/Echidna/Medusa/Trident/fork-PoC are switched on **when a hypothesis already exists** — to
confirm it. That is a waste of the tool. An invariant fuzzer that is given an `I-NN` from T13 and
let loose finds a **call sequence** that cannot be reached by reading in principle — and
that is where un-dup lives, because the crowd reads and does not run.

### Indirect confirmation from our own data

All of our confirmed Highs are about a **sequence / state transition**, not a single
bad line: a split cooldown where the floor reads a pre-finalize NAV, depth-band
price impact, a fee-migration reward/charge asymmetry. This is exactly the class that
stateful fuzzing catches.

### Protocol

1. Take an `I-NN` from `system_model.md` (**this is why T10 goes first**).
2. Encode the most valuable one as a property: fizz/Echidna/Medusa (EVM) · Trident (Solana) ·
   proptest/quickcheck (Rust/Go) · differential T8 (multi-client).
3. Run **before a hypothesis appears**. The goal is not to confirm but to **find a sequence**.
4. A found sequence = a `D-NN` of machine origin → into SELECT.

### Anti-tautology (mandatory)

The invariant is taken from the **independent model**, not from the code. An invariant copied from the implementation will make the
fuzzer prove that the code does what it does. It is our existing anti-tautology gate (flounder),
applied to fuzzing.

### Trigger (a harness is expensive — hours)

Apply when: (a) the target is EVM/Solana with a state machine; **and** (b) T10 yielded an invariant that
**cannot be checked by reading** (multi-step / order-dependent). Otherwise — skip.

---

## 4. T12 — Predictive Boundary Crossing

> **The decision on the question "B = a hybrid with T12 or a replacement?" (the operator, 2026-07-27): a HYBRID, and it is stronger than the sum —
> because the two requirements are closed by ONE action and cure each other's weaknesses.**
>
> They answer DIFFERENT questions: T12 — "did I move down?" (anti-gaming of the counter);
> B ("predict, then verify") — "did I understand the layer I passed?" (anti-superficiality).
> Separately each can be bypassed: pure T12 is satisfied by the mechanical production of artifacts
> without understanding (**exactly the Goodhart risk I noted myself: "I will start producing logs instead of
> thinking"**); pure B spins in place — you can predict the behavior of a single function a hundred times
> without descending anywhere.
>
> **The key: the artifact for T12 and the check for B are one and the same action.** When going "static →
> runtime", I must first write down "I expect Y", then run it and get a log. The log = the T12 artifact
> = the verification of the B prediction. The work is not doubled — B **gives meaning** to the artifact, and T12 forces
> every prediction to pull downward. So not "replace" and not "put side by side", but merge into a single
> mechanism with two crediting conditions.

### The essence

**A layer counts only if BOTH conditions are met:**

1. **a representation boundary is crossed** (not just one more read);
2. **a prediction is made BEFORE the crossing and verified AFTER**.

Five reads in a row in one file = **one** layer, not five. A crossing without a prediction = **zero**
layers (it is movement, not understanding).

### Three fields for every DEPTH-MAP layer

```
L3  boundary: static → runtime (fork run)
    predicted: redeem() will return 99 ETH, fees will grow by 1e18
    observed:  revert ERC721IncorrectOwner  ← artifact: forge log, line 214
```

### 🔴 `predicted ≠ observed` is a GENERATOR, not an accounting error

A prediction miss resolves into three outcomes, and each is movement:

| Outcome | What to do |
|---|---|
| **the system behaves unexpectedly** | immediately a new `D-NN`, top SELECT priority |
| **I did not understand the system** | dig the SAME layer deeper, do not go down (the counter does not grow) |
| **the model was wrong** | feedback into `system_model.md` (see beat 5 in T10) |

**This closes the system loop:** T10/T11/T14 give the PLACE → the T12 hybrid digs → its own
prediction misses give birth to new `D-NN` → SELECT. Depth stops being only an expense and
becomes one more source of entry points.

### Boundary types (each leaves an artifact)

| Boundary | Artifact proof |
|---|---|
| static → runtime | the log of a test / fork / harness run |
| repo/module A → repo/module B | the path + commit of both |
| spec → implementation | a quote from the corpus + `file:line` |
| deployment A → deployment B (chain / version) | two addresses/commits + a diff |
| code → live on-chain state | the output of an `eth_call` / RPC read |

### Enforcement

Every DEPTH-MAP row must carry: `file:line` + **the boundary type** + **`predicted:`** +
**`observed:` with a reference to the artifact**. A layer without all four is not credited. This makes depth
non-fakeable by prose — neither a boundary crossing nor a prediction miss can be imitated,
both leave a trace.

**A caveat against a new Goodhart:** a heavy artifact (a run/fork/harness) is required for a **claim
of layer ≥3 and for any claim ≥5**, not for every step of thinking. On early layers `predicted/observed`
may rely on reading — but it must be written down BEFORE, not after. A retrospective "I thought so"
is not credited; this is the first thing the gate checks.

### 🔴 Idea D — Depth Fan-In (on every layer: who ELSE touches this state)

**The problem this fixes.** Our depth ceiling is strictly vertical along a SINGLE thread. But an auditor's
failure is more often not "did not descend deeper" but "descended along one path and **did not ask who else writes
to the state at layer 3**". Depth without fan-in is a tube, not a slice.

**The rule.** Every DEPTH-MAP layer gets a fourth mandatory field:

```
L3  boundary:  static → runtime (fork run)
    predicted: fees will grow by 1e18
    observed:  fees == 0  ← forge log :214
    fan-in:    fees ← redeem() :179 · redeemNative() :190 · withdrawFees() :261  (3 writers, 1 on the thread)
```

It is filled in **mechanically** — grep by the variable/account/storage name: all writers and all
callers. Not a judgment but an enumeration, so there is nothing to imitate.

**Why this is strong.** This is the point where cross-thread synthesis **meets** depth rather than running
parallel to it: a writer of the same state from ANOTHER subsystem is a ready second piece of evidence for T6, and
it is found not by intuition but by grep. It also fixes DEPTH-MAP-single-subsystem honestly, rather than with a formality.

**As a side effect:** fan-in > 1 with `ENFORCED` on my branch is a direct suspicion of `ENFORCED-PARTIAL`
(the guard is on my path, but on the paths of the other writers?). That is, D feeds T10 back.

### Side effect

It directly cures the "latent" bucket: the "code → live state" boundary becomes mandatory for a depth claim,
i.e. the live-current check happens EARLY, not after the PoC.

---

## 5. T13 — `system_model.md` (the artifact)

Lives next to `hypotheses.md` in `bug-bounty-toolkit/sessions/{target}/`. Created by an entry hook from a
template — like `hypotheses.md`, so that "forgetting to create it" is physically impossible.

**Why a separate file:** the hypothesis for why "at depth 3 everything is clean" is not laziness but the **degradation of working
memory**: by the fifth layer I no longer hold precisely what was on the first. `hypotheses.md` stores **hypotheses**,
but not the **model of the system**. The fifth layer must rely on what was written down, not on what is remembered.

### Structure

```markdown
## Corpus            — what was read BEFORE the code (docs, tests, audits, the primitive's spec, the family reference)
## Actors & Trust    — who can do what (roles, permissionless vs privileged)
## Value Flows       — where value enters and exits (walk backward from here)
## State Machine     — states and transitions
## Invariants        — I-NN: formula · check: <what to go and check in the code> · class (state|economic) ·
##                    source · component: <node, for convergence> · pred: <the expected status,
##                    set BEFORE the code — idea F> · enforcement: ENFORCED / ENFORCED-PARTIAL /
##                    IMPLICIT / ABSENT / SUBSTITUTED · file:line · tests: N ·
##                    crowd-heat (hot|cold, from T14-A) · lib: <the invariant_library key, if from the library>
## Missing Negatives — from idea C: unwritten test negatives → concrete paths for ENFORCED-PARTIAL
## Long Tail         — I-NN beyond the limit ≤12: not ranked and not gated, but NOT deleted (mitigation of the
##                    limit's recall risk; an input on a pivot/T9)
## Divergences       — D-NN: which I-NN is violated · where · rank (value × paths × test-coverage ÷ crowd-heat) · → H-NN
## Attention Gaps    — from T14: holes in the audit map + suspicious commits (the second source of a PLACE)
## Depth Trace       — layers passed: boundary · predicted · observed · artifact · fan-in (idea D)
## Model Revisions   — model corrections from DRIVE feedback (beat 5 of T10)
```

### 🔴 Idea A — `invariant_library.md`: the model as CAPITAL, not a consumable

**The problem.** `system_model.md` is born and dies inside a single hunt. So T10 costs the same
every time, and knowledge gained on Wormhole-NTT does not make the next NTT fork cheaper.

**The solution.** A cross-hunt library `bug-bounty-toolkit/methodology/invariant_library.md`,
keyed by **primitive**, not target: `ERC721/OZ-v5` · `Wormhole-NTT` · `UniswapV2-fork` · `Anchor-PDA` ·
`Cosmos-SDK-module` · `halo2-gadget` · `Pyth-pull` · `QBFT`. Under the key — a list of invariants with
**how the reference enforces them** (`file:line` in the reference implementation).

**What this gives (three effects, each measurable):**

1. **T10 gets cheaper with every hunt.** On a familiar primitive the model is not built from scratch but
   instantiated from the library → the 30-45 minute time-box drops to minutes.
2. **T10-B becomes a machine, not a trick.** A fork that does not enforce its parent's invariant = `ABSENT`
   **for free**, by a simple diff against the library entry. Right now it is a manual comparison.
3. **`ENFORCED` stops being wasted work.** Today "the invariant holds" = a dead end and zero
   value. In the library it is an **asset**: a confirmed guard of the reference is the reference for the whole family.

**Maintenance rule:** every closed hunt appends to the library only those `I-NN` that relate to the
**primitive**, not to the target's business logic (otherwise the library bloats into a dump). An entry must
carry the reference's `file:line` — without it, it is an opinion, not a reference.

It directly feeds `single_target_mastery` (compounding knowledge) and `protocol_family_bug_transfer`
(transferring an invariant instead of transferring a finding).

### 🔴 Idea E — `fingerprint:` in the library: `SUBSTITUTED` becomes COMPUTABLE

**The problem this fixes.** `SUBSTITUTED` is the most valuable of the five statuses (a defect in the foundation,
not in a particular path) and at the same time the only one with no objective marker: "the mechanism
is home-grown" is decided today by judgment. A status assigned by taste will be assigned rarely and
inconsistently — i.e. the main lesson of phase 0 will not survive to combat use.

**The solution.** A canonical mechanism almost always has a **machine fingerprint** — an import, a base
contract, a characteristic signature, a storage shape. So in `invariant_library.md` under each
invariant a third column appears, `fingerprint:`:

| Primitive | Invariant | `fingerprint:` of the canonical mechanism |
|---|---|---|
| `ERC20Votes/OZ` | vote weight is taken from a snapshot in the past | base `ERC20Votes`/`Votes`; a checkpoint array + binary search; `getPastVotes(addr, block)` |
| `Pyth-pull` | the price is not older than N seconds | `getPriceNoOlderThan(...)` (and NOT `getPriceUnsafe` + a custom `publishTime` check) |
| `OZ-ReentrancyGuard` | no re-entry | the `nonReentrant` modifier from OZ (not a custom `bool locked`) |
| `UniswapV2-fork` | k does not decrease | `require(balance0Adj*balance1Adj >= reserve0*reserve1*1000**2)` |

**The detection rule (grep, not judgment):** *functionality present + fingerprint absent*
= a `SUBSTITUTED` candidate. This is exactly what case C of phase 0 looked like: the governor called "weight at a past moment",
and under the call there were neither checkpoints nor a binary search — a home-grown accounting subsystem.

**Why it is cheap:** no separate mechanism is needed, it is one column in the artifact of idea A. Every
hunt that recognized a primitive appends the fingerprint together with the invariant. A detector script
(`canonical_fingerprint.py`, grepping fingerprints over the target) makes sense **only after** the
library accumulates ≥10 entries — earlier it would be searching an empty space (the same rule we already
applied to the magnitude-gate: first ≥2 cases, then the gate).

### 🔴 Idea F — `pred:` against fact: the T12 mechanics, lifted to the MODEL level

**An observation of phase 0 that is stronger than the result itself.** The blind test is exactly "predicted →
verified", only applied to invariants rather than to depth layers. And the divergence gave more than the hit:
it was `pred=ENFORCED / fact=ABSENT` that exposed the whole `SUBSTITUTED` class. The mechanism has already
proven itself on our own test — what remains is to carry it into the combat loop.

**The rule.** On the blind beat (2), for each `I-NN` a `pred:` is written — where I EXPECT to see a weakness.
On beat 3, after reading the code, the actual `status:` is set. The divergence is read in two
directions, and they are not equal:

| Divergence | What it means | Action |
|---|---|---|
| `pred: ABSENT` → fact `ENFORCED` | **my model of the domain is wrong** — I expected a hole where there is none | a model correction (beat 5), and it is a cheap measurement of my own calibration |
| 🔴 `pred: ENFORCED` → fact `ABSENT`/`SUBSTITUTED` | **a place that EVERYONE considers closed** | **the top `D-NN` rank, above a plain `ABSENT`** |

**Why the second row is a principle, not a heuristic.** Un-dup means "the crowd does not look here".
An invariant that I myself, knowing the domain and holding the spec in my hands, confidently considered enforced is exactly
the invariant that any auditor just as confidently considers enforced. The absence of a check there
is invisible **by construction**, not by chance. This gives us the first non-taste basis for
the order of statuses inside priority 1: today "`SUBSTITUTED` above `ABSENT`" rests on a single
observation, while with `pred:` the order is computed from the divergence.

**A side effect — measurable calibration.** The share of "I was sure and wrong" per hunt is an honest number
about my domain intuition, which is not measured at all now. It goes to `calibration_log.jsonl` (§10).

**Cost:** one column in the `I-NN` table and the requirement to fill it BEFORE reading the code (checked
the same way as `predicted:` in T12 — by order, not by presence).

### Two classes of invariants — economic ones are equal to state invariants

All our invariants today are about **state** (`Σ balances ≤ balance`). Large hacks often break an
**economic** invariant that cannot be seen by reading functions, only by modeling:

- "the attack costs more than the gain" (otherwise — griefing/an economic exploit)
- "there is no risk-free cycle" (mint→redeem in one transaction must not yield a profit)
- "the price does not move for free" (no free shift of the oracle/curve)
- "the honest participant's costs are lower than their income" (otherwise — the departure of liquidators/validators)

We have a phase `J4: Economic Model Analysis`, but it is **optional and late** — it comes after
hypotheses have already been generated from the code. Economic `I-NN` must be entered into `system_model.md`
**on a par** with state invariants, i.e. BEFORE reading the code. Mark them with the field `class: economic`.

> 🔴 **A filter against a cheap `ABSENT` (correction 7 of phase 0, mandatory).** An economic `I-NN`
> is almost always "not expressible in code" — and therefore gets `ABSENT` for free, inflating the list for
> nothing (in case C this accumulated 9 of 19). An economic invariant counts as a divergence
> **only if a concrete permissionless sequence that breaks it is named**. No
> sequence — into `## Long Tail`, not into `D-NN`.

A check from experience: a defect can break a state invariant while its **permissionless amplification**
(a circular mint→redeem pumping `fees`) is an economic invariant "a risk-free cycle must not
shift someone else's pool". The second was found only because I specifically looked; in a model it would have been there from the start.

---

## 5-bis. T14 — Attention-Gap Mapping (a map of the attention deficit)

**The common principle of the two techniques:** a bug lives where **nobody looked**. An audit shows where the
*auditor* did not look; git shows where the *author* did not look. Both give a PLACE, both are machine-computable,
and both are **orthogonal to T10** — they work even if there is nothing to build a model from.

### T14-A — An audit report as an INVERTED coverage map

Today we read audits to **dedup findings** — i.e. post-factum. The reversal: a report is
a map of **where the crowd looked**.

1. From all available reports assemble an "attention map": which files / functions / bug classes are mentioned.
2. Overlay it on the surface → **the holes of the map** = priority places.
3. A `D-NN` that lands in a hole of the map gets a **rank bonus**; a `D-NN` that lands in a covered zone gets
   a penalty and a mandatory dedup check BEFORE DRIVE (our `dedup_before_verify`, but applied to the PLACE,
   not to the finding).

### 🔴 Idea B — dedup at the level of the INVARIANT (`crowd-heat`), not the file

An attention map by files/functions is crude: the crowd reasons in **invariants**, not lines.
If a report discusses "can a fee be charged twice" — the **invariant** becomes crowded,
in whichever file we find the divergence. So the T14-A map is collapsed into one field right in the
`I-NN` table: `crowd-heat: hot | cold`.

**🔴 The operator's amendment (2026-07-27) — accepted as a rule, it is not cosmetic:**

> "Even if the `crowd-heat` field is set, it is still worth digging through ourselves — but at the very end.
> At the start we must go where there is no `crowd`."

This is right, and here is why it is fundamental: **`hot` ≠ "closed".** The crowd looked — but the crowd
also **did not follow through**: findings routinely live in exactly the "discussed" places, and a
halo2 bug lived for 4 years under tier-1 audits. A veto by `crowd-heat` = a voluntary blind spot, exactly
the forbidden frame "it has been looked at here → it is clean here".

So `crowd-heat` is a **rank divisor, not a filter**:

| Order | What we take | Rationale |
|---|---|---|
| 1 | `cold` divergences | maximum un-dup, which is what this was all for |
| 2 | `hot` divergences | **mandatory to walk through**, but after the cold ones; before DRIVE — a dedup check of the place |

A `hot` one counts as overdue only where a dedup check found a **concrete** report with the same
mechanism, not "the topic was mentioned".

**Why this cures our main bucket:** un-dup is obtained by construction, not by luck. Duplicate findings are exactly the case where an attention map would have said we were digging
in the same place as everyone else. We already have `adversarial_reading.md` and T5 patch-diff seeding — what is missing
is precisely the **inversion**: read a report not for what is in it but for what is not in it.

### T14-B — Commit Archaeology (git as a pointer to haste)

Bugs live in code that was written in a hurry. The signals, all computable from history:

- a commit **after the audit date** (our `deployed ≠ audited`, but generalized to the whole repo);
- the commit message: `quick fix` / `temp` / `TODO` / `revert` / `hotfix` / `wip`;
- high file **churn** (many edits in a short time = unstable logic);
- code added **in a single commit without accompanying tests** (meshes with the `test-coverage = 0` ranker);
- a PR merged without review / with a single approval from the author;
- **the last commit before a freeze/release** — the classic place of an unreviewed edit.

The difference from the existing `wave_delta.py`: that one answers "what changed since my last visit"
(a re-visit), T14-B — "where in the project's history are the traces of haste" (the first visit too).

> 🔴 **An operational condition exposed during the dry run (2026-07-27): T14-B requires the FULL history, and we
> clone shallow.** A check of the session repos: 5 of 6 are `--depth 1`, exactly one commit. On such a
> clone there is no signal at all. **Clone with full history when T14-B is planned**; if the
> repo was published as a squash ("publishing to public repo") — look for an upstream/mirror. The script itself
> detects a degenerate history and explicitly refuses to produce a ranking (otherwise a "confident list out of
> nothing" would be read as a source of a PLACE — the same silent cap we forbid).

---

## 6. Integration: the new SELECT priority

It was (two streams: code-centric + boundary-centric), it is now — **divergence at the head, and there are now three objective
generators of a PLACE**:

| # | Source | Where it comes from | Objective? |
|---|---|---|---|
| 1 | 🔴 **`D-NN` — a model↔code divergence** (`SUBSTITUTED` / `ABSENT` / `ENFORCED-PARTIAL`) | T10 (manual) + T11 (machine) | yes — rank = value × paths × test-coverage × convergence |
| 2 | 🔴 **Attention-gap** — a hole in the audit map / a trace of haste in git | T14-A / T14-B | yes — computable from reports and history |
| 3 | 🔴 **A prediction miss** `predicted ≠ observed` | T12 hybrid (a by-product of DRIVE) | yes — recorded in the DEPTH-MAP |
| 4 | `H-NN` by severity × confidence | code reading | no (taste) |
| 5 | a boundary lead (a trust boundary) | T1 boundary-centric | partially |
| 6 | an unread score-5 → score-4 file | T1 rubric | no |
| 7 | a T6 composite of refuted ones · 8. a T9 new axis | — | — |

**This is the mechanical answer to "where to dig":** the first three positions are pointed to not by taste but by
computable artifacts. Moreover source #3 is generated by depth itself — the loop is closed.

**The intersection of sources = maximum priority.** A `D-NN` that lies in a hole of the audit map AND in a
file with a trace of haste is the best place the system knows how to name. Such a coincidence outranks
a single `D-NN` of any severity.

**🔴 The order inside priority 1 (the operator's amendment, idea B): `cold` first, then `hot` — but `hot`
is walked through MANDATORILY.** A queue, not a filter. The gate: source #1 cannot be declared worked out
while unwalked `hot` divergences remain; "it is crowded there" is not a falsifier and does not count as a kill.

---

## 7. Synthesis with the graph upgrade

The key link for which the graph upgrade goes AFTER T10/T13:

**Scout Fan-Out is sliced by INVARIANTS, not by subsystems.** A scout gets the task
"find where `I-03` is not enforced" instead of "scan the accounting files". This changes the quality of leads
radically: a scout returns an `ABSENT` fact with `file:line`, not an opinion about what looks risky.
Plus a `schema`-forced return makes the absence of a falsifier impossible.

From the graph upgrade we take (decided 2026-07-27):

- **Scout Fan-Out → a `Workflow` script with a `schema`.** The gain is not in saving context but in
  enforcement: validation at the tool-call level → the model retries a lead without `file:line`/prediction/
  falsifier. Design the schema **isomorphically** to the `## Scout Fan-Out` section in the ledger.
- **T4 → a panel of lenses, WITHOUT majority vote.** Three lenses (correctness / exploitability /
  dedup-vs-audit); a kill only by a hard falsifier `file:line` from any one of them. A majority ("2 of 3
  refute → kill") systematically kills our target cross-thread/depth-ceiling findings, where
  each piece of evidence separately is harmless (a halo2 bug survived 4 years for exactly this reason) → it drops recall,
  which is forbidden by the measure-don't-feel rule.
- **gap-map as loop-until-dry** (the operator insisted): "run the unread score-4/5 files until the list
  is empty" — honestly mechanical parallel work, it is encoded.
- **Rejected:** loop-until-dry on T9. The T9 axis is set by abduction, not by a counter; `while(dry<2)
  spawn finders` = N same-type passes with the same frame = exactly our false exhaustion.

---

## 8. Work phases

| Phase | What | Cost | The gate to go further |
|---|---|---|---|
| **0** | ✅ **DONE 2026-07-27.** A blind retro-validation of T10 on 3 third-party bugs. Result: **2/3, the gate passed, GO**; a rerun of the missed case on a senior model gave a precise hit on mechanism and place. Artifacts: `sessions/_methodology/phase0_blind/` (PROTOCOL · GROUND_TRUTH · corpus_A/B/C · RESULTS) | cheap, no code | ✅ passed |
| **1** | ✅ **DONE 2026-07-27.** Created `system_model_template.md` (5 statuses, `check:`/`component:`/`pred:`, Long Tail, CANON-TODO), `independent_model_first.md`, `attention_gap_mapping.md`, `blind_spots.md`, `methodology/invariant_library.md` (with `fingerprint:`); mythos ← Mandate 0.9 DIVERGENCE-FIRST + T10-T14 + SELECT a1-a3 + T4 without majority; deephunt ← phase `J-M`, J1 expanded into an enforcement-map, J0.5 partitions by invariants, completeness-gate item 5b, the `S-M` mirror; the entry hook creates the model independently of resume (K3) + a J-M beat; 4 model gates + 29/29 replay | methodology + template, little code | ✅ tests green; a dry run on a live hunt is ahead |
| **1b** | ✅ **DONE 2026-07-27.** `audit_coverage_invert.py` is built into `J-2` (+`crowd_heat.json` in the output and the phase gate), `commit_archaeology.py` into `J-1` (+ the full-history condition). The `cold`→`hot` queue rule is fixed in the skill and in the `active_divergence_unresolved` gate | cheap, plain scripts | ✅ |
| **2** | ✅ **DONE 2026-07-27.** The `DEPTH-TRACE` field in the ledger template (boundary / predicted / observed / **fan-in**), the gate `active_depth_t12_incomplete` (a claim of ≥3 layers without an honest trace + a posthoc prediction + a miss without a `D-NN`), **K1 fixed**: `depth_spin` counts a new `predicted/observed` pair as progress | a gate edit | ✅ 33/33 depth+T12; recall give-up 14/14, FP 0/15 — did not drop |
| **3** | ✅ **DONE 2026-07-28, BUT REBUILT.** Analysis on the ground: `hunt_driver.workflow.js` was not just an orphan but a SECOND loop engine (its own rounds, axis rotation by a counter — a rejected technique, its own HUNT-EXIT, ledger writes by subagents). The operator's decision: the driver is **retired**, replaced by two NARROW fan-outs that return data: `scout_fanout.workflow.js` (schema-forced leads, partitions by `I-NN`) and `gapmap.workflow.js` (loop-until-dry over unread score-4/5). Anti-spin was solved differently from the plan: while background work is in flight the hook **releases** the turn (a notification will resume it), with a 15-minute watchdog against a lost agent. Detection — a launch↔`<tool-use-id>` pair in the notification (the ack arrives immediately, so "tool_use without a result" does not work) | medium | ✅ 12/12 watchdog; give-up recall 14/14, FP 0/15 |
| **4** | ✅ **METHODOLOGY PART DONE 2026-07-28.** T11 in mythos (`Technique 11`, phase 1); `J2` in deephunt expanded from "break the invariant" into a **fuzzer GENERATOR before a hypothesis** (input = the model's `I-NN`, anti-tautology gate, a found sequence = a machine `D-NN` → `## Divergences`); economic `I-NN` tied into `J4` (named-sequence filter, correction 7); the skeleton `scripts/web3/hypothesis/harness_from_invariant.md` (fizz/Trident/T8) was created. **🔴 A desk smoke test exposed a broken link (2026-07-28):** `invariant_generator.py` parsed only the legacy format `## I1:`, while `J2` now feeds it `system_model.md` with `I-NN` in a 12-column TABLE → it extracted 0 invariants. The fix: `_parse_model_table()` (a table parser, with priority over legacy); a smoke test on a model with filled `I-01`/`I-03` → both skeletons were generated, the formula+`file:line` carried through, the function name is valid (`invariant_i01`). **The combat wiring `I-NN`→property (filling Handler/actors/check + a fizz run) is per-target by nature, on a live stateful hunt** (the same place as the full fan-out) | expensive, per-target | ✅ methodology part + desk smoke of the generator; a combat fizz run — on a live target |
| **5** | ✅ **DONE 2026-07-28.** `blind_spots.md` was developed (BS-01/02/03 + a "Mechanism closure" section); a silent generator is closed by an **escalation in the reason of the MODEL gate** (zero `D-NN` → the §10 table + a mandatory entry in `blind_spots.md`), NOT by a hard block (the axiom "bugs are everywhere" + deadlock risk); the §10 calibration fields are documented in `calibration_log.md` (`type: hunt_outcome`: `origin`/`dup`/`detector_status`/`pred_misses→dnn`/`ttfd_h`/`silent_generator`/`blind_spot_logged`), the capture point is `origin:` in `H-NN` | cheap | ✅ the suite is green, no new block-0 points |

**The `model_eval` scorer (manual → auto) is the only remainder, it does NOT block:** the `model_eval:` block in
`regression_manifest.yaml` is filled in (3 cases of phase 0), but `regression_replay.py` does not know about it —
the run is manual. An auto-scorer is separate work, it will come when the corpus grows to ≥10 cases (it is replenished
by every analyzed third-party bug). Until then measure-don't-feel is held by a manual rerun of phase 0.

### 🔴 Where the SEVEN ideas A-G went (so they are not lost)

| Idea | Lives in technique | Artifact | Phase | Enforcement |
|---|---|---|---|---|
| **A** `invariant_library.md` — the model as capital | T13 (+feeds T10-B) | `methodology/invariant_library.md` (cross-hunt, key = primitive) | **1** (created) → replenished by every hunt | §11.4: on `HUNT-EXIT` — a gate "primitive `I-NN` appended to the library" |
| **B** `crowd-heat` — dedup by invariant | T14-A → a field in the `I-NN` table | the `## Invariants` section in `system_model.md` | **1b** (together with T14) | §11.4: source #1 cannot be closed with unwalked `hot` ones |
| **C** Test-Inversion — the unwritten negative | T10, beat 4 (ranker/paths) | `## Missing Negatives` in `system_model.md` | **1** | §11.4: an `I-NN` with status `ENFORCED` without enumerated negatives = not checked "on all paths" |
| **D** Depth Fan-In — who ELSE touches the state | T12 (the 5th layer field) | a DEPTH-MAP row | **2** (together with the T12 hybrid) | §11.4: a layer without `fan-in:` is not credited; fan-in>1 with `ENFORCED` → an automatic suspicion of `ENFORCED-PARTIAL` |
| 🔴 **E** `fingerprint:` — `SUBSTITUTED` computable by grep | T13/idea A (a library column) → the canon operator in T10 | the 3rd column in `methodology/invariant_library.md` | **1** (the column) → the script `canonical_fingerprint.py` only at ≥10 entries | §11.4: `active_library_not_updated` is extended — an entry without `fingerprint:` is incomplete |
| 🔴 **F** `pred:` against fact — T12 at the model level | T10, beats 2→3 | the `pred:` column in the `I-NN` table | **1** | §11.4: `active_model_pred_posthoc` — `pred:` is empty or appeared after `status:`; `pred=ENFORCED`→fact `ABSENT/SUBSTITUTED` = the top `D-NN` rank |
| 🔴 **G** phase 0 corpora — a growing eval set | outside the techniques: method regression | `phase0_blind/` + `regression_manifest.yaml` (the `model_eval:` block) | **1** (registration) → replenished by every ingest | §11.6: an edit to the T10 prompt/template without a rerun of the corpora = "feels like progress" |

### 🔴 Where the SEVEN corrections earned by phase 0 went (so they do not dissolve into the prose of §2)

The conclusions of phase 0 were written into §2 — but implementation follows the §11 map, and they did not arrive there at first.
The table closes this gap: each correction has a place in the template/checklist and an enforcement point.

| # | Correction | Lives in | Artifact | Enforcement |
|---|---|---|---|---|
| 1 | **Specificity limit ≤12 `I-NN`, no more than half non-`ENFORCED`** | T10, beat 2 | the header of `## Invariants` in the T13 template + the cold modeler's prompt | gate `active_model_shotgun`: >12 `I-NN` OR a non-`ENFORCED` share > 50% → block (a shotgun list = slop) |
| 2 | **The operator "is the mechanism canonical?"** | T10, beat 3 | a checklist item of `independent_model_first.md` | gate `active_model_canon_unchecked`: an `I-NN` with the source "standard/spec" without the mark "mechanism verified" |
| 3 | **The 5th status `SUBSTITUTED`** | the enforcement schema | the `I-NN` table in the T13 template | included in `active_divergence_unresolved` on a par with `ABSENT`; the rank is **above** a plain `ABSENT` |
| 4 | **Convergence of `I-NN` on a component = a rank signal** | T10, beat 4 (ranker) | **the `component:` field** in the `I-NN` table — without it the signal is incomputable | a ranker multiplier; computed by machine (a counter by `component:`) |
| 5 | **Blind modeling — on a SENIOR model** | T10, anti-anchor | an explicit `model:` in the cold subagent call (`J-M`, `hunt_driver.workflow.js`) | review at introduction: the scout tier missed on case C, the senior one hit |
| 6 | 🔴 **The `check:` field — what exactly to go and check in the code** | T10, beat 2 | a column in the `I-NN` table | gate `active_model_check_missing`: an `I-NN` without `check:` is not considered built |
| 7 | 🔴 **An economic `I-NN` without a concrete sequence → `## Long Tail`, not into `D-NN`** | T10 + §5 (2 classes) | a rule in the header of `## Invariants` | gate `active_model_econ_slop`: an `ABSENT` economic `I-NN` without a named permissionless sequence is not credited as a divergence |

**Correction 6 — why it is not cosmetic.** In case A the modeler FORMULATED the mechanism less precisely than
the ground truth (said "one side is adjusted, the other is not", while in fact it was a scale mismatch
`10000` versus `1000^2`). The hit still happened — **because the check it prescribed
("make sure that BOTH brackets use the same constants") led to the defect regardless of
whether the mechanism was guessed right**. Conclusion: the value of an `I-NN` is not in the correctness of the guess but in the **executability
of the prescribed check**. It is the model analogue of our falsifier: a formula without a `check:` is an opinion.

**Correction 7 — why it is mandatory.** In case C almost all `ABSENT` turned out to be economic
premises marked "not expressible in code": formally true, practically useless, and precisely
they inflated the list to 19. This is a direct conflict with §5 ("economic invariants are equal"): without
the filter, equality turns into a free generator of `ABSENT`. The filter is a **named sequence**:
an economic invariant lives as a divergence only if a concrete permissionless
sequence that breaks it is named (like a circular mint→redeem). Otherwise — `Long Tail`.

**The order is not accidental:** T13+T10 are cheap and **provide the input** for the rest. T14 does not depend on the model, so
it goes in parallel and earlier — it is the only one that works even where there is no corpus. The graph upgrade goes AFTER
phase 1, otherwise scouts will again go off reading files instead of checking invariants. T11 goes last — it
consumes invariants that simply do not exist before T10.

### Phase 0 redone: a blind test instead of a contaminated one

**The defect of the earlier scheme:** T10 cannot be validated on our own solved cases — these are cases
that I **solved myself**. I know the answer, so I will "build" exactly the invariant that leads to it.
That is not a check of the method but an imitation of it.

**The blind protocol:**

1. Take a **third-party** known bug that we did not find — from Solodit / DeFiHackLabs / SlowMist,
   with a known root cause. Three of them, of different classes.
2. Give a cold subagent **only the corpus**: docs, spec, tests, README — **without the implementation code**
   and without mentioning that the bug exists.
3. Ask it to build `I-NN` and predict where enforcement is most likely `ABSENT` /
   `ENFORCED-PARTIAL`.
4. **Only afterwards** compare: did the predicted status land on the place of the real bug.

This is falsifiable: an agent cannot fit an answer it does not know. A hit of ≥2 out of 3 — the method
works. 0-1 — we redo the method rather than deploy it.

### 🔴 Idea G — phase 0 is NOT one-off: the corpora as a growing eval set

**What was missed.** Phase 0 was done as a go/no-go and closed at that. But its artifact — three
anonymized corpora + ground truth **recorded BEFORE the predictions** — is the only honest
measure of the method that we have at all. Discarding it after a single use is the same
as discarding `ENFORCED` invariants (exactly the disease that idea A treats).

**Three uses, each cheap:**

1. **Regression for T10 edits.** Any change to the T10 prompt / template / checklist is rerun
   against A/B/C. The baseline is fixed: A — hit@2, B — hit@1-2, C — hit@1 on the senior tier.
   Without this, an "improvement" of the method is a feeling, not a fact (measure-don't-feel). **Especially needed for
   the ≤12 limit:** it raised precision in ONE run, and its recall cost is not measured.
2. **The corpus grows for free.** We regularly analyze third-party bugs anyway (SlowMist / Solodit /
   DeFiHackLabs ingests). The rule: an analyzed bug with a clear root cause turns, in ~20 minutes, into a
   corpus case — a spec without code + ground truth recorded BEFORE the run. In a year this is an eval set
   that nobody else has, and it covers the classes where we are weak (cross-checked against `blind_spots.md`).
3. **It makes the policy "a model release = a re-audit window" measurable.**
   Right now it prescribes re-running known-clean targets — expensive, slow, with no number at the output.
   With the corpora the delta of a new model is measured in an hour: the same blind run, compared against the baseline.
   Phase 0 already showed that the model tier decides (`sonnet` missed, the senior one hit) — so
   the quantity worth measuring is real.

**The anonymization rule (otherwise the eval set will go stale):** a corpus must not name the protocol — otherwise
the model recognizes the incident by name, and we measure the recall of its memory, not the method. In phase 0 this was observed,
going forward it is a mandatory condition for accepting a new case.

---

## 9. Risks (honestly)

| Risk | Mitigation |
|---|---|
| **T10 is a hypothesis, not a fact.** There is no data that the method will work; indirectly — Orchard and a mock-vs-prod divergence (= a divergence between model and implementation) | Phase 0 = a **blind** validation on third-party bugs BEFORE deployment |
| **T12 hybrid: a new Goodhart** — I will start producing `predicted/observed` formally, retroactively | the prediction is written BEFORE the crossing (the gate checks the order); a heavy artifact only for layer ≥3 |
| **T14-A: the audit map lies in the other direction** — a report does not list everything the auditor looked at and did not find; "a hole in the map" ≠ "nobody looked" | treat it as a **rank bonus**, not as a guarantee of un-dup; a dedup check is still mandatory before submission |
| **T14-B: churn signals are noisy** — an active file may simply be the core of the product | use only in **intersection** with another source (§6), not as a single pointer |
| 🔴 **The ≤12 limit can cut off a real invariant** (in phase 0 it raised precision, but that is ONE run — the flip side of a limit is always recall) | surplus `I-NN` are **not deleted but moved into `## Long Tail`** of the same file: they do not participate in ranking and are not counted by the gate, but remain available on a pivot/T9. Plus the limit is rechecked on the phase 0 corpora on every T10 edit (§11.6) |
| T10 lengthens the start of a hunt (a model before code = a delay of the first lead) | a 30-45 minute time-box; the model is a draft, completed along the way |
| The docs lie → a "divergence" is false | `D-NN` = a **lead**, not a finding; it goes through the ordinary T2 STATE A→D + T4 |
| Double bookkeeping: two files, I will forget to maintain `system_model.md` | the entry hook creates the file; completeness-gate: zero `I-NN` at the exit = a block |
| **A background `Workflow` × the Stop hook** `hunt_completeness_gate.py`: while the workflow is in the background, the ledger does not move → anti-spin (8 blocks / 30 min) may release the loop in the middle of a hunt = a silent death of the autonomous mode | **the main technical risk of phase 3**; fix before deployment, with a test on a live hunt |
| `ledger_first_nudge.py` hangs on PostToolUse for `Task`, not for `Workflow` → LEDGER-FIRST enforcement will go blind silently | edit simultaneously |
| An opt-in gate: `Workflow` cannot be called without permission; an ad-hoc hunt by a link will not get it | **keep both paths**, do not delete the Task fan-out |
| 🔴 **`depth_spin` × T12**: the gate punishes "stayed on the layer because I did not understand" — a correct T12 outcome | K1 in §11.4: count a new `predicted/observed` pair as progress too |
| 🔴 **The model gate × "when not to apply T10"**: a deadlock on dapphunt / web2 / a small contract | K2 in §11.4: the sentinel `MODEL: N/A — <reason>` (the pattern is already in the code) |
| 🔴 **Phase 3 extends dead code**: the driver is an orphan, nobody calls it | wiring step 0 in §11.5, before any driver edits |
| A "source of the PLACE" metric without a capture point = self-deception | the `origin:` field in the body of `H-NN` → transferred to `calibration_log` at the exit |

---

## 10. Metrics (measure, don't feel)

Kept in `calibration_log.jsonl`:

1. **The share of DUPLICATE among submitted** — the main one; it is what divergence-first and T14-A treat.
2. **The share of findings by source of the PLACE** (§6): `D-NN` · attention-gap · prediction miss · code reading.
   ⚠ **A capture point is needed, otherwise the metric is dead:** the `origin:` field is mandatory in the body of every `H-NN`
   (template `hypotheses_template.md:176`), and at `HUNT-EXIT`/submission it is transferred to
   `calibration_log.jsonl`. Without this §10 item 2 is unmeasurable, and the phase gates that refer to it are decoration.
3. **Recall on `regression_manifest.yaml`** — does not drop in any phase, otherwise a rollback.
4. Detector precision: the share of `ABSENT` / `ENFORCED-PARTIAL` / `SUBSTITUTED` that grew into a
   confirmed High/Crit (**separately for the three statuses** — a working hypothesis: `SUBSTITUTED` is the most accurate
   of all, since it is the only status where the defect is in the foundation, not in a particular path).
5. **The share of prediction misses** (`predicted ≠ observed`) and how many of them became `D-NN`.
6. **Un-dup tracking per generator** (FDE Plan 6 §52 light) — the share of CONFIRMED findings whose
   `undup_origin`/`origin:` points to a specific un-dup generator (`assumption-mining` /
   `negative-space` / `third-party-seam` / ... — the full vocabulary is in `blind_spots.md` "Un-dup Generators —
   Pool-Seed"). Read at the revision (the same point that triggers the "Revision" section in `blind_spots.md`):
   a generator with 0 confirmed over N hunts where it was `RUN` is **silent**, recorded in the same place as a silent
   `I-NN`/`D-NN` generator (the §10 table above); a generator with a steady share of confirmed is **productive**,
   and its seed priority in `## Un-Dup Sweep` (the §51 matrix) is moved forward. It closes the self-improving loop
   specifically on un-dup, and not only on recall/precision in general.

### Time-to-first-divergence — a diagnostic of the SYSTEM, not of the target

**The operator's position (2026-07-27), accepted as the frame:**

> "Bugs are everywhere — that is a fact. In some places they are harder to find, in some places we cannot find them at all — but only
> because the system is not perfect yet and is weak in something. This update will strengthen it."

Hence the rule for reading the metric: **zero `D-NN` over N hours means "our detector did not fire", not
"the target is empty".** The metric does not have and will not get the right to end a hunt — that would directly contradict
the axiom. It is read as a **signal to escalate the method**, with the concrete question "which generator is silent":

| What is silent | Diagnosis | Escalation |
|---|---|---|
| zero `I-NN` | the corpus was not assembled | a surrogate corpus: analogue → tests → economic meaning (T10) |
| `I-NN` exist, all `ENFORCED` | did not check "on all paths" | run the `ENFORCED-PARTIAL` operator on each |
| `D-NN` exist, all of low rank | the ranker does not see value | walk backward from the value transfer, recompute value-weight |
| attention-gaps are empty | there were not enough reports/history | T10-B family diff (a reference instead of an audit) |
| everything is silent | the **method** is silent, not the target | a T9 cold restart on a new axis — and **record the gap in `blind_spots.md`** |

Every such silence is an entry into `blind_spots.md` (phase 5): a class that the system has **never** found
over 40+ hunts is not "it does not exist" but our blind zone. `calibration_log` measures the
accuracy of findings; `blind_spots.md` measures **class coverage** — what we do not measure at all.

---

## 11. MAP OF EDITS — where exactly to change and what to add

> Paths verified on the real tree 2026-07-27. Line numbers are as of the time of writing, check when editing.

### 11.0 What ALREADY exists (do not build from scratch — extend)

A survey of the tree gave three facts that make the plan much cheaper:

1. **`bug-bounty-toolkit/scripts/_methodology/hunt_driver.workflow.js` ALREADY EXISTS** — a working
   Workflow driver with phases `Depth / Verify / Rotate`, a `schema`-forced return (`ROUND_SCHEMA`,
   `VERDICT_SCHEMA`), a budget guard and rotation of T9 axes. Phase 3 = an **extension**, not writing from scratch.
2. **A panel of lenses is ALREADY implemented in it** (`lenses = ['correctness/guard', 'severity/de-minimis',
   'scope/reachability']`, `hunt_driver.workflow.js:123-131`) — but with a **majority vote**
   (`if (survived >= 2 && highEnough)`, ~`:137`). This is exactly what we decided to throw out: a finding
   where each piece of evidence separately is harmless (cross-thread / depth-ceiling) will not gather 2 of 3.
   **The edit is pinpoint, one branch of a condition.**
3. **`J1: Invariant Discovery` and `J2: Invariant Break` in `/deephunt` are already about invariants** —
   T10/T11 are not bolted on the side but **unfold the existing phases**: J1 moves FORWARD
   (before reading the code) and becomes `J-M`, J2 gets the fuzzer-as-generator.
4. 🔴 **`hunt_driver.workflow.js` is an ORPHAN (found in the final recheck 2026-07-27).** By grep
   across the whole tree: the file is mentioned NOWHERE except this plan — not in `deephunt.md`, not in `hunt.md`,
   not in `dapphunt.md`, not in `CLAUDE.md`, not in any hook. Nobody calls it. So phase 3
   "extend the existing driver" extends **dead code**, and its metric will be empty.
   **The mandatory step zero of phase 3 is WIRING:** an explicit beat in `/deephunt` (a launch condition +
   `Workflow({scriptPath:'bug-bounty-toolkit/scripts/_methodology/hunt_driver.workflow.js',
   args:{slug}})`) and a line in `CLAUDE.md` §4. Without wiring, driver edits are not verifiable at all.

### 11.1 Methodology — the core

**`bug-bounty-toolkit/methodology/mythos_techniques.md`**

| What | Where exactly |
|---|---|
| The mandate **DIVERGENCE-FIRST** (next to DEPTH-LEAD-FIRST) | inside `## Technique 0 — Hunt Mandates` (`:9-85`) |
| SELECT: a new priority **1 = `D-NN`** | inside `## Hunt-Loop — Operating Spine` (`:86-246`), the SELECT block |
| A reference "T1 is not the only source of SELECT, see T10" | the header of `## Technique 1` (`:247`) |
| **T4 → a panel of lenses WITHOUT majority**: a kill only by a hard falsifier `file:line`; "three said it does not look like it" = `[CONTESTED]` | inside `## Technique 4 — Two-Agent Verifier Pass` (`:542-670`) |
| **NEW `## Technique 10-14`**: T10 Independent Model First (+T10-B Family Invariant Diff, +anti-anchor **on a senior tier**, **+5 statuses incl. `SUBSTITUTED`**, **+the operator "is the mechanism canonical?"**, **+the ≤12 limit**, +a ranker **with convergence**, +feedback, **+idea C Test-Inversion**, **+idea F `pred:`→fact**) · T11 Harness as Generator · **T12 Predictive Boundary Crossing** (a hybrid of boundary and prediction, **+idea D Depth Fan-In as the 5th layer field**) · T13 `system_model` (2 classes of invariants, **+idea A `invariant_library`** with the **`fingerprint:` column of idea E**) · **T14 Attention-Gap Mapping** (A: inversion of the audit map · B: commit archaeology · **+idea B `crowd-heat` with ALL `hot` into the queue, not into a filter**) | insert between the end of `## Technique 9` (`:953-1007`) and `## Per-Skill Integration Map` (`:1008`) |
| Rows T10-T14 in the integration table | `## Per-Skill Integration Map` (`:1008-1019`) |
| The SELECT table "three objective generators of a PLACE + the source-intersection rule" | the same Hunt-Loop Spine block, next to the `D-NN` priority |

**`bug-bounty-toolkit/methodology/hypothesis_taxonomy.md`** — an optional and minor edit: mark
that an `ABSENT` invariant from T10 is a legitimate entry into the taxonomy on a par with code-read (so that the Layer-1
cross-check is applied to it as well).

### 11.2 Artifacts and templates

| File | Action |
|---|---|
| `bug-bounty-toolkit/sessions/_methodology/system_model_template.md` | **CREATE** — the T13 template (9 sections from §5, **5 statuses** of enforcement incl. `SUBSTITUTED`, class `state\|economic`, the fields `tests: N` and **`component:`**, a header with the **≤12 limit**) |
| `bug-bounty-toolkit/sessions/_methodology/independent_model_first.md` | **CREATE** — the operational T10 checklist (modeled on `scout_fanout.md`): corpus → I-NN (**limit ≤12**) → **5 statuses** → **the operator "is the mechanism canonical?"** → ranker (**incl. convergence**) → feedback; blocks "no corpus", "T10-B family diff", "anti-anchor (**senior tier**)", "when NOT to apply" |
| `bug-bounty-toolkit/sessions/_methodology/attention_gap_mapping.md` | **CREATE** — the T14 checklist (A: how to build an attention map from reports and look for holes · B: the list of git signals of haste) |
| `bug-bounty-toolkit/sessions/_methodology/blind_spots.md` | **CREATE already in phase 1** (develop in phase 5) — bug classes that we have **never** found; maintained after each hunt and from the "silent generators" of §10. The first entry was already earned by phase 0: "a canonical mechanism is by default considered present" |
| 🔴 `bug-bounty-toolkit/methodology/invariant_library.md` | **CREATE (idea A), phase 1** — a cross-hunt library of invariants by **primitive** (`ERC721/OZ-v5`, `Wormhole-NTT`, `UniswapV2-fork`, `Anchor-PDA`, `Cosmos-SDK`, `halo2-gadget`, `Pyth-pull`, `QBFT`); under each — the invariant + how the REFERENCE enforces it with the reference's `file:line` + the **`fingerprint:` of the canonical mechanism (idea E)** — an import/base contract/signature/storage shape by which a substitution is caught by grep. It lives in `methodology/`, NOT in `sessions/_methodology/`, because it outlives hunts |
| `bug-bounty-toolkit/sessions/_methodology/hypotheses_template.md` | **EDIT**: in `## Loop State` (`:98-136`) add the fields `Model:` (`I-NN total / ABSENT / ENFORCED-PARTIAL / current D-NN`) and `Prediction-miss:` (a miss counter → auto-`D-NN`); in DEPTH-MAP — the fields `boundary/predicted/observed` **+ `fan-in` (idea D)**; in `## Scout Fan-Out` (`:137`) — a note "partitions are sliced by `I-NN` if a model is built"; in the body of `### H-{NN}` (`:176`) — the field `origin:` (the source of the PLACE, for the §10 item 2 metric) |
| `bug-bounty-toolkit/sessions/_methodology/system_model_template.md` | the sections **`## Missing Negatives`** (idea C) and **`## Long Tail`** (mitigation of the ≤12 limit) + the fields `crowd-heat` / `lib:` / **`component:`** / **`pred:` (idea F)** / **`check:` (correction 6)** in the `I-NN` table — design with them from the start, do not bolt on later |

**The decision on where `D-NN` lives:** divergences live **only** in `system_model.md`; in the ledger — a reference
and a counter in Loop State. One source of truth, no double bookkeeping.

### 11.3 The `/deephunt` skill — `.claude/commands/deephunt.md`

| What | Where exactly |
|---|---|
| **NEW phase `J-M`: Independent Model First (T10)** — lettered, outside the numeric scale, so as not to break J-2→J9. Insert **between** `### J-2: Audit Reports Mining` (`:132-179`) and `### J-1: Deep Reconnaissance` (`:180`). Rationale: the corpus = audits (J-2) + docs, while recon (J-1) already touches code. Inside: anti-anchor (the model is built by a cold agent), T10-B family diff, "no corpus", "when NOT to apply" | between `:179` and `:180` |
| **T14-A is embedded in the EXISTING `### J-2: Audit Reports Mining`** (`:132-179`) — not a new phase but an **inversion of the existing one**: besides "what was found", build a map of "where they looked" and look for its holes | `:132` |
| **T14-B is embedded in `### J-1: Deep Reconnaissance`** (`:180-235`) — running `commit_archaeology.py` as a standard recon step | `:180` |
| `### J1: Invariant Discovery` (`:359-380`) → **rewrite into "reconciling the `I-NN` from `J-M` with the code"** (an enforcement-map across **all 5 statuses**, incl. the operator "is the mechanism canonical?"), not "discovering invariants from scratch" | `:359` |
| `### J2: Invariant Break` (`:381-420`) → **T11**: a harness from `I-NN` as a GENERATOR, run BEFORE a hypothesis; anti-tautology ("the invariant from the model, not from the code") | `:381` |
| `### J0.5: Parallel Specialty Fan-Out` (`:341-358`) → partitions **by invariants**, called via Workflow | `:341` |
| `### J5.5: T4 Two-Agent Verifier Pass` (`:531-561`) → a panel of lenses, a kill by falsifier | `:531` |
| `### ⛔ COMPLETENESS-GATE` (`:921-958`) → add an item "the model is built, all `I-NN` are mapped, open `D-NN` are worked out" | `:921` |
| `## Reference Files` (`:1009-1026`) → add `independent_model_first.md`, `system_model_template.md`, `depth_engine_plan.md` | `:1009` |
| The Solana mirror: `S-M` next to `## Solana Phase Variants (S-2 → S9)` | `:750` |

**`.claude/commands/hunt.md` and `.claude/commands/dapphunt.md`** — one reference line to `J-M`/T10
(a light edit, so that the beat is not lost when entering not through `/deephunt`).

### 11.4 Hooks — enforcement (`bug-bounty-toolkit/scripts/hooks/`, wired in `.claude/settings.json`)

| File | Edit |
|---|---|
| `hunt_entry_gate.py` | create `sessions/{slug}/system_model.md` from the template **next to** `hypotheses.md`; in the forcing reminder add the `J-M` beat before reading code |
| `hunt_completeness_gate.py` | **new gates** modeled on the existing `active_ledger_*` (`:403-736`): `active_model_missing` (no file / zero `I-NN`) · `active_model_unmapped` (an `I-NN` without an enforcement status) · `active_model_no_partial_pass` (all `I-NN` = `ENFORCED`, not one "checked on all paths" → the `ENFORCED-PARTIAL` operator was not run) · `active_divergence_unresolved` (an open `SUBSTITUTED`/`ABSENT`/`ENFORCED-PARTIAL` without DRIVE — modeled on `active_ledger_composite_abandoned`, `:589`) · **`active_model_shotgun`** (>12 `I-NN` or a non-`ENFORCED` share > 50% — correction 1 of phase 0) · **`active_model_canon_unchecked`** (an `I-NN` from a spec/standard without the mark "canonical mechanism verified" — correction 2 of phase 0) · **`active_model_check_missing`** (an `I-NN` without the `check:` field — correction 6) · **`active_model_econ_slop`** (an economic `ABSENT` without a named permissionless sequence — correction 7) · **`active_model_pred_posthoc`** (idea F: `pred:` is empty or set after `status:` — checked by order, like `predicted:` in T12) |
| `hunt_completeness_gate.py` | **T12 hybrid**: `_depth_layers` (`:308-328`) and `active_ledger_depthmap_*` (`:608-736`) — a layer counts only in the presence of a **boundary type** + **`predicted:`** + **`observed:` with an artifact**; a separate gate `active_depth_prediction_posthoc` (a prediction cannot appear later than the observation — check the order/emptiness of `predicted`) |
| `hunt_completeness_gate.py` | **a prediction miss = an auto-`D-NN`**: `predicted ≠ observed` without a created `D-NN` or without the mark "did not understand → digging this same layer" → a block (otherwise a miss is silently swallowed) |
| `hunt_completeness_gate.py` | **⚠ anti-spin × background Workflow** (the main risk of phase 3): `active_ledger_stale` (`:754`) and the "8 blocks / 30 min" counter must not fire while a Workflow is running in the background — otherwise the loop is released in the middle of a hunt |
| `ledger_first_nudge.py` + `.claude/settings.json` | the PostToolUse matcher `Task` → **`Task\|Workflow`**, otherwise LEDGER-FIRST will go blind silently |

#### 🔴 Gates for ideas A/B/C/D (phases 1, 1b, 2)

| Gate | Idea | Block condition |
|---|---|---|
| `active_model_negatives_missing` | **C** | there is an `I-NN` with status `ENFORCED`, but the `## Missing Negatives` section is empty → the "on all paths" operator was not run |
| `active_model_hot_unprocessed` | **B** | source #1 is declared worked out, while `hot` divergences remain unwalked. **This is NOT a veto by crowd-heat but a ban on abandoning the queue** — "it is crowded there" does not count as a falsifier |
| `active_depth_fanin_missing` | **D** | a DEPTH-MAP layer without the `fan-in:` field is not credited (in the same `_depth_layers` edit as T12) |
| `active_library_not_updated` | **A** | `HUNT-EXIT` with a non-empty model, but the library was not replenished with a single primitive entry → knowledge is thrown away again |

#### 🔴 Gate consolidation — 12 checks, but NOT 12 functions (decided at the final reconciliation)

The list above gives **twelve** model checks. Implementing them modeled on the existing
`active_ledger_*` (one function per gate, `hunt_completeness_gate.py` is already 1474 lines, 11 gates)
means doubling the file and creating 12 separate replay tests. That is a new risk in itself: the more
independent block points, the higher the chance of a deadlock out of nowhere, and a deadlock in autonomous mode
is more expensive than a skipped check.

**The decision — three functions instead of twelve**, by the nature of the check, not by the number of rules:

| Function | What it covers | Nature |
|---|---|---|
| `active_model_incomplete` | `missing` · `unmapped` · `shotgun` · `canon_unchecked` · `check_missing` · `econ_slop` · `negatives_missing` | **completeness of the artifact** — all read one file, return a LIST of reasons in one message |
| `active_model_order_violation` | `pred_posthoc` (idea F) | **order** — `pred:` could not have appeared after `status:`; the same nature as `active_depth_prediction_posthoc` in T12, implement with one piece of code |
| `active_divergence_unresolved` | abandoned `SUBSTITUTED`/`ABSENT`/`ENFORCED-PARTIAL` · `hot_unprocessed` (idea B) · `library_not_updated` (idea A+E) | **abandoned work** — modeled on `active_ledger_composite_abandoned` (`:589`) |

The sentinel `MODEL: N/A — <reason>` (K2) removes all three at once — one check at the entry, not three.

#### 🔴 K6 — the enforcement hook was BLIND all this time (found 2026-07-28)

While checking phase 3, I found that `ledger_first_nudge.py` listens to the **`Task`** tool, while in this harness
the subagent tool is called **`Agent`**: across all transcripts `Agent` = 970 calls, `Task` = 0.
The hook never fired **even once** since it was written. A second layer of the same blindness: the "ledger is empty" detector
matched `H-03` from the EXAMPLES in the template itself (`Depth-Lead: {… H-03 — 3/5 …}`) → a fresh ledger looked
filled in, and the nudge would have stayed silent even with the right name. Both layers are fixed (`Agent|Task|Workflow` in the matcher
and in the body; `{...}` placeholders are cut out before the check), the behavior is confirmed by a run.

**A lesson stronger than the bug itself:** this is exactly the failure the plan predicted for `Workflow`
("will go blind silently") — but it had ALREADY happened and lived unnoticed. Any hook tied to a tool name
or to the shape of a template must have a run proving that it fires, not only the absence of false positives.

#### 🔴 Two conflicts exposed DURING IMPLEMENTATION (2026-07-27) — fixed in code

**K4. The "at exit" gate physically could not fire.** `active_library_not_banked` was designed to check
library replenishment at `HUNT-EXIT` — but `main()` released the turn on `ledger_success_exit(...)`
BEFORE any checks, i.e. after the exit token the hook is silent by construction. **Fix:** the library
check sits INSIDE the success branch, before `sys.exit(0)`; it is unblocked by the line `LIBRARY: updated`
(or `LIBRARY: N/A — <reason>`) in the ledger. A lesson of a general kind: an "at exit" gate must be placed in the exit
branch itself, otherwise it is decoration.

**K5. The gate order shadowed the depth cluster.** The MODEL cluster, placed before the depth-quality gates,
intercepted three scenarios of the e2e smoke: an instance in the middle of DRIVE received the message "build a model"
instead of the concrete "the depth map is a placeholder". **Fix:** the MODEL cluster stands AFTER depth-quality.
Rationale: the model gate is persistent (it will fire on the next turn too), while the depth gates address
the hypothesis IN WORK — their message is more concrete and more urgent. Caught by the smoke, not by reasoning.

#### 🔴 Three conflicts with the existing code (exposed by the final recheck 2026-07-27)

**K1. `depth_spin` (`:1172-1217`, `K=4`) punishes CORRECT T12 behavior.** The gate counts a streak
of blocks where the ledger was written but `_max_depth` and `_t4_count` did not grow, and on the 4th issues a depth order.
But the third outcome of a T12 miss — "**I did not understand the system → digging THIS SAME layer, the counter does not grow**" —
is exactly that state. I.e. two of our enforcements will pull in different directions: T12 tells you to
linger on a layer, `depth_spin` interprets lingering as elaboration. **Fix (one line in the streak
reset condition):** count a new `predicted/observed` entry as progress TOO — i.e. `streak = 0`
at `md > p_md OR t4 > p_t4 OR po_count > p_po`. Otherwise phase 2 will quietly break phase 2.

**K2. The model gates will block targets where T10 forbids itself.** The entry hook arms the marker on
ANY hunt URL, including a `/dapphunt` frontend, web2 and a small contract (<300 LOC) — and for them §2 explicitly
says "do NOT apply T10". The `active_model_missing` gate head-on = a deadlock out of nowhere.
**The fix — the `N/A` sentinel, exactly as already done for scout / impacts / BOUNDARY-MAP / DEPTH-MAP**
(`:420`, `:439`, `:485`, `:687`): the line `MODEL: N/A — <reason>` in Loop State removes the gate.
The pattern is established in the codebase, nothing to invent — but it was not in the plan.

**K3. The entry hook creates files only on the first entry.** `resume = os.path.exists(ledger)`
(`hunt_entry_gate.py:217-226`) — the whole creation block is under `if not resume`. After phase 1 is deployed,
all hunts ALREADY in progress (a ledger exists) will never get `system_model.md`. **Fix:** check
for the existence of the model **independently** of `resume`, with a separate `if not os.path.exists(model)`.

### 11.5 Workflow (graph) — extending the existing one

**`bug-bounty-toolkit/scripts/_methodology/hunt_driver.workflow.js`**

| What | Where |
|---|---|
| 🔴 **STEP 0 — WIRING (see 11.0 item 4): nobody calls the driver right now.** A launch beat in `/deephunt` + a line in `CLAUDE.md` §4. Do it FIRST, otherwise the other edits to this file are unverifiable | `deephunt.md`, `CLAUDE.md` |
| **Remove the majority vote**: `if (survived >= 2 && highEnough)` (`:138`) → confirm if ≥1 lens gives High+ **and none** returned a hard falsifier `file:line`; refuted without a falsifier → `[CONTESTED]`, not a kill. The edit drags along the `log` line `:136` and the finalizer text `:141` (it says "confirmed by majority") | `:138` |
| `VERDICT_SCHEMA` (`:44-52`) → a mandatory `falsifier` field (`file:line`) when `refuted: true` | `:44-52` |
| **NEW phase `Scout`** with `schema`-forced leads, partitions **by `I-NN`** from `system_model.md` | before `phase('Depth')` (`:106`) |
| **NEW phase `GapMap`** — loop-until-dry over unread score-4/5 (the operator insisted) | after `Scout` |
| extend `meta.phases` with the new phases | `:5-9` |

#### 🔴 Three Workflow integration pitfalls (caught by a smoke test 2026-07-28, not by reasoning)

1. **`args` arrives as a STRING, not an object.** The first combat launch died in 48 ms with zero agents
   on our own `args.slug` check. In combat this would read as "the fan-out worked, no leads" — the most
   dangerous kind of failure. **Fix in both scripts:** `const A = typeof args === 'string' ? JSON.parse(args) : (args || {})`.
2. **CRLF breaks a launch by `scriptPath`.** Edits via `io.open(path,'w')` on Windows silently
   convert the file to CRLF; `\r` is a control character, and the permission harness rejects the call
   ("script contains control characters"). The symptom is confusing: the script itself is valid, an inline variant
   of the same code runs. **The rule: keep workflow scripts in LF** (write with `newline='\n'`,
   or normalize), the check — `b'\r\n' in open(p,'rb').read()`.
3. **`scriptPath` is resolved from the CWD.** After a `cd` into `bug-bounty-toolkit` a relative path
   is doubled. Call from the project root or give a path from the root.

Verified by an end-to-end run: a minimal workflow returned a result, so the runtime and agent spawning
work; the logic of both scripts is covered by the local harness `workflow_smoke.mjs` (21/21) —
args normalization, partitions by `I-NN`, `schema` passing, dedup preserving the highest severity,
an agent failure = an uncovered partition out loud, cap 7, queue draining in batches, `dropped_by_cap` surfaced.

#### 🔴 The combat smoke paid off at once: a fan-out over our OWN hooks found 4 DEAD gates (2026-07-28)

The very first real `scout_fanout` (2 read-only sonnet scouts with `schema`-forced leads over
`hunt_completeness_gate.py` / `hunt_entry_gate.py`) returned 4 confirmed defects — all of the same
class "a detector looks at the shape of the REAL template and is silently dead" as K6 (`Task` vs `Agent`).
Synthetic replay ledgers did not catch them because they do not contain the RULES block / the trailing doc of the template.

1. **The T12 gate is dead:** `active_depth_t12_incomplete` took `_DEPTH_LEAD_LINE_RE.search()` = the FIRST
   match, and the first one in every ledger is the RULES header `8. **DEPTH-LEAD-FIRST**` (depth=0) → `claim<3`
   ALWAYS → the gate NEVER fired. Fix: `claim = _max_depth(txt)` (findall+max, the real field).
2. **The P-B gate blocked FOREVER:** the trailing doc on the field line of `BOUNDARY-MAP` contains the literal
   `` `{` `` → `"{" not in m.group(0)` is forever false even after filling in. Fix: check for a `{…}` PAIR
   (`re.search(r"\{[^}]*\}", …)`), a lone `{` in the placeholder's prose does not form one.
3. **A slug collision (High, was LIVE):** `slug_from_url("…/address/0x…")` → `"address"` for any
   contract/chain → two different hunts into one `sessions/address/` + a false RESUME branch. Live
   evidence — a spurious `sessions/address/` created by this very turn (deleted). Fix:
   an explorer segment (`address/token/tx/…`) → `chain-tag_address`.
4. **`_max_depth` phantom 3:** `findall` without skipping a `{` placeholder picked up the example `{… 3/5 …}` →
   poisoned the `depth_spin` baseline. Fix: `if "{" in line: continue` (the same logic as the guarded loops).

All 4 are closed by a **positive** regression in `template_sentinel_check.py` (25/25): on a realistically
filled template the detector MUST COME ALIVE (t12 fires on 5/5, pb-gate blocks on a placeholder / silent
on filled-keep-prose, slugs distinct+stable). A lesson for the test: the sentinel checked only "silent on an
untouched one" — but a dead gate is also silent; a "must fire" pair on a filled template is needed.

### 11.6 Regression and metrics

| File | Action |
|---|---|
| `bug-bounty-toolkit/scripts/_methodology/audit_coverage_invert.py` | **CREATE** (T14-A) — builds an attention map (files/functions/classes) from a set of reports and outputs the **holes** relative to the surface |
| `bug-bounty-toolkit/scripts/_methodology/commit_archaeology.py` | **CREATE** (T14-B) — git signals of haste: commits after the audit date, `quick fix/temp/TODO/hotfix/wip`, churn, a commit without tests, a PR without review, the last commit before a release |
| `bug-bounty-toolkit/sessions/_methodology/regression_manifest.yaml` | 🔴 **REGISTER the phase 0 corpora as the PERMANENT T10 regression harness (idea G).** The format of the existing `cases:` does not fit (they are file-recall and magnitude) — a **separate `model_eval:` block** is needed: `corpus_ref` · `ground_truth_ref` · `baseline` (A hit@2 · B hit@1-2 · C hit@1 on the senior tier) · `tier` · `anonymized: true`. It is replenished by every analyzed third-party bug (~20 min per case); the acceptance condition — **the corpus does not name the protocol**, otherwise we measure the model's memory, not the method. The source — `phase0_blind/corpus_A/B/C` + `GROUND_TRUTH.md` (written BEFORE the predictions → the harness is honest). Any edit to the T10 prompt/template/checklist must be rerun against them, otherwise an "improvement" is unmeasurable. Our own solved cases are **not suitable** for the blind test — contaminated by knowledge of the answer; their place in regression is as a check of the `ENFORCED-PARTIAL` operator |
| `bug-bounty-toolkit/scripts/_methodology/depth_gates_replay.py` | T12 tests (a layer without an artifact is not credited) |
| 🔴 `bug-bounty-toolkit/scripts/_methodology/template_sentinel_check.py` | **CREATED 2026-07-28** — TEMPLATE↔DETECTOR consistency on the real `hypotheses_template.md` / `system_model_template.md`: checks BOTH directions (must fire / must stay silent). Catches the class "the template is edited — the detector silently goes blind", which synthetic replay harnesses do not see. It found a second blindness at once: `active_ledger_thin` (the LEDGER-LIVE guard) counted an untouched template as filled |
| `bug-bounty-toolkit/scripts/_methodology/gate_replay.py` | tests of the new model gates: `missing` · `unmapped` · `no_partial_pass` · `divergence_unresolved` · `shotgun` · `canon_unchecked` · `check_missing` · `econ_slop` · `pred_posthoc` · `negatives_missing` · `hot_unprocessed` · `library_not_updated` (the rule: **first the replay test, then the gate**) |
| `bug-bounty-toolkit/scripts/_methodology/scout_gates_replay.py` | tests of partitions-by-invariants |
| `bug-bounty-toolkit/scripts/_methodology/regression_replay.py` | a run before/after each phase; recall dropped → rollback |
| `bug-bounty-toolkit/sessions/_methodology/calibration_log.jsonl` | the new metric fields from §10 |

### 11.7 The project's `CLAUDE.md` (root) — last, when the mechanics already work

- **§1 "Main hunt mandates"** — add **DIVERGENCE-FIRST** right after DEPTH-LEAD-FIRST
  (breadth finds a thread → **the model and the attention map point to the PLACE** → depth opens it). Also there —
  the operator's wording about time-to-first-divergence: the metric's silence = a weakness of the SYSTEM, not an emptiness of the
  target; it never gives an exit from the loop.
- **§3 "Methodology checklists"** — rows `independent_model_first.md`, `system_model_template.md`,
  `attention_gap_mapping.md`, `blind_spots.md`.
- **§4 "Toolkit map"** — mention `methodology/depth_engine_plan.md`, **`methodology/invariant_library.md`**
  (idea A — a cross-hunt asset, read when a primitive is recognized) and `hunt_driver.workflow.js`
  (with the launch condition — see wiring step 0 in §11.5).

### 11.8 Order of application (so that nothing breaks)

```
Phase 0  → 11.6 (regression_manifest: BLIND third-party cases)         ← cheap, go/no-go
Phase 1  → 11.2 (templates + invariant_library[A+E fingerprint] + Missing Negatives[C] + Long Tail
          + the fields component: / check: / pred:[F] + create blind_spots.md)
          → 11.1 (T10/T13 in mythos, 5 statuses + the canon operator) → 11.3 (J-M, J1)
          → 11.4 (entry hook: K3 creation independent of resume; model gates with the N/A sentinel from K2;
          negatives gate[C]; library gate[A]; shotgun gate + canon gate — corrections 1 and 2 of phase 0)
          → 11.6 (registering the phase 0 corpora as model_eval[G] + a rerun after a T10 edit)
Phase 1b → 11.6 (audit_coverage_invert.py + commit_archaeology.py) → 11.3 (in J-2 and J-1)
          → 11.4 (crowd-heat[B]: the hot_unprocessed gate — a queue, NOT a filter)
          ↑ parallel to phase 1 — T14 does not depend on the model
Phase 2  → 11.4 (T12 hybrid + fan-in[D] + posthoc gate + miss→D-NN + the K1 depth_spin fix)
          + 11.6 (depth_gates_replay)
Phase 3  → 11.5 STEP 0 WIRING → 11.4 (anti-spin × Workflow, matcher) → 11.5 (driver) → 11.6 (replay)
Phase 4  → 11.3 (J2/T11, economic invariants in J4) + 11.1 (T11 in mythos)
Phase 5  → 11.2 (blind_spots.md) + 11.6 (calibration fields)
Final    → 11.7 (CLAUDE.md)
```

The rule for every phase: **first the replay test of the new gate, then the gate itself** — otherwise the gate goes to prod
unverified (we have already been burned this way on `BREADTH_RE`).
