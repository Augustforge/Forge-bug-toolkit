export const meta = {
  name: 'hybrid-scout-fanout',
  description:
    'HYBRID Scout Fan-Out (T10 × open-kritt) — not to be confused with the classic Scout Fan-Out (scout_fanout.workflow.js). Fan-out over invariants I-NN checks enforcement on ALL paths (their map, our divergence meaning), then reduce=synthesis — a senior agent over the WHOLE batch of observations looks for pairs of DISTANT clues (cross-thread) that a single-partition scout structurally cannot express. Returns ranked D-NN threads with depth potential. Does NOT verify and does NOT drive depth — the main agent does that serially afterwards.',
  whenToUse:
    'AFTER the T10 model is built (system_model.md with I-NN is ready) and the surface is multi-subsystem. Replaces the manual cross-thread merge pass, which kept failing. Phase 0 (model) and phase 3 (depth-drive ≥5) are outside this script, done by hand.',
  phases: [
    { title: 'Enforce', detail: 'sonnet fan-out: 1 invariant I-NN = 1..N workers (rerun-N-union / model-diversity) → where it is NOT enforced on all paths' },
    { title: 'Synthesize', detail: 'senior agent, loop-until-dry: pairs of distant clues → D-NN threads (cross-thread)' },
    { title: 'Contest', detail: 'run_dual_approach_contest (§27) — ONE fork (2 threads, shared entry_point, different axis) → independent read-only check of each branch' },
  ],
}

// ═══════════════════════════════════════════════════════════════════════════════
// THE BOUNDARY THAT MUST NOT BE CROSSED (otherwise the hybrid collapses into breadth — a lesson learned):
//
//   THEIR "depth" = a pipeline stage (enforce → synthesize). Processing horizontal.
//   OUR depth-ceiling = interaction layers (call→state→external→hook→accounting). Vertical, downward.
//
// This script lives ONLY in the generation half: find the PLACE (a D-NN thread). It does NOT verify,
// does NOT trace down ≥5 layers, does NOT emit a finding. The DAG ends at emitting the thread. Opening it up
// (single-pick depth-drive) is serial, by hand, AFTER, outside this engine. The terminal stage here
// is NOT "depth done" — that would be false exhaustion. return.next enforces this.
//
// What was taken from open-kritt (phase 2, which we lacked as a stage):
//   • consumesAll-reduce: the agent receives the WHOLE batch at once and "reasons across all results together".
//   • no-finding stub as a first-class output (clean fan-in, commit-or-pass).
//   • model-per-depth tiering: sonnet on enforce (cheap, wide), senior on synthesize (expensive, deep).
// What stayed ours (which they lack):
//   • partitions by INVARIANTS I-NN, not by files (T10 divergence, not "find a bug here").
//   • synthesize looks for a PAIR of distant clues (cross-thread axis 5), rather than ranking single findings.
//   • anti-substitution: their [E] = pred, not fact — the leaf re-checks independently.
//
// Weaknesses and how they are worked around:
//   (1) depth conflation → hard rule: the DAG never reaches exploitation, return.next forces a serial DRIVE.
//   (2) SUBSTITUTED blindness in the fan-out → anti-substitution block in the leaf prompt + the "is the mechanism canonical" operator.
//   (3) reduce loses signal on minified JSON → observations are RICH (not compressed) + loop-until-dry, not 1 call.
// ═══════════════════════════════════════════════════════════════════════════════

// args (object OR string — we normalize both, like scout_fanout):
//   { slug, src,
//     invariants: [{ id:"I-03", check, component, pred, partition_scope,
//                     rerun?: 1..3,            // §40.2 rerun-N-union: same invariant N times, merge-union
//                     models?: ["sonnet",...],  // §55.1 model-diversity: 2+ models, symmetric-diff = priority
//                     axis?: "commodity-subtraction" | "negative-space" }, ...]  (2..7),
//     enforce_model?: "sonnet", synth_model?: "opus", max_synth_rounds?: 4, dual_contest?: false }
//
// Un-dup engineering (§40.2 + §27 + §55.1 + §52 — see sessions/_methodology/scout_fanout.md):
//   - rerun-N-union / model-diversity: as in CLASSIC, but the unit = INVARIANT, not partition; N runs
//     of one invariant are merged (max-severity status + union paths/neighbor_touch) BEFORE synthesis —
//     synthesis always receives EXACTLY one observation per invariant_id.
//   - `models_run` is returned as {invariant_id: [models]} — the main agent writes it into the ledger.
//   - `run_dual_approach_contest` (§27): triggered automatically if synthesis produced 2+ threads on
//     ONE entry point (entry_point) with DIFFERENT axis — an independent read-only check of each branch
//     (not "which is prettier", but whether it holds up in the code). `dual_contest: false` — turn it off.
const A = typeof args === 'string' ? JSON.parse(args) : (args || {})

const slug = A.slug || ''
const src = A.src || ''
const invs = A.invariants || []
if (!slug) throw new Error('HYBRID Scout Fan-Out: args.slug is required')
if (!Array.isArray(invs) || invs.length < 1)
  throw new Error('HYBRID Scout Fan-Out: args.invariants is empty — build system_model.md first (T10, phase 0)')
if (invs.length > 7)
  throw new Error(`HYBRID Scout Fan-Out: ${invs.length} invariants — cap is 7 per wave (the rest goes to WAVE-2)`)

const ENFORCE_TIER = A.enforce_model || 'sonnet'
const SYNTH_TIER = A.synth_model || 'opus'
const MAX_ROUNDS = Math.max(1, Math.min(Number(A.max_synth_rounds) || 4, 6))
const DUAL_CONTEST = A.dual_contest !== false

const RERUN_CAP = 3
const MODEL_CAP = 3
const COMBO_CAP = 4 // models.length × rerun per ONE invariant — anti-explosion
const WORKER_CAP = 21 // 7 invariants × combo-cap ceiling per wave

const STATUS_RANK = { ABSENT: 4, SUBSTITUTED: 3, 'ENFORCED-PARTIAL': 2, IMPLICIT: 1, ENFORCED: 0 }

// ── un-dup job plan: 1 invariant → 1..(models×rerun) workers ───────────────────
function invariantJobs(inv) {
  const models = Array.isArray(inv.models) && inv.models.length
    ? [...new Set(inv.models)].slice(0, MODEL_CAP)
    : [ENFORCE_TIER]
  const rerunN = Math.max(1, Math.min(Number(inv.rerun) || 1, RERUN_CAP))
  if (models.length * rerunN > COMBO_CAP) {
    throw new Error(
      `HYBRID Scout Fan-Out: invariant "${inv.id}" — models(${models.length})×rerun(${rerunN}) > combo-cap ${COMBO_CAP}`
    )
  }
  const jobs = []
  for (const m of models) for (let i = 0; i < rerunN; i++) jobs.push({ inv, model: m, runIndex: i })
  return jobs
}

const enforceJobs = invs.flatMap(invariantJobs)
if (enforceJobs.length > WORKER_CAP) {
  throw new Error(`HYBRID Scout Fan-Out: ${enforceJobs.length} workers in the Enforce wave — cap ${WORKER_CAP}`)
}

// ── merge N runs of one invariant into ONE observation (rerun-N-union before synthesis) ────────
function mergeEnforceRuns(runs) {
  // runs: [{result, model}], non-empty
  const byStatus = [...runs].sort((a, b) => (STATUS_RANK[b.result.status] || 0) - (STATUS_RANK[a.result.status] || 0))
  const primary = byStatus[0].result
  const seenEv = new Set()
  const paths = []
  for (const r of runs) {
    for (const p of r.result.paths || []) {
      const k = p.evidence || p.path
      if (seenEv.has(k)) continue
      seenEv.add(k)
      paths.push(p)
    }
  }
  const neighborTouch = [...new Set(runs.flatMap((r) => r.result.neighbor_touch || []))]
  return { ...primary, paths, neighbor_touch: neighborTouch }
}

// ── PHASE 1 schema: an enforcement observation for one invariant ────────────────────
const ENFORCE_SCHEMA = {
  type: 'object',
  required: ['invariant_id', 'status', 'paths', 'coverage_note'],
  properties: {
    invariant_id: { type: 'string', description: 'I-NN from the model' },
    status: {
      type: 'string',
      enum: ['ENFORCED', 'ENFORCED-PARTIAL', 'IMPLICIT', 'ABSENT', 'SUBSTITUTED'],
      description: 'actual enforcement status — regardless of what their catalog/[E] claims',
    },
    pred_vs_fact: {
      type: 'string',
      description: 'the claimed pred: versus the fact. pred:ENFORCED→fact:ABSENT/SUBSTITUTED = highest rank (a place everyone considers closed)',
    },
    paths: {
      type: 'array',
      description: 'EXPLICITLY listed paths on which the invariant was checked (if-branches, sibling functions, batch-vs-single, mint-vs-burn, ETH-vs-token). Empty list when ABSENT.',
      items: {
        type: 'object',
        required: ['path', 'enforced_here', 'evidence'],
        properties: {
          path: { type: 'string', description: 'which path/branch' },
          enforced_here: { type: 'boolean' },
          evidence: { type: 'string', description: 'file:line — the specific guard line or its absence' },
        },
      },
    },
    substituted_check: {
      type: 'string',
      description: 'the "is the mechanism canonical" operator: is the data source backed by a fingerprint from invariant_library, or was a home-made analog built? "N/A" if the invariant is not about a canonical primitive.',
    },
    neighbor_touch: {
      type: 'array',
      description: 'CRITICAL for cross-thread: which OTHER subsystems/invariants this path reads or writes (global balance, shared state, external call, hook). This is raw material for the reduce stage.',
      items: { type: 'string' },
    },
    coverage_note: { type: 'string', description: 'what in the partition was NOT read. "Everything checked" is forbidden.' },
  },
}

// ── PHASE 2 schema: a D-NN thread from synthesizing a pair of observations ──────────────────────────
const SYNTH_SCHEMA = {
  type: 'object',
  required: ['threads', 'exhausted'],
  properties: {
    threads: {
      type: 'array',
      description: 'D-NN threads from the SEAM of two distant clues. An empty array = the round yielded nothing new.',
      items: {
        type: 'object',
        required: ['clues', 'seam_hypothesis', 'prediction', 'depth_potential', 'divergence_rank'],
        properties: {
          clues: {
            type: 'array',
            description: 'EXACTLY two (or more) clues: which I-NN/subsystems are intertwined. Each one alone is harmless.',
            items: { type: 'string' },
          },
          seam_hypothesis: {
            type: 'string',
            description: 'a new attack vector living in the SEAM, invisible in any single clue alone (e.g. global balance × per-connector limit = an unlock via A releases deposits of B)',
          },
          prediction: { type: 'string', description: 'what exactly will break and how to see it' },
          entry_point: { type: 'string', description: 'file:line — where to start the serial depth-drive' },
          depth_potential: {
            type: 'integer',
            description: 'how many interaction layers down the thread promises (call→state→external→hook→accounting). <5 = weak for an un-dup crit.',
          },
          divergence_rank: {
            type: 'number',
            description: 'T10 rank: value-weight × path-count × (tests==0) × convergence ÷ crowd-heat. crowd-heat = a queue (cold first), NOT a filter.',
          },
          axis: {
            type: 'string',
            enum: ['cross-function', 'order-dependent', 'temporal', 'cross-subsystem', 'economic-sequence'],
            description: 'which T10 axis expresses this seam (single-function is NOT included — it is not about a seam)',
          },
        },
      },
    },
    exhausted: {
      type: 'boolean',
      description: 'true ONLY if this round honestly found NO new pair beyond those already passed. Do not set true just to finish.',
    },
  },
}

function enforcePrompt(inv, budgetHint, workerCount) {
  const axisNote = inv.axis === 'commodity-subtraction'
    ? '\nAXIS (§52 un-dup): commodity-subtraction — first run the standard detectors/scanners (if applicable to this invariant), mark their findings `hot` and SUBTRACT them — return what is BEYOND the commodity scan.'
    : inv.axis === 'negative-space'
    ? '\nAXIS (§52 un-dup): negative-space — look for UN-MODELED surface: paths covered neither by an audit nor by tests at all. Absence of coverage is itself a candidate.'
    : ''
  const engNote = `\nWORKER ENGINEERING (§27, CAI technique, anti-slop):
- Your answer is <orchestrator_internal> data for the synthesis stage, NOT final prose; downstream it is not quoted verbatim, only the structured schema fields are.
- Output-budget of this call: ${budgetHint ? `~${budgetHint} tokens (combined budget ÷ ${workerCount} wave workers)` : 'be extremely brief'} — no prose beyond the schema.
- ≤1-2 tools per invariant (usually reading only) — do not widen scope without need.`
  return `You are a read-only INVARIANT-checking agent in a bug-bounty hunt (stage T10-enforcement). Target: ${slug}.
Sources: ${src || 'sessions/' + slug}.

YOUR INVARIANT ${inv.id}: ${inv.check}
  component: ${inv.component || '(see model)'}
  claimed pred: ${inv.pred || '(not specified)'}
  partition scope: ${inv.partition_scope || 'the whole component'}${axisNote}${engNote}

TASK — NOT "find a bug", but "find the PLACE where the invariant does NOT hold":
1. Using the operator "on ALL paths?": list EXPLICITLY every branch/path where the invariant must hold
   (if-branches, sibling functions, batch-vs-single, mint-vs-burn, ETH-vs-token) and for each — enforced here or not,
   with a concrete file:line. ENFORCED-PARTIAL (holds on one path, not on another) is the most valuable status,
   do not round it up to ENFORCED.
2. Using the operator "is the mechanism canonical?": if the invariant relies on a standard primitive — did the implementation
   apply the canonical mechanism or a home-made analog? Look at WHAT backs the data source, not
   at the calling code (it looks canonical). Functionality present + fingerprint absent = SUBSTITUTED.
3. Compare pred with the fact. pred:ENFORCED → fact:ABSENT/SUBSTITUTED = highest priority (a place everyone considers closed).

⚠ ANTI-SUBSTITUTION (mandatory): if the repo has their specs/invariants.md or an audit catalog with tags [E]/[D]/[C] —
this is the CORPUS SUBJECT of verification, NOT the truth. Their [E] = "the authors claim enforced" = pred, NOT fact. Your job is to
independently re-check, not to rewrite their tag. A mismatch between their [E] and your fact = exactly what we are looking for.

⚠ neighbor_touch — FILL IN CAREFULLY: which OTHER subsystems this path reads/writes (global balance,
shared mapping, external call, hook, accounting of a neighboring instance). Alone this is not a bug — but the next
stage weaves these touches into cross-thread vectors. An incomplete neighbor_touch = a lost crit in the seam.

RULES: read-only, do NOT write to the ledger. "The invariant is enforced on all paths" is a legitimate and valuable answer (stub),
do not invent ABSENT for the sake of a result. Read the REAL code, do not guess from names.`
}

function synthPrompt(observations, priorThreads, round) {
  const obsJson = JSON.stringify(observations, null, 1)
  const prior = priorThreads.length
    ? `\nALREADY found threads (do NOT repeat, look for OTHER pairs):\n${JSON.stringify(priorThreads.map((t) => t.clues), null, 1)}\n`
    : ''
  return `You are a senior security engineer at the CROSS-THREAD SYNTHESIS stage (T6 × their consumesAll-reduce). Target: ${slug}.
Round ${round}.

Below are ALL the enforcement observations per invariant, collected by the fan-out. Each one alone has been examined and is possibly
harmless. Your task is NOT to rank single findings, but to find PAIRS OF DISTANT clues (different I-NN, different
subsystems, different files) that look clean alone, but INTERTWINED yield a new attack vector.

This is the core of the method: the bug sits in the SEAM, not in a single function (example: a global token__ balance × per-connector
limit → an unlock via connector A releases funds backed by deposits of connector B — no single observation
alone is a bug). Rely on the neighbor_touch field — it holds the subsystem touches.

Seam axes (single-function does NOT count — it is not about a seam): cross-function, order-dependent, temporal,
cross-subsystem/isolation, economic-sequence.

For each thread found, give: two+ clues, a seam hypothesis, prediction, entry_point (file:line to dig from),
depth_potential (how many interaction layers down it promises — <5 is weak for an un-dup crit), divergence_rank, axis.

⚠ You do NOT verify and do NOT trace downward — the main agent does that serially. You emit a THREAD, not a finding.
${prior}
Observations:
${obsJson}

If this round honestly found no NEW pair — return threads:[] and exhausted:true. Do not close prematurely.`
}

// ── PHASE 3 schema/prompt: run_dual_approach_contest (§27) ─────────────────────────
// Two orthogonal hypotheses per FORK (shared entry_point, different axis) — an independent read-only
// check of EACH, not a choice of "which is prettier". Stays in the generation half: not a PoC, not a depth-drive —
// an extra confidence signal for SELECT before the serial depth-drive.
const CONTEST_SCHEMA = {
  type: 'object',
  required: ['supported', 'evidence', 'confidence'],
  properties: {
    supported: { type: 'boolean', description: 'independent check: does this hypothesis branch hold on the real code?' },
    evidence: { type: 'string', description: 'file:line confirming or refuting precisely THIS branch' },
    confidence: { type: 'string', enum: ['low', 'med', 'high'] },
    note: { type: 'string' },
  },
}

function contestPrompt(thread) {
  return `You are a read-only agent of the CONTEST stage (§27 run_dual_approach_contest, CAI technique). Target: ${slug}.
Sources: ${src || 'sessions/' + slug}.

FORK: at entry point ${thread.entry_point || '(not specified)'} synthesis proposed a competing seam
hypothesis on axis ${thread.axis}:
  seam_hypothesis: ${thread.seam_hypothesis}
  clues: ${(thread.clues || []).join(' × ')}
  prediction: ${thread.prediction || '(not specified)'}

TASK: independently CHECK whether EXACTLY THIS hypothesis holds on the real code (file:line) — do not compare
with the alternative branch, do not build a PoC, do not trace downward (the main agent does that serially afterwards).
READ-ONLY, do NOT write to the ledger.`
}

async function run_dual_approach_contest(threadA, threadB) {
  const [ra, rb] = await parallel([
    () => agent(contestPrompt(threadA), { label: 'contest:A', phase: 'Contest', agentType: 'general-purpose', model: ENFORCE_TIER, schema: CONTEST_SCHEMA }),
    () => agent(contestPrompt(threadB), { label: 'contest:B', phase: 'Contest', agentType: 'general-purpose', model: ENFORCE_TIER, schema: CONTEST_SCHEMA }),
  ])
  return { a: ra, b: rb }
}

// ── PHASE 1: enforce fan-out (their map, our divergence, sonnet, un-dup-aware) ─────────
log(`HYBRID Scout Fan-Out: ${slug} · invariants ${invs.length} · workers ${enforceJobs.length} · enforce=${ENFORCE_TIER} synth=${SYNTH_TIER}`)

const rawBudget = (budget && Number.isFinite(budget.total) ? budget.total : null)
  ?? (budget && typeof budget.remaining === 'function' ? budget.remaining() : null)
const perWorkerBudget = Number.isFinite(rawBudget) ? Math.max(200, Math.floor(rawBudget / enforceJobs.length)) : null

const rawEnforced = await parallel(
  enforceJobs.map((j) => () =>
    agent(enforcePrompt(j.inv, perWorkerBudget, enforceJobs.length), {
      label: `enforce:${j.inv.id}${enforceJobs.length > invs.length ? `:${j.model}:r${j.runIndex}` : ''}`,
      phase: 'Enforce',
      agentType: 'general-purpose',
      model: j.model,
      schema: ENFORCE_SCHEMA,
    })
  )
)

// group by invariant_id → merge N runs (rerun-N-union) into ONE observation before synthesis
const byInvariant = new Map()
for (let i = 0; i < enforceJobs.length; i++) {
  const r = rawEnforced[i]
  if (!r) continue
  const key = enforceJobs[i].inv.id
  if (!byInvariant.has(key)) byInvariant.set(key, [])
  byInvariant.get(key).push({ result: r, model: enforceJobs[i].model })
}
const deadInv = invs.length - byInvariant.size
if (deadInv) log(`⚠ ${deadInv} invariants returned no enforcement — NOT covered, fill in manually`)

// models_run (§55.1) — which models actually ran on each invariant
const modelsRun = {}
for (const [key, runs] of byInvariant) modelsRun[key] = [...new Set(runs.map((r) => r.model))].sort()

const observations = [...byInvariant.entries()].map(([key, runs]) => {
  const merged = mergeEnforceRuns(runs)
  merged.invariant_id = key
  // symmetric-difference (§55.1): a status divergence found NOT by all models of the invariant — priority
  const models = modelsRun[key]
  if (models.length >= 2) {
    const positiveModels = new Set(
      runs.filter((r) => ['ABSENT', 'ENFORCED-PARTIAL', 'SUBSTITUTED'].includes(r.result.status)).map((r) => r.model)
    )
    if (positiveModels.size && positiveModels.size < models.length) merged.undup_priority = 'model-diversity'
  }
  return merged
})

// Observations that are already a defect on their own (ABSENT/PARTIAL/SUBSTITUTED) — direct D-NN, not just raw material for pairs.
const directDivergences = observations
  .filter((o) => ['ABSENT', 'ENFORCED-PARTIAL', 'SUBSTITUTED'].includes(o.status))
  .sort((a, b) => Number(!!b.undup_priority) - Number(!!a.undup_priority))
log(`enforcement: ${observations.length} observations (${enforceJobs.length} workers) · ${directDivergences.length} direct divergences (ABSENT/PARTIAL/SUBSTITUTED)`)

// ── PHASE 2: synthesis-reduce (their consumesAll, our cross-thread, senior tier, loop-until-dry) ──
// A single reduce call loses pairs on a long batch — loop while it brings something new, up to 1 empty round.
const threads = []
let dryRounds = 0
for (let round = 1; round <= MAX_ROUNDS && dryRounds < 1; round++) {
  const r = await agent(synthPrompt(observations, threads, round), {
    label: `synthesize:r${round}`,
    phase: 'Synthesize',
    model: SYNTH_TIER,
    schema: SYNTH_SCHEMA,
  })
  const fresh = (r && r.threads) || []
  if (!fresh.length || (r && r.exhausted)) {
    dryRounds++
    log(`synth round ${round}: empty (dry ${dryRounds}/1)`)
    if (!fresh.length) continue
  }
  threads.push(...fresh)
  log(`synth round ${round}: +${fresh.length} threads (total ${threads.length})`)
}

// Rank the threads: first undup_priority (model-diversity), then divergence_rank, then depth_potential.
const rankedThreads = threads
  .filter(Boolean)
  .sort(
    (a, b) =>
      Number(!!b.undup_priority) - Number(!!a.undup_priority) ||
      (b.divergence_rank || 0) - (a.divergence_rank || 0) ||
      (b.depth_potential || 0) - (a.depth_potential || 0)
  )

// ── PHASE 3: run_dual_approach_contest (§27) — EXACTLY one fork per wave ──────
// Fork = 2+ threads on ONE entry_point with different axis (synthesis honestly did not pick one version
// of the seam). We contest only the strongest pair (by divergence_rank) — we do not fan out over all forks at once.
let contestRun = false
if (DUAL_CONTEST) {
  const forkGroups = new Map()
  for (const t of rankedThreads) {
    if (!t.entry_point) continue
    const arr = forkGroups.get(t.entry_point) || []
    arr.push(t)
    forkGroups.set(t.entry_point, arr)
  }
  const fork = [...forkGroups.values()].find((arr) => arr.length >= 2 && new Set(arr.map((t) => t.axis)).size >= 2)
  if (fork) {
    const [tA, tB] = fork.sort((a, b) => (b.divergence_rank || 0) - (a.divergence_rank || 0)).slice(0, 2)
    log(`run_dual_approach_contest: fork at "${tA.entry_point}" — ${tA.axis} vs ${tB.axis}`)
    const contest = await run_dual_approach_contest(tA, tB)
    contestRun = true
    if (contest.a) tA.contest_verdict = { supported: contest.a.supported, evidence: contest.a.evidence, confidence: contest.a.confidence }
    if (contest.b) tB.contest_verdict = { supported: contest.b.supported, evidence: contest.b.evidence, confidence: contest.b.confidence }
  }
}

// soft nudge (§55.1, NOT a hard gate): no invariant has model-diversity, but there is a live direct D-NN
const anyModelDiversity = Object.values(modelsRun).some((arr) => arr.length >= 2)
if (!anyModelDiversity && directDivergences.length) {
  log(`⚠ model-diversity nudge: no invariant was run on 2+ models — consider models:[...] on a re-run of the strongest (soft advice, NOT a block)`)
}

return {
  slug,
  invariants_run: invs.length,
  invariants_failed: deadInv,
  direct_divergences: directDivergences.map((o) => ({
    invariant_id: o.invariant_id,
    status: o.status,
    pred_vs_fact: o.pred_vs_fact,
    evidence: (o.paths || []).filter((p) => !p.enforced_here).map((p) => p.evidence),
    undup_priority: o.undup_priority,
  })),
  cross_thread_threads: rankedThreads,
  coverage_notes: observations.map((o) => ({ invariant_id: o.invariant_id, gap: o.coverage_note })),
  models_run: modelsRun,
  contest_run: contestRun,
  next:
    'MAIN agent: (1) merge into the ledger — direct_divergences → D-NN, cross_thread_threads → D-NN with axis+depth_potential, models_run → `## Scout Fan-Out`; ' +
    '(2) SELECT the strongest thread (undup_priority × divergence_rank × depth_potential); ' +
    '(3) ⛔ DAG IS DONE — next is a SERIAL depth-drive ≥5 layers BY HAND (call→state→external→hook→accounting), NOT a fan-out. ' +
    'This script terminating ≠ "depth done". An empty cross_thread_threads = change the invariant AXIS (WAVE-2), NOT an exit.',
}
