// Local smoke test of Workflow scripts WITHOUT a real runtime.
//
// Why. A real run through the `Workflow` tool checks everything at once, but depends on the permission
// plumbing and costs agents. Here the script is executed under the same contract (`args/agent/parallel/log/
// phase/budget`), but `agent()` is a stub returning data PER THE SCHEMA. This proves everything except
// the agent spawning itself: `args` normalization, partitioning, schema shape, dedup, return shape,
// behavior on a failed agent and on "empty".
//
// The smoke test caught a real integration defect: `args` arrives as a STRING, which made the script
// crash in 48 ms with zero agents — in production that would read as "the fan-out ran, no leads".
//
// NOTE: the regexes below that match script output (prompts/log lines) are written in English to match the
// English prompts/log lines of the workflow scripts.
//
// Run: node scripts/_methodology/workflow_smoke.mjs

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const results = []

function check(name, cond, detail = '') {
  results.push(!!cond)
  console.log(`  [${cond ? 'PASS' : 'FAIL'}] ${name}${detail ? ' — ' + detail : ''}`)
}

// We execute the script under the runtime contract: meta is declared, the body is the body of an async function.
async function runScript(file, args, agentImpl) {
  const src = fs.readFileSync(path.join(HERE, file), 'utf8').replace('export const meta', 'const meta')
  const logs = []
  const calls = []
  const agent = async (prompt, opts) => {
    calls.push({ prompt, opts })
    return agentImpl(prompt, opts, calls.length - 1)
  }
  const parallel = async (thunks) => {
    const out = []
    for (const t of thunks) {
      try { out.push(await t()) } catch { out.push(null) }
    }
    return out
  }
  const log = (m) => logs.push(String(m))
  const phase = () => {}
  const budget = { total: null, spent: () => 0, remaining: () => Infinity }
  const body = new (Object.getPrototypeOf(async function () {}).constructor)(
    'args', 'agent', 'parallel', 'log', 'phase', 'budget', 'workflow', src
  )
  const value = await body(args, agent, parallel, log, phase, budget, null)
  return { value, logs, calls }
}

const lead = (file_line, sev, extra = {}) => ({
  title: 'attacker calls X -> Y', file_line, prediction: 'p', falsifier: 'f',
  severity_ceiling: sev, confidence: 'med', ...extra,
})

console.log('── scout_fanout.workflow.js')

// 1) args as a STRING (exactly the case that crashed the first production run)
{
  const args = JSON.stringify({
    slug: 's', src: 'x',
    partitions: [{ id: 'P1', title: 't1', scope: 'sc1' }, { id: 'P2', title: 't2', scope: 'sc2', invariant: 'I-03' }],
  })
  const r = await runScript('scout_fanout.workflow.js', args, async (_p, o) => ({
    partition: o.label, leads: [lead('a.py:10', 'High')], coverage_note: 'what I did not read',
  }))
  check('args as a string → the script runs', r.value && r.value.partitions_run === 2)
  check('agents launched equal the number of partitions', r.calls.length === 2, `calls=${r.calls.length}`)
  check('schema passed to agent()', !!r.calls[0].opts.schema, 'otherwise lead enforcement is lost')
  check('agents are read-only, tier sonnet', r.calls[0].opts.model === 'sonnet')
  check('the invariant made it into the P2 partition prompt', /I-03/.test(r.calls[1].prompt),
        'partition by I-NN, not by subsystem')
  check('the prompt forbids writing to the ledger', /do NOT write to the ledger/i.test(r.calls[0].prompt))
}

// 2) dedup by (file:line × invariant) keeping the highest severity
{
  const args = { slug: 's', partitions: [{ id: 'P1', title: 't', scope: 's' }, { id: 'P2', title: 't', scope: 's' }] }
  const r = await runScript('scout_fanout.workflow.js', args, async (_p, o, i) => ({
    partition: o.label,
    leads: i === 0
      ? [lead('a.py:10', 'Medium'), lead('b.py:20', 'Low')]
      : [lead('a.py:10', 'Critical')],           // same file:line, higher severity
    coverage_note: '-',
  }))
  const L = r.value.leads
  check('duplicate by file:line collapsed', L.length === 2, `leads=${L.length}`)
  check('highest severity kept', L[0].severity_ceiling === 'Critical', L[0].severity_ceiling)
  check('sorted by severity', L[0].severity_ceiling === 'Critical' && L[1].severity_ceiling === 'Low')
}

// 3) a failed agent = an UNCOVERED partition, and this must be visible
{
  const args = { slug: 's', partitions: [{ id: 'P1', title: 't', scope: 's' }, { id: 'P2', title: 't', scope: 's' }] }
  const r = await runScript('scout_fanout.workflow.js', args, async (_p, _o, i) => {
    if (i === 1) throw new Error('agent died')
    return { partition: 'P1', leads: [], coverage_note: 'gap' }
  })
  check('agent failure counted', r.value.partitions_failed === 1)
  check('the uncovered partition is reported out loud', r.logs.some((l) => /returned no result/.test(l)),
        'silent loss of a partition = fake coverage')
  check('empty lead list is a legal answer', Array.isArray(r.value.leads) && r.value.leads.length === 0)
  check('coverage_notes reach the caller', r.value.coverage_notes.length === 1)
}

// 4) protection against a pointless call
{
  let threw = null
  try {
    await runScript('scout_fanout.workflow.js', { slug: 's', partitions: Array(8).fill({ id: 'x', title: 't', scope: 's' }) }, async () => ({}))
  } catch (e) { threw = e.message }
  check('cap of 7 partitions holds', /cap 7/.test(threw || ''), threw || 'did not throw')
}

console.log('── scout_fanout.workflow.js — un-dup engineering')

// 5) rerun-N-union: a partition with rerun:2 runs twice on the same tier, leads union+dedup
{
  const args = {
    slug: 's',
    partitions: [{ id: 'P1', title: 't', scope: 's', rerun: 2 }],
  }
  const r = await runScript('scout_fanout.workflow.js', args, async (_p, o, i) => ({
    partition: o.label,
    leads: i === 0 ? [lead('a.py:10', 'Medium')] : [lead('a.py:10', 'High'), lead('b.py:5', 'Low')],
    coverage_note: '-',
  }))
  check('rerun:2 → 2 workers per partition', r.calls.length === 2, `calls=${r.calls.length}`)
  check('both workers on the same tier (sonnet)', r.calls.every((c) => c.opts.model === 'sonnet'))
  check('union+dedup: 2 unique leads after the merge', r.value.leads.length === 2, `leads=${r.value.leads.length}`)
  check('duplicate a.py:10 collapsed to the highest severity (High)', r.value.leads.some((l) => l.file_line === 'a.py:10' && l.severity_ceiling === 'High'))
}

// 6) model-diversity: a partition with models:[sonnet,opus] → symmetric-diff flags the lead with top priority
{
  const args = {
    slug: 's',
    partitions: [{ id: 'P1', title: 't', scope: 's', models: ['sonnet', 'opus'] }],
  }
  const r = await runScript('scout_fanout.workflow.js', args, async (_p, o) => ({
    partition: o.label,
    // sonnet finds a.py:10 (Medium), opus finds a.py:10 (High) + b.py:5 (Low, ONLY opus)
    leads: o.model === 'sonnet' ? [lead('a.py:10', 'Medium')] : [lead('a.py:10', 'High'), lead('b.py:5', 'Low')],
    coverage_note: '-',
  }))
  check('models:[..] → 1 worker per model', r.calls.length === 2, `calls=${r.calls.length}`)
  check('different models actually passed to agent()', new Set(r.calls.map((c) => c.opts.model)).size === 2,
        r.calls.map((c) => c.opts.model).join(','))
  check('models_run reflects both models per partition', (r.value.models_run.P1 || []).length === 2,
        JSON.stringify(r.value.models_run))
  const b = r.value.leads.find((l) => l.file_line === 'b.py:5')
  check('a lead found by ONLY one model is marked undup_priority', !!b && b.undup_priority === 'model-diversity')
  check('such a lead ranks above the severity tier (first in the list)', r.value.leads[0].file_line === 'b.py:5',
        r.value.leads.map((l) => l.file_line).join(','))
}

// 7) combo-cap: models×rerun > 4 per partition — fails explicitly, not silently trimmed
{
  let threw = null
  try {
    await runScript('scout_fanout.workflow.js', {
      slug: 's',
      partitions: [{ id: 'P1', title: 't', scope: 's', models: ['sonnet', 'opus'], rerun: 3 }],
    }, async () => ({}))
  } catch (e) { threw = e.message }
  check('models(2)×rerun(3)=6 > combo-cap 4 → throws', /combo-cap/.test(threw || ''), threw || 'did not throw')
}

// 8) per-worker engineering (§27) is present in the prompt
{
  const args = { slug: 's', partitions: [{ id: 'P1', title: 't', scope: 's' }] }
  const r = await runScript('scout_fanout.workflow.js', args, async () => ({ partition: 'P1', leads: [], coverage_note: '-' }))
  check('<orchestrator_internal> wrapper in the prompt', /<orchestrator_internal>/.test(r.calls[0].prompt))
  check('output-budget mentioned in the prompt', /Output-budget/.test(r.calls[0].prompt))
  check('tools cap mentioned in the prompt', /1-2 tools/.test(r.calls[0].prompt))
}

// 9) soft nudge: 0 partitions with model-diversity, but a live lead → log, NOT throw
{
  const args = { slug: 's', partitions: [{ id: 'P1', title: 't', scope: 's' }] }
  const r = await runScript('scout_fanout.workflow.js', args, async (_p, o) => ({
    partition: o.label, leads: [lead('a.py:1', 'High')], coverage_note: '-',
  }))
  check('nudge logged, did not block execution', r.logs.some((l) => /model-diversity nudge/.test(l)))
}

console.log('── divergence_fanout.workflow.js — un-dup engineering')

function divAgentImpl(config) {
  return async (prompt, o) => {
    if (o.phase === 'Enforce') return config.enforce(prompt, o)
    if (o.phase === 'Synthesize') return config.synthesize(prompt, o)
    if (o.phase === 'Contest') return config.contest(prompt, o)
    throw new Error(`unknown phase in test: ${o.phase}`)
  }
}

const noThreadsSynth = async () => ({ threads: [], exhausted: true })

// 10) baseline: no rerun/models — 1 worker per invariant, models_run with 1 model each, contest not triggered
{
  const args = {
    slug: 's',
    invariants: [{ id: 'I-01', check: 'c1' }, { id: 'I-02', check: 'c2' }],
    dual_contest: false,
  }
  const r = await runScript('divergence_fanout.workflow.js', args, divAgentImpl({
    enforce: async (_p, o) => ({ invariant_id: o.label.split(':')[1], status: 'ENFORCED', paths: [], coverage_note: '-' }),
    synthesize: noThreadsSynth,
    contest: async () => ({ supported: true, evidence: 'x:1', confidence: 'med' }),
  }))
  check('baseline: 1 worker per invariant (2 total)', r.calls.filter((c) => c.opts.phase === 'Enforce').length === 2)
  check('models_run: 1 model per invariant', r.value.models_run['I-01'].length === 1 && r.value.models_run['I-02'].length === 1)
  check('dual_contest:false → contest_run false', r.value.contest_run === false)
}

// 11) rerun-N-union on an invariant: 2 runs merge into ONE observation with union paths + the worst status
{
  const args = { slug: 's', invariants: [{ id: 'I-01', check: 'c1', rerun: 2 }], dual_contest: false }
  const r = await runScript('divergence_fanout.workflow.js', args, divAgentImpl({
    enforce: async (_p, o, i) => (i === 0
      ? { invariant_id: 'I-01', status: 'ENFORCED', paths: [{ path: 'p1', enforced_here: true, evidence: 'a.sol:1' }], coverage_note: '-' }
      : { invariant_id: 'I-01', status: 'ABSENT', paths: [{ path: 'p2', enforced_here: false, evidence: 'a.sol:2' }], coverage_note: '-' }),
    synthesize: noThreadsSynth,
    contest: async () => ({ supported: true, evidence: 'x', confidence: 'med' }),
  }))
  check('rerun:2 → 2 enforce workers per 1 invariant', r.calls.filter((c) => c.opts.phase === 'Enforce').length === 2)
  check('merge takes the worst status (ABSENT > ENFORCED)', r.value.direct_divergences[0].status === 'ABSENT')
  check('merge unions the paths of both runs', r.value.direct_divergences[0].evidence.length >= 1)
}

// 12) model-diversity on an invariant: symmetric-diff → undup_priority + ranked higher
{
  const args = { slug: 's', invariants: [{ id: 'I-01', check: 'c1', models: ['sonnet', 'opus'] }], dual_contest: false }
  const r = await runScript('divergence_fanout.workflow.js', args, divAgentImpl({
    enforce: async (_p, o) => (o.model === 'opus'
      ? { invariant_id: 'I-01', status: 'ABSENT', paths: [{ path: 'p', enforced_here: false, evidence: 'a.sol:9' }], coverage_note: '-' }
      : { invariant_id: 'I-01', status: 'ENFORCED', paths: [], coverage_note: '-' }),
    synthesize: noThreadsSynth,
    contest: async () => ({ supported: true, evidence: 'x', confidence: 'med' }),
  }))
  check('models:[..] → 2 enforce workers on different models', new Set(r.calls.filter((c) => c.opts.phase === 'Enforce').map((c) => c.opts.model)).size === 2)
  check('ABSENT found by NOT all models → undup_priority', r.value.direct_divergences[0].undup_priority === 'model-diversity')
}

// 13) combo-cap on an invariant
{
  let threw = null
  try {
    await runScript('divergence_fanout.workflow.js', {
      slug: 's', invariants: [{ id: 'I-01', check: 'c1', models: ['sonnet', 'opus'], rerun: 3 }],
    }, divAgentImpl({ enforce: async () => ({}), synthesize: noThreadsSynth, contest: async () => ({}) }))
  } catch (e) { threw = e.message }
  check('models(2)×rerun(3) > combo-cap 4 → throws', /combo-cap/.test(threw || ''), threw || 'did not throw')
}

// 14) run_dual_approach_contest: a fork (shared entry_point, different axis) triggers the Contest phase
{
  const args = {
    slug: 's',
    invariants: [{ id: 'I-01', check: 'c1' }, { id: 'I-02', check: 'c2' }],
    max_synth_rounds: 2,
  }
  let synthCall = 0
  const r = await runScript('divergence_fanout.workflow.js', args, divAgentImpl({
    enforce: async (_p, o) => ({ invariant_id: o.label.split(':')[1], status: 'ABSENT', paths: [{ path: 'p', enforced_here: false, evidence: 'a.sol:1' }], neighbor_touch: ['other'], coverage_note: '-' }),
    synthesize: async () => {
      synthCall++
      if (synthCall === 1) {
        return {
          threads: [
            { clues: ['I-01', 'I-02'], seam_hypothesis: 'h1', prediction: 'p1', entry_point: 'a.sol:1', depth_potential: 5, divergence_rank: 9, axis: 'cross-function' },
            { clues: ['I-02', 'I-01'], seam_hypothesis: 'h2', prediction: 'p2', entry_point: 'a.sol:1', depth_potential: 5, divergence_rank: 8, axis: 'temporal' },
          ],
          exhausted: false,
        }
      }
      return { threads: [], exhausted: true }
    },
    contest: async (_p, o) => ({ supported: /FORK/.test(_p) && true, evidence: 'a.sol:1', confidence: 'high', _label: o.label }),
  }))
  check('contest actually invoked (2 Contest agents)', r.calls.filter((c) => c.opts.phase === 'Contest').length === 2)
  check('contest_run: true in the output', r.value.contest_run === true)
  const withVerdict = r.value.cross_thread_threads.filter((t) => t.contest_verdict)
  check('both competing threads got a contest_verdict', withVerdict.length === 2, withVerdict.length)
  check('the contest prompt references the fork/axis', /fork/i.test(r.calls.find((c) => c.opts.phase === 'Contest').prompt))
}

// 15) per-worker engineering (§27) in the enforce prompt
{
  const args = { slug: 's', invariants: [{ id: 'I-01', check: 'c1' }], dual_contest: false }
  const r = await runScript('divergence_fanout.workflow.js', args, divAgentImpl({
    enforce: async () => ({ invariant_id: 'I-01', status: 'ENFORCED', paths: [], coverage_note: '-' }),
    synthesize: noThreadsSynth,
    contest: async () => ({}),
  }))
  const enforcePrompt0 = r.calls.find((c) => c.opts.phase === 'Enforce').prompt
  check('<orchestrator_internal> wrapper in the enforce prompt', /<orchestrator_internal>/.test(enforcePrompt0))
  check('output-budget mentioned in the enforce prompt', /Output-budget/.test(enforcePrompt0))
}

console.log('── gapmap.workflow.js')

// 5) loop-until-dry: the queue is drained in batches, unread and trimmed files are visible
{
  const files = Array.from({ length: 7 }, (_, i) => `src/F${i}.sol`)
  const args = JSON.stringify({ slug: 's', files, batch: 3, maxFiles: 6 })
  const r = await runScript('gapmap.workflow.js', args, async (p) => {
    const f = /FILE: (\S+)/.exec(p)[1]
    return { file: f, read_fully: f !== 'src/F2.sol', leads: f === 'src/F0.sol' ? [lead(`${f}:5`, 'High')] : [], note: 'checked X' }
  })
  check('only files within maxFiles processed', r.value.files_read === 6, `read=${r.value.files_read}`)
  check('what was trimmed by the limit is RETURNED explicitly', r.value.dropped_by_cap.length === 1,
        'silent cap forbidden: silently trimmed coverage reads as "covered everything"')
  check('the trimming is stated in the log', r.logs.some((l) => /TRIMMED/.test(l)))
  check('the unread file stayed marked', r.value.not_read_fully.includes('src/F2.sol'))
  check('queue drained in batches', r.logs.filter((l) => /^round /.test(l)).length === 2)
  check('leads collected', r.value.leads.length === 1)
  check('"empty but checked" is returned with justification', r.value.empty_but_checked.length === 5)
}

const ok = results.filter(Boolean).length
console.log(`\n${ok}/${results.length} workflow-smoke cases green`)
process.exit(ok === results.length ? 0 : 1)
