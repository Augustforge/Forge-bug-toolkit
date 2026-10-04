export const meta = {
  name: 'gapmap-dry',
  description: 'Coverage gap-map as loop-until-dry: drives UNREAD score-4/5 files in batches until the list is empty. Each file is read line by line, returning either a lead with a schema, or an honest "empty + what exactly was read".',
  whenToUse: 'Before any "found nothing" conclusion and at the completeness gate: an unread file = an unchecked file. Mechanical work that parallelizes honestly.',
  phases: [
    { title: 'GapMap', detail: 'one agent per file, in batches; repeat until no unread files remain' },
  ],
}

// ── Why loop-until-dry, not "top-N" ─────────────────────────────────────────
// "Went through the top-5" is a sample, not coverage: the tail of the list is systematically never read,
// and it is exactly what later becomes the "coverage gap" in the report on why we found nothing.
// Here the list is drained to empty, and anything dropped by the limit is LOGGED explicitly (a silent cap
// is forbidden: silently trimmed coverage reads as "covered everything").
//
// args: { slug, src, files: ["src/A.sol", ...], batch?: 5, maxFiles?: 60, model?: "sonnet" }

// ⚠ Smoke test: `args` may arrive as a STRING, not an object — then `args.files` is undefined and
// the script crashes instantly with zero agents (looks like "ran, found nothing"). We normalize.
const A = typeof args === 'string' ? JSON.parse(args) : (args || {})

const slug = A.slug || ''
const src = A.src || ''
let files = (A.files || []).slice()
if (!slug) throw new Error('gapmap-dry: args.slug is required')
if (!files.length) throw new Error('gapmap-dry: args.files is empty — first build the list of unread score-4/5')
const BATCH = A.batch || 5
const MAX_FILES = A.maxFiles || 60
const TIER = A.model || 'sonnet'

const dropped = files.length > MAX_FILES ? files.slice(MAX_FILES) : []
files = files.slice(0, MAX_FILES)

const FILE_SCHEMA = {
  type: 'object',
  required: ['file', 'read_fully', 'leads', 'note'],
  properties: {
    file: { type: 'string' },
    read_fully: { type: 'boolean', description: 'read LINE BY LINE in full (not "skimmed")' },
    leads: {
      type: 'array',
      items: {
        type: 'object',
        required: ['title', 'file_line', 'prediction', 'falsifier', 'severity_ceiling'],
        properties: {
          title: { type: 'string' },
          file_line: { type: 'string' },
          prediction: { type: 'string' },
          falsifier: { type: 'string' },
          severity_ceiling: { type: 'string', enum: ['Low', 'Medium', 'High', 'Critical'] },
        },
      },
    },
    note: { type: 'string', description: 'if there are no leads — WHAT exactly was checked and why it is empty (not "looks fine")' },
  },
}

function filePrompt(f) {
  return `You are a read-only coverage gap-map agent. Target ${slug}, sources ${src || 'sessions/' + slug}.
FILE: ${f}

Read it LINE BY LINE in full — not by function names and not diagonally. Then:
1. Return a lead ONLY with a concrete \`file:line\`, a prediction and a **falsifier**. Without a falsifier — not a lead.
2. Empty is a legitimate answer, but in \`note\` write WHAT was checked (which functions/branches/invariants), not
   "looks fine". Our axiom: didn't find = didn't dig deep enough, not "clean".
3. Set \`read_fully=false\` honestly if the file did not fit entirely — then it stays in the queue.
4. Do NOT write to the ledger: you return data, the main agent merges.`
}

let queue = files.slice()
const collected = []
const unread = []
let round = 0

log(`gapmap-dry: ${slug} · files ${queue.length} · batch ${BATCH}`)
if (dropped.length) log(`⚠ TRIMMED by maxFiles: ${dropped.length} files will NOT go into this run — ${dropped.join(', ')}`)

while (queue.length) {
  round++
  const batch = queue.splice(0, BATCH)
  const res = (await parallel(batch.map((f) => () =>
    agent(filePrompt(f), {
      label: `gapmap:${f.split('/').pop()}`,
      phase: 'GapMap',
      agentType: 'general-purpose',
      model: TIER,
      schema: FILE_SCHEMA,
    })
  ))).filter(Boolean)

  for (const r of res) {
    collected.push(r)
    if (!r.read_fully) unread.push(r.file)
  }
  const found = res.reduce((n, r) => n + (r.leads || []).length, 0)
  log(`round ${round}: ${res.length}/${batch.length} files · leads ${found} · remaining ${queue.length}`)
}

const leads = collected.flatMap((r) => r.leads || [])
log(`gapmap-dry finish: read ${collected.length}, leads ${leads.length}, not fully read ${unread.length}`)

return {
  slug,
  files_read: collected.length,
  leads,
  not_read_fully: unread,
  dropped_by_cap: dropped,
  empty_but_checked: collected.filter((r) => !(r.leads || []).length).map((r) => ({ file: r.file, note: r.note })),
  next: 'MAIN agent: leads → H-NN in the ledger; not_read_fully and dropped_by_cap REMAIN unread — the gap-map is not closed until they are empty',
}
