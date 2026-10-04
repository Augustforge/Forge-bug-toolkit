export const meta = {
  name: 'scout-fanout',
  description: 'CLASSIC Scout Fan-Out — not to be confused with HYBRID Scout Fan-Out (divergence_fanout.workflow.js, which has a reduce=synthesis stage). An explore-wide fan-out of read-only scouts with SCHEMA-forced leads: partitions by invariants I-NN (if the model is built) or by subsystems. The cross-thread merge is done BY HAND by the main agent (in HYBRID it is mechanized). Un-dup-aware: rerun-N-union + model-diversity + per-worker budget engineering. Returns DATA — the main agent merges it, scouts do NOT write to the ledger.',
  whenToUse: 'Once on entering a hunt (and on every new T9 axis), when the surface is multi-subsystem: ≳15 score-4/5 files OR ≥3 subsystems. A small contract does not need it — it is cheaper to read it whole.',
  phases: [
    { title: 'Scout', detail: 'a read-only agent per partition: 1 partition = 1..N workers (rerun-N-union / model-diversity), a lead must carry file:line + prediction + falsifier' },
  ],
}

// ── Why a workflow, and not just a fan-out of Agents ───────────────────────────────
// There is ONE win and it is not context savings: `schema` is validated at the tool-call level, so
// a lead without `file:line` / prediction / falsifier physically will not pass — the agent retries. With a plain
// Agent fan-out this rests on prompt prose, i.e. it does not hold (our long-standing source of slop).
//
// ⚠ Scouts write NOTHING to the ledger (operator decision). The only writer is the main
// agent: only this way does the merge with anti-slop + dedup + the cross-thread T6 pass work. Parallel writes
// to one file also conflict.
//
// args: { slug: "<target>", src: "<path to sources>",
//         partitions: [{ id, title, scope, invariant?,
//                         rerun?: 1..3,           // §40.2 rerun-N-union: same partition N times, union+dedup
//                         models?: ["sonnet",...], // §55.1 model-diversity: 2+ models, symmetric-diff = priority
//                         axis?: "commodity-subtraction" | "negative-space" }, ...]   (2..7 partitions),
//         model?: "sonnet" }
//
// Un-dup engineering (§40.2 + §27 + §55.1 + §52 — see sessions/_methodology/scout_fanout.md):
//   - rerun-N-union: a partition with `rerun: N` (cap 3) is run N times on the same tier — the model's nondeterminism
//     is exploited, the union of all runs goes through THE SAME dedup pass below (file:line×class, top-severity).
//   - model-diversity: a partition with `models: [...]` (cap 3, names deduped) is run by EACH model. A lead
//     found NOT by all models of the partition (symmetric difference) is marked
//     `undup_priority: "model-diversity"` and ranked HIGHER within the same severity tier.
//   - per-worker engineering (§27, CAI technique): output-budget `combined // n` workers + an `<orchestrator_internal>`
//     wrapper (the worker = data, not prose to quote) + ≤1-2 tools/worker — built into the scout prompt.
//   - `models_run` is returned as an object {partition_id: [models]} — the main agent writes it into the ledger
//     `## Scout Fan-Out` (Task 1 `models_run:` in the `## Un-Dup Sweep` header — a reference to this section, not a duplicate).
//   - Combo-cap: models.length × rerun ≤ 4 per partition (anti-explosion), ≤21 workers total per wave.

// ⚠ Smoke test: `args` arrives as a STRING, not an object (depends on how the caller
// serializes the parameter). Without this normalization the script crashed in 48 ms with "args.slug
// is required" and ZERO agents launched — in production that would read as "the fan-out ran, no leads".
// We accept both forms.
const A = typeof args === 'string' ? JSON.parse(args) : (args || {})

const slug = A.slug || ''
const src = A.src || ''
const parts = A.partitions || []
if (!slug) throw new Error('scout-fanout: args.slug is required')
if (!Array.isArray(parts) || parts.length < 1) throw new Error('scout-fanout: args.partitions is empty')
if (parts.length > 7) throw new Error(`scout-fanout: ${parts.length} partitions — cap 7 (the rest goes to a second wave)`)
const TIER = A.model || 'sonnet'

const RERUN_CAP = 3
const MODEL_CAP = 3
const COMBO_CAP = 4 // models.length × rerun per ONE partition — anti-explosion
const WORKER_CAP = 21 // 7 partitions × combo-cap ceiling per wave

const LEAD_SCHEMA = {
  type: 'object',
  required: ['partition', 'leads', 'coverage_note'],
  properties: {
    partition: { type: 'string' },
    leads: {
      type: 'array',
      items: {
        type: 'object',
        required: ['title', 'file_line', 'prediction', 'falsifier', 'severity_ceiling', 'confidence'],
        properties: {
          title: { type: 'string', description: 'one line: attacker action → observable effect' },
          file_line: { type: 'string', description: 'path/to/File.sol:120 — a SPECIFIC line, not the whole file' },
          prediction: { type: 'string', description: 'what exactly will break and how to see it' },
          falsifier: { type: 'string', description: 'which guard/fact (file:line) kills this hypothesis — without it the lead is invalid' },
          invariant: { type: 'string', description: 'I-NN from system_model.md, if the partition is cut by invariant' },
          enforcement: { type: 'string', enum: ['ENFORCED', 'ENFORCED-PARTIAL', 'IMPLICIT', 'ABSENT', 'SUBSTITUTED', 'N/A'] },
          severity_ceiling: { type: 'string', enum: ['Low', 'Medium', 'High', 'Critical'] },
          confidence: { type: 'string', enum: ['low', 'med', 'high'] },
        },
      },
    },
    coverage_note: { type: 'string', description: 'what in the partition was NOT read (an honest coverage hole, not "everything checked")' },
  },
}

// ── un-dup job plan: 1 partition → 1..(models×rerun) workers ────────────────────
function partitionJobs(p) {
  const models = Array.isArray(p.models) && p.models.length
    ? [...new Set(p.models)].slice(0, MODEL_CAP)
    : [TIER]
  const rerunN = Math.max(1, Math.min(Number(p.rerun) || 1, RERUN_CAP))
  if (models.length * rerunN > COMBO_CAP) {
    throw new Error(
      `scout-fanout: partition "${p.title}" — models(${models.length})×rerun(${rerunN}) > combo-cap ${COMBO_CAP}`
    )
  }
  const jobs = []
  for (const m of models) for (let i = 0; i < rerunN; i++) jobs.push({ p, model: m, runIndex: i })
  return jobs
}

const jobs = parts.flatMap(partitionJobs)
if (jobs.length > WORKER_CAP) {
  throw new Error(`scout-fanout: ${jobs.length} workers in the wave — cap ${WORKER_CAP}`)
}

function partitionKey(p) {
  return p.id || p.title
}

function scoutPrompt(p, budgetHint, workerCount) {
  const inv = p.invariant
    ? `\nYOUR INVARIANT: ${p.invariant}\nLook for the PLACE where it is NOT enforced (or enforced partially / on a substituted mechanism), not "suspicious code".`
    : ''
  const axisNote = p.axis === 'commodity-subtraction'
    ? '\nAXIS (§52 un-dup): commodity-subtraction — first run the standard detectors/scanners of your partition (if applicable), mark their findings `hot` (what the crowd already sees) and SUBTRACT them from your leads — return what is BEYOND the commodity scan.'
    : p.axis === 'negative-space'
    ? '\nAXIS (§52 un-dup): negative-space — look NOT for "suspicious code", but for UN-MODELED surface: what is covered by no audit, no tests, no standard scanners of the partition. Absence of coverage is itself a candidate lead.'
    : ''
  const engNote = `\nWORKER ENGINEERING (§27, CAI technique, anti-slop):
- Your answer is <orchestrator_internal> data for the main agent's merge, NOT final prose for a human; downstream it is not quoted verbatim, only the structured schema fields are.
- Output-budget of this call: ${budgetHint ? `~${budgetHint} tokens (combined budget ÷ ${workerCount} wave workers)` : 'be extremely brief'} — no prose beyond the schema.
- ≤1-2 tools per partition (usually only reading files in your scope) — do not widen scope without need.`
  return `You are a read-only scout in a bug-bounty hunt. Target: ${slug}. Sources: ${src || 'see sessions/' + slug}.
Partition: ${p.title}. Scope: ${p.scope}.${inv}${axisNote}

RULES (strict):
1. READ-ONLY. Edit nothing, do NOT write to the ledger — you return data, the main agent merges.
2. Every lead must carry a SPECIFIC \`file:line\`, a prediction and a **falsifier** (what exactly
   would kill it). A lead without a falsifier is an opinion, not a lead; do not return such a one.
3. A bug class name without a code-grounded prediction = slop → discard it yourself, do not hand it over.
4. Better 2 strong leads than 9 of "looks risky". An empty list is a legitimate answer.
5. In \`coverage_note\` honestly write what you did NOT get to read. "Everything checked" is a forbidden phrasing:
   what is not read is not checked.
${engNote}

Read the REAL code from the files, do not guess from names.`
}

log(`CLASSIC Scout Fan-Out: ${slug} · partitions ${parts.length} · workers ${jobs.length} · tier ${TIER}`)

// ── budget: combined // n (§27) — best-effort, budget.total may be unavailable (then null) ──
const rawBudget = (budget && Number.isFinite(budget.total) ? budget.total : null)
  ?? (budget && typeof budget.remaining === 'function' ? budget.remaining() : null)
const perWorkerBudget = Number.isFinite(rawBudget) ? Math.max(200, Math.floor(rawBudget / jobs.length)) : null

const rawResults = await parallel(jobs.map((j) => () =>
  agent(scoutPrompt(j.p, perWorkerBudget, jobs.length), {
    label: `scout:${partitionKey(j.p)}${jobs.length > parts.length ? `:${j.model}:r${j.runIndex}` : ''}`,
    phase: 'Scout',
    agentType: 'general-purpose',
    model: j.model,
    schema: LEAD_SCHEMA,
  })
))

// ── group by partition (successful runs) ──────────────────────────────────────────
const byPartition = new Map()
for (let i = 0; i < jobs.length; i++) {
  const r = rawResults[i]
  if (!r) continue
  const key = partitionKey(jobs[i].p)
  if (!byPartition.has(key)) byPartition.set(key, [])
  byPartition.get(key).push({ result: r, model: jobs[i].model })
}
const dead = parts.length - byPartition.size

// models_run (§55.1) — which models actually ran on each partition
const modelsRun = {}
for (const [key, runs] of byPartition) {
  modelsRun[key] = [...new Set(runs.map((r) => r.model))].sort()
}

// leads bound to partition/model VIA the job (not via the agent's self-report — more reliable)
const leads = []
for (const [key, runs] of byPartition) {
  const models = modelsRun[key]
  // symmetric-difference (§55.1): a lead found NOT by all models of the partition — a priority un-dup candidate
  const byFileLine = new Map()
  if (models.length >= 2) {
    for (const r of runs) {
      for (const l of r.result.leads || []) {
        if (!byFileLine.has(l.file_line)) byFileLine.set(l.file_line, new Set())
        byFileLine.get(l.file_line).add(r.model)
      }
    }
  }
  for (const r of runs) {
    for (const l of r.result.leads || []) {
      const undupPriority = models.length >= 2 && byFileLine.get(l.file_line).size < models.length
        ? 'model-diversity'
        : undefined
      leads.push({ ...l, partition: key, ...(undupPriority ? { undup_priority: undupPriority } : {}) })
    }
  }
}

// Dedup by (file:line + invariant class) — keep the highest severity_ceiling;
// undup_priority is preserved if it was present on at least one of the merged runs (rerun-N-union).
const RANK = { Low: 1, Medium: 2, High: 3, Critical: 4 }
const byKey = new Map()
for (const l of leads) {
  const k = `${l.file_line}|${l.invariant || l.title.slice(0, 40)}`
  const prev = byKey.get(k)
  if (!prev) { byKey.set(k, l); continue }
  const merged = (RANK[l.severity_ceiling] || 0) > (RANK[prev.severity_ceiling] || 0) ? { ...l } : { ...prev }
  if (prev.undup_priority || l.undup_priority) merged.undup_priority = prev.undup_priority || l.undup_priority
  byKey.set(k, merged)
}
const deduped = [...byKey.values()].sort(
  (a, b) =>
    Number(!!b.undup_priority) - Number(!!a.undup_priority) ||
    (RANK[b.severity_ceiling] || 0) - (RANK[a.severity_ceiling] || 0)
)

// soft nudge (§55.1, NOT a hard gate): no partition has model-diversity, but there is a live lead
const anyModelDiversity = Object.values(modelsRun).some((arr) => arr.length >= 2)
if (!anyModelDiversity && deduped.length) {
  const strongest = deduped[0].partition
  log(`⚠ model-diversity nudge: the strongest partition "${strongest}" was run on 1 model — consider models:[...] on a re-run (soft advice, NOT a block)`)
}

if (dead) log(`⚠ ${dead} partitions returned no result — they are NOT covered, fill them in manually`)
log(`leads: ${leads.length} raw (${jobs.length} workers) → ${deduped.length} after dedup`)

return {
  slug,
  partitions_run: parts.length,
  partitions_failed: dead,
  leads: deduped,
  coverage_notes: [...byPartition.entries()].flatMap(([key, runs]) =>
    runs.map((r) => ({ partition: key, gap: r.result.coverage_note }))
  ),
  models_run: modelsRun,
  next: 'MAIN agent: merge into the ledger (anti-slop → dedup → cross-thread T6 pass) → H-NN, models_run → `## Scout Fan-Out`, THEN status to chat',
}
