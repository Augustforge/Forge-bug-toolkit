// ⛔ DEPRECATED — DO NOT WIRE INTO THE LOOP (operator decision, phase 3 rebuilt).
//
// The reason is not code quality but architecture: this is a SECOND loop engine (its own rounds, its own counter
// of "dry" axes, its own T9 rotation, its own HUNT-EXIT), whereas we have exactly one engine — the Stop hook
// `hunt_completeness_gate.py`. Two engines with different exit conditions conflict. Also:
//   • rotating the axis BY A COUNTER is exactly what we deliberately rejected: the T9 axis is set by abduction
//     ("loop-until-dry on T9" was rejected in depth_engine_plan §7);
//   • its agents write to the ledger DIRECTLY — this breaks the single-writer rule and bypasses the anti-slop merge;
//   • majority-vote in T4 (`survived >= 2`) cuts our target class (cross-thread findings where each
//     clue alone is harmless) — we dropped that rule.
//
// Replacement (both are one-shot fan-outs that return DATA, merged by the main agent):
//   scout_fanout.workflow.js — explore-wide fan-out with schema-forced leads (partitions by `I-NN`)
//   gapmap.workflow.js       — coverage gap-map as loop-until-dry over unread score-4/5
//
// The file is kept as a reference for the shape of a Workflow script. You may run it manually, but it is NOT part
// of the methodology and is NOT mentioned in any skill.

export const meta = {
  name: 'hunt-driver',
  description: 'Autonomous depth-driver: cold-context agents drive the STRONGEST ledger thread down ≥5 layers / adversarially audit a soft-kill until a T4-confirmed High/Critical or until the axes run dry. Fresh context breaks the "it\'s clean here" anchor (which the Stop hook does not break). Trigger: Workflow({scriptPath, args:{slug:"<target>"}}).',
  whenToUse: 'When you need GENUINE autonomy for hours/days on a single target — a driver with fresh-context agents instead of an interactive instance that gets anchored and rationalizes exhaustion.',
  phases: [
    { title: 'Depth', detail: 'a cold agent drives 1 thread to the next layer / attacks the weakest kill, writes the ledger' },
    { title: 'Verify', detail: 'adversarial verifiers (T4) try to REFUTE the candidate' },
    { title: 'Rotate', detail: 'dry axis → a cold agent on a NEW axis (T9)' },
  ],
}

// ── args ────────────────────────────────────────────────────────────────────
// { slug: "<target>"  (required, folder sessions/<slug>/),
//   dryAxisLimit?: number (how many dry rounds before rotating the axis, default 3),
//   maxAxes?: number (how many T9 axes to run before a surface status, default 4),
//   maxRounds?: number (hard ceiling of rounds, default 40) }
const slug = (args && args.slug) || ''
if (!slug) throw new Error('hunt-driver: args.slug is required (folder sessions/<slug>/)')
const DRY_AXIS_LIMIT = (args && args.dryAxisLimit) || 3
const MAX_AXES = (args && args.maxAxes) || 4
const MAX_ROUNDS = (args && args.maxRounds) || 40
const LEDGER = `sessions/${slug}/hypotheses.md`

const ROUND_SCHEMA = {
  type: 'object',
  required: ['progressed', 'note'],
  properties: {
    progressed: { type: 'boolean', description: 'did DEPTH grow (a new thread layer OR a new T4 verdict), NOT just "wrote something in the ledger"' },
    threadId: { type: 'string', description: 'H-NN or the name of the thread that was advanced' },
    layerReached: { type: 'integer', description: 'depth-ceiling layer reached (0-5+)' },
    candidateFinding: {
      type: ['object', 'null'],
      properties: {
        title: { type: 'string' },
        severity: { type: 'string', enum: ['None', 'Low', 'Medium', 'High', 'Critical'] },
        file: { type: 'string' },
        mechanism: { type: 'string' },
      },
    },
    note: { type: 'string', description: 'one line: what was done + what is next' },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  required: ['refuted', 'severity', 'reason'],
  properties: {
    refuted: { type: 'boolean', description: 'true = the candidate is REFUTED (found a guard/fact that makes the bug impossible/de-minimis/out-of-scope)' },
    severity: { type: 'string', enum: ['None', 'Low', 'Medium', 'High', 'Critical'] },
    reason: { type: 'string', description: 'file:line guard/fact — why you refuted OR why you confirm' },
  },
}

function depthPrompt(round, axis) {
  return `You are a COLD depth agent in an autonomous bug-bounty driver. Target: ${slug}. Ledger: ${LEDGER}.
You have a FRESH context — you are NOT anchored on "it's clean here". Your task is EXACTLY ONE step deeper, not breadth.

STEPS:
1. Read ${LEDGER}. Understand Loop State, Active Hypotheses, Refuted (especially [SCOPED-OUT]/[DE-MINIMIS]/config-dep/
   out-of-scope kills — these are JUDGMENTS, not falsifiers), Scout partitions in RELAUNCH/PENDING status.
2. SELECT EXACTLY ONE target by priority: (a) the strongest open thread (max severity×confidence) not yet driven
   to 5/5; OTHERWISE (b) the weakest soft-kill for an adversarial attack on its basis; OTHERWISE (c) an unfinished scout partition.
3. DRIVE this target to the NEXT depth-ceiling layer (call→state→external→hook→accounting). Read the REAL code
   (clone/grep with your tools), every layer with \`file:line\`. For a kill attack: prove "why it is ACTUALLY
   reachable/amplifiable" or confirm the kill with a REAL falsifier (file:line guard).
4. Edit ${LEDGER} LIVE: update \`Depth-Lead:\` (with the layer count), add/transition a hypothesis with a status, kill —
   ONLY with a file:line falsifier OR a [SCOPED-OUT]/[DE-MINIMIS] tag. If you found a potential bug — create an H-NN
   with a full body. Update the Per-iteration trace.
5. Return the structure: progressed=true ONLY if you really went deeper (new layer/verdict), candidateFinding≠null
   ONLY if there is a concrete potential High/Critical with a mechanism and file:line.

Round ${round}, axis "${axis}". Do NOT map the whole scope, do NOT write "exhaustive/hardened/bad-EV". One step DEEPER.`
}

function verifyPrompt(f, lens) {
  return `You are a COLD adversarial T4 verifier (lens: ${lens}). Target ${slug}, ledger ${LEDGER}.
Candidate finding: "${f.title}" (severity claim: ${f.severity}) in ${f.file}. Mechanism: ${f.mechanism}.
Your task is to REFUTE it. Read the real code by file:line. Through the "${lens}" lens find a guard/fact/
precondition that makes the bug impossible, de-minimis, out-of-scope or already mitigated. If you honestly
CANNOT refute — confirm with the real severity. By default lean toward refuted=true when in doubt
(we cut false positives before submit). Return a verdict with a file:line justification.`
}

const AXES = [
  'strongest-open-thread (max severity×confidence, depth-ceiling ≥5)',
  'soft-kill adversarial re-audit (SCOPED-OUT/DE-MINIMIS/config-dep — why it is reachable)',
  'cross-thread T6 composite (pairs of distant subsystems → new vector)',
  'unfinished scout partitions + fresh threat-model angle',
]

let confirmed = null
let roundsRun = 0
let axisIdx = 0
let dry = 0

log(`hunt-driver start: ${slug} · ledger ${LEDGER} · maxAxes ${MAX_AXES} · dryLimit ${DRY_AXIS_LIMIT}`)

while (roundsRun < MAX_ROUNDS && axisIdx < MAX_AXES && !confirmed) {
  if (budget.total && budget.remaining() < 60000) {
    log(`budget nearly exhausted (${Math.round(budget.remaining() / 1000)}k) → stop, surface status`)
    break
  }
  roundsRun++
  const axis = AXES[Math.min(axisIdx, AXES.length - 1)]

  phase('Depth')
  const r = await agent(depthPrompt(roundsRun, axis), {
    label: `depth:r${roundsRun}:${slug}`,
    phase: 'Depth',
    agentType: 'general-purpose',
    model: 'sonnet',
    schema: ROUND_SCHEMA,
  })

  if (!r) { dry++; log(`round ${roundsRun}: agent returned no result → dry ${dry}/${DRY_AXIS_LIMIT}`); }
  else {
    log(`round ${roundsRun} [${axis.split(' ')[0]}]: ${r.progressed ? 'DEEPER' : 'no depth'} · ${r.note}`)

    const f = r.candidateFinding
    if (f && (f.severity === 'High' || f.severity === 'Critical')) {
      // T4 — 3 adversarial verifiers with DIFFERENT lenses (perspective-diverse refute).
      phase('Verify')
      const lenses = ['correctness/guard', 'severity/de-minimis', 'scope/reachability']
      const verdicts = (await parallel(lenses.map((lens) => () =>
        agent(verifyPrompt(f, lens), {
          label: `verify:${lens.split('/')[0]}:${slug}`,
          phase: 'Verify',
          agentType: 'general-purpose',
          model: 'sonnet',
          schema: VERDICT_SCHEMA,
        })
      ))).filter(Boolean)

      const survived = verdicts.filter((v) => !v.refuted).length
      const highEnough = verdicts.some((v) => !v.refuted && (v.severity === 'High' || v.severity === 'Critical'))
      log(`  T4 «${f.title}»: ${survived}/${verdicts.length} did not refute, High+=${highEnough}`)

      if (survived >= 2 && highEnough) {
        // Confirmed by majority + severity High+ → log T4 and HUNT-EXIT, stop the driver.
        await agent(
          `You are the finalizer in ${LEDGER}. The finding is CONFIRMED by T4 (${survived}/${verdicts.length} verifiers did not refute, severity High+).
Finding: "${f.title}" in ${f.file}. Mechanism: ${f.mechanism}.
Edit ${LEDGER}: (1) add an entry to \`## Verifier Log (T4)\`: \`- <date> — <H-NN> — verdict: confirm ${f.severity} — ${f.file}\`;
(2) write the line \`HUNT-EXIT: T4-CONFIRMED ${f.severity}\` into Loop State. Return a one-line confirmation.`,
          { label: `finalize:${slug}`, phase: 'Verify', agentType: 'general-purpose', model: 'sonnet' }
        )
        confirmed = { finding: f, survived, of: verdicts.length }
        log(`✅ CONFIRMED ${f.severity}: ${f.title} — driver stops (HUNT-EXIT recorded)`)
        break
      } else {
        log(`  candidate did not survive T4 → building block, continuing`)
        dry = 0 // real work was done (found+checked), the axis is not dry
      }
    } else if (r.progressed) {
      dry = 0
    } else {
      dry++
    }
  }

  // Dry axis → rotate to a new one (T9), fresh cold agent.
  if (dry >= DRY_AXIS_LIMIT) {
    axisIdx++
    dry = 0
    log(`axis ran dry (${DRY_AXIS_LIMIT} rounds without depth) → rotating to axis ${axisIdx + 1}/${MAX_AXES}`)
  }
}

const status = confirmed
  ? `CONFIRMED ${confirmed.finding.severity}: ${confirmed.finding.title} (${confirmed.survived}/${confirmed.of} T4)`
  : (axisIdx >= MAX_AXES
      ? `${MAX_AXES} axes dry after ${roundsRun} rounds — surface status to the operator (gap-map in ${LEDGER}), NOT an auto-exit`
      : `stopped (budget/cap) after ${roundsRun} rounds — resume possible`)

log(`hunt-driver finish: ${status}`)
return { slug, confirmed, roundsRun, axesUsed: axisIdx + (confirmed ? 1 : 0), ledger: LEDGER, status }
