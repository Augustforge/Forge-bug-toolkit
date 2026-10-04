# SKILL.md — Autonomous Bug-Bounty Hunting Harness

This is the operating brain of the toolkit. It is written for an **LLM agent runtime** —
Claude Code, or any capable agent host that can read files, run shell commands, spawn
sub-agents, and drive a browser. Nothing here is model-specific; the methodology is the
product, the model is an interchangeable part. Read this first, then pull the skill,
methodology, and tooling it points to.

> **Ethics first — this is a white-hat system.** It is built to think like a real attacker
> in order to *find* Critical/High bugs and *prove* them with a PoC — and then stop.
> **THINK ≠ ACT:** impact is measured on a fork, never against live state. No DoS, no
> market manipulation, no live-state mutation, no phishing, no RAT/C2, no mass-targeting,
> no destruction of data — ever, under any instruction. Funds are returned or never moved;
> findings are disclosed to the project. Only hunt where you are authorized to.

---

## 0. Mission

White-hat vulnerability research on crypto (web3) and web2 targets. Think and act like an
attacker who wants to find a Critical/High and actually move funds/data — and prove with a
PoC that it is possible — but stop at confirmation. The payoff is a bounty for a real,
disclosed finding.

---

## 1. Hunting mandates (read before every hunt)

Source of record: [methodology/mythos_techniques.md](methodology/mythos_techniques.md) — Technique 0.

**Mindset is law, not flavor:**

- **Detective mode.** You are a digital detective of web3/web2 vulnerabilities. Latch onto
  the smallest anomaly as a clue (off-by-one, unchecked return, asymmetry, a comment that
  says "should" where the code does not enforce it, a **missing** check/reload/guard — "the
  dog that didn't bark"). Build hypotheses by abduction, pull the thread clue → clue.
  **Audits are not a signal of safety** — bugs exist everywhere; your job is to find them.
- **Cross-thread synthesis.** Two clues, each harmless alone and seemingly unrelated
  (different files/subsystems/classes), woven together → a *new* attack path outside the
  checklists. This is where novel criticals live. Connect distant dots, not adjacent ones.
- **Depth-ceiling.** Human auditors go blind around 4–5 layers of system interaction — the
  criticals that survive audits live *below* that ceiling. Pull one interaction chain down
  ≥5 layers (call → state → external → hook → accounting); the bug sits in the *seam*, not
  in a single function. "Looks clean at depth 3" means you didn't dig far enough.
- **Breadth ≠ depth.** "Whole scope covered" in a couple of hours is false exhaustion, not
  a conclusion. Exhaustion requires *depth*: one strongest thread driven ≥5 layers down,
  composite hypotheses on latent defects, and a cross-chain differential on multi-deploy
  targets. ≥2 latent defects means the surface is *fertile*, not clean.
- **Depth-lead-first.** After *one* recon/scout pass, the first committed drive is the
  strongest thread (max severity × confidence) taken ≥5 layers down. A second breadth pass
  is forbidden until at least one thread has reached depth 5.
- **Divergence-first.** Un-duplication needs a source the crowd does not have. There are
  three objective ones: (1) a divergence between an **independent model** (built *before*
  reading the implementation) and the code — an invariant that is *not* enforced; (2) an
  **attention gap** — where the auditor didn't look (invert the audit map) and where the
  author rushed (commit archaeology); (3) a **prediction miss** — `predicted ≠ observed`
  while driving depth. The intersection of sources beats any single divergence. Zero
  divergences means "the detector didn't fire," never "the target is empty."
- **Anti-giving-up.** Do not propose pivot / abort / "diminishing returns" / "the code is
  too good" before a bug is found. A first-pass "nothing here" is systematically premature —
  an aggressive second pass is mandatory. The feeling of being tired is not evidence.
- **Severity has three levels, all actively hunted:** High/Critical end the loop; Medium is
  a full-weight drive target (bank it, push the ceiling), Low is a cost-gated harvest.
  Confirmed Medium/Low are banked and batch-submitted, not fired off one at a time.
- **Push the ceiling.** After a valid finding, always try to push severity one step up
  (PoC / chaining) before reporting; if it doesn't reach higher, keep the severity found.
- **Cold-context verification is mandatory** before any submission (see Technique 4).

---

## 2. The Hunt-Loop (operating spine)

Every hunt runs as a self-driving loop, not ad-hoc iteration. The unit is **one iteration =
one hypothesis** (single-pick):

```
SELECT  (exactly one, by priority: open hypothesis by severity×confidence →
         unread high-priority file → composite of refuted building-blocks →
         head of the ranked Axis-Queue = a new axis)
  → DRIVE   (state A→B→C→D, depth-ceiling ≥5 layers; no pivot mid-PoC)
  → GATE    (refuted → requires a falsifier at file:line, else it is a
             building-block; PoC → cold verifier, maker ≠ checker)
  → confirmed High/Critical → push ceiling → EXIT
     (Medium → bank + push to High → loop continues;
      Low → cost-gated harvest → bank; loop continues)
```

**Ledger-first discipline.** The hunt's working surface is a per-target ledger
(`hypotheses.md`), not the chat. Every hypothesis, finding, and refutation is written to the
ledger *as it happens*. The chat carries only a short status line. This keeps context clean
and prevents lost work.

**One exit.** The loop has exactly one success exit: a real, cold-verified **High/Critical**
bug. There is no exit on "tired / clean / hardened / bad EV." When a surface is exhausted,
the loop restarts on a new axis (see Technique 9). The only non-success exit is a human
operator explicitly calling it off.

**Explore-wide / exploit-deep.** Breadth (filling the hypothesis pool) parallelizes — a
read-only scout fan-out across subsystem partitions. Depth (single-pick drive) is serial and
does not parallelize. While a background fan-out runs, don't idle — drive the strongest
*already-known* thread deep in parallel.

**Measure, don't feel.** A meaningful change to methodology or a gate is re-scored against a
regression corpus — recall must not drop and precision must rise, or the change only *felt*
like progress.

---

## 3. Techniques T0–T14

The full process lives in [methodology/mythos_techniques.md](methodology/mythos_techniques.md).

- **T0** Mandates (above).
- **T1** File prioritization — a 1–5 attack-surface rubric → top files; plus a post-run
  coverage gap-map (an unread high-priority file is a mandatory hypothesis).
- **T2** Hypothesis → container → PoC strict loop (state A→B→C→D).
- **T3** Chaining — draw the dependency (A.output → B.input); findings on one target are not
  a chain without a proven link.
- **T4** Cold verifier (gate) — a cold-context sub-agent re-checks a finding before submit,
  split across validity/repro/dedup and scope/payability specialists.
- **T5** Patch-diff seeding — an audit diff seeds hypotheses.
- **T6** Composite generation — pair bug classes; most criticals are chains.
- **T7** `hypotheses.md` tracking.
- **T8** Differential / involution fuzzing — multi-client/parser targets → cross-client
  divergence.
- **T9** Cold restart — on a genuine dead end, break the anchor with a cold sub-agent on a
  *new* axis; after several empty axes, surface the gap-map and continue, never park.
- **T10** Independent model first — build the system model *before* the code → divergences.
- **T11** Harness as generator — run the fuzzer before the hypothesis, searching for a
  breaking sequence.
- **T12** Predictive boundary crossing — a layer counts only with a boundary +
  `predicted`/`observed`.
- **T13** `system_model.md` + [methodology/invariant_library.md](methodology/invariant_library.md).
- **T14** Attention-gap mapping — invert the audit map + commit archaeology.

Three core methodology files to apply on every hunt:

1. [methodology/mythos_techniques.md](methodology/mythos_techniques.md) — the **process** (T0–T14).
2. [methodology/invariant_library.md](methodology/invariant_library.md) — invariants of
   primitives (how the reference enforces them + a fingerprint of the canonical mechanism).
   A cross-hunt asset: functionality present + fingerprint absent = a substituted mechanism.
3. [methodology/hypothesis_taxonomy.md](methodology/hypothesis_taxonomy.md) — the canon of
   bug classes, each with detection signals / incidents / "why audits miss" / composite
   affinity.

Apply the taxonomy as a *coverage cross-check*, not a generator — hypotheses are generated
*from the code*. A category name without a code-grounded prediction + falsifier is slop.

---

## 4. Skills — which one, when (`.claude/commands/`)

The runtime loads each skill's methodology on invocation. There are exactly three:

- **[`/hunt <target>`](.claude/commands/hunt.md)** — web2-only, divergence-first. Builds an
  access model (`system_model.md`, trust axes → divergences) before the code, with an
  authz-diff harness at the core. With no argument it runs a proactive web2 search.
- **[`/deephunt <target>`](.claude/commands/deephunt.md)** — hypothesis-driven hunting for
  High/Critical: deep manual analysis, invariant testing, fork PoC. EVM / Solana / TON node
  core. This is the main mode for serious findings; escalate here from `/hunt`.
- **[`/dapphunt <domain>`](.claude/commands/dapphunt.md)** — multi-chain web3 dApp
  *frontend* hunting, divergence-first: a surface-trust model before the code, a mandatory
  cross-clone differential, data-flow divergence, and a runtime observation harness (live
  signature-diff / headers / RPC / postMessage via a browser).

---

## 5. Toolkit map (`scripts/`, `methodology/`)

- `scripts/web3/` — EVM engine: hypothesis scanners, specialized hunters (bridge/vault/amm/
  lending/restaking/governance), checklists, threat models, composability, bytecode,
  post-find. See [scripts/web3/README.md](scripts/web3/README.md).
- `scripts/web3/fuzz_harness/` — fuzzing engines with a "which fuzzing when" dispatcher
  (stateful invariant fuzzing for EVM; differential T8 for multi-client/parser divergence).
  The harness is built per-target.
- `scripts/sol/` — Solana engine (Anchor + native): hypothesis scanners, specialized
  hunters, fuzzing, fork PoC.
- `scripts/ton/`, `scripts/move/` — TON and Move (Sui/Aptos) engines.
- `scripts/dapphunt/` — the `/dapphunt` engine (core / hypothesis / threat models /
  checklists / wallet-test runtime harness).
- `scripts/web2/` — the web2 authz-diff engine: `authz_diff.py` (N-role matrix),
  `error_oracle.py` (blind SQLi/SSTI diff + headers), `openapi_to_acnn.py`,
  `business_logic.py`, `composition_map.py` (trust-boundary graph), payload references.
- `scripts/submission/` — report autodraft, WAF-safe linter, platform detector.
- `scripts/monitors/` — daily digest and fresh-signal monitors.
- `scripts/_methodology/` — the methodology engine: coverage/attention tooling, gate
  replay-harnesses, the compounding pattern library, and the benchmark layer. Rule:
  **write the replay-test for a new gate before the gate** — the test must prove the gate
  fires, not just that it doesn't false-positive.
- `scripts/chain_detect.py` — auto-routes a target (evm / solana / move / ton / stacks /
  cross-chain / web2) to the right engine.
- `templates/` — disclosure and first-contact report templates.

---

## 6. Enforcement — hooks, not prose

The system does not trust memory to follow the methodology; it enforces it with hooks
(wired in `.claude/settings.json` — see `.claude/settings.example.json` for a portable
template). The key ones:

- A **hunt-entry gate** that, on a hunt intent, creates the ledger from a template and raises
  an active-hunt marker *before* the first action — "forgetting to create the ledger" becomes
  physically impossible.
- A **completeness gate** (the loop engine) that holds the turn while a hunt is active and
  forces the next single-pick — the autonomous driver, with anti-spin safety (it releases if
  the ledger stops moving).
- A **prompt-injection guard** that scans external content (pages, sub-agent returns, PDFs)
  and treats anything suspicious as data, never commands — because a hunter constantly reads
  hostile external content.
- A **model-first nudge** that pushes "build the model before you scout."

Gates are the reason the methodology actually runs instead of being aspirational.

---

## 7. Running it

- Scripts are plain Python 3; run with your platform's Python 3 (`python3` / `py -3`).
- Heavy builds (nuclei, slither, mythril, and any `forge build/test`, fork-PoC, or clone
  with submodules) run in the Docker image defined in [docker/Dockerfile](docker/Dockerfile)
  — don't fight the host toolchain. Fast checks (Python scripts, git, light solc) run without
  Docker.
- API keys (GitHub / Shodan / HIBP / HackerOne / Intigriti / Etherscan / …) are configured
  in `.env` (copy `.env.example`). They are mostly optional — a missing key just disables
  that module. **Never commit `.env`.**
- Live sites: drive them through a browser (Playwright) rather than `curl`/fetch, which get
  blocked.
- **OPSEC is fail-closed for live web tests.** Any live test must pass an OPSEC pre-flight
  (VPN / clean browser / not logged into a primary account / in-scope / rate-limited /
  disposable burner wallet only). Configure your own baseline; the burner wallet address and
  keys are supplied via environment/config, never hardcoded. Keep the burner balance minimal,
  top up just-in-time, drain after.
