#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression test for model_first_nudge.py (PreToolUse MODEL-FIRST scout-guard).

System rule: replay test first, hook second (we got burned on BREADTH_RE / template-blindness).
The test PROVES firing (feedback_hook_must_prove_firing), not just the absence of false positives:
  - fire on the REAL untouched template (template_sentinel_check principle: a detector blind to a
    template edit stays silent for months -- LEDGER-LIVE/nudge went blind exactly that way);
  - silence on MODEL: BUILDING / N/A / scout wave DONE;
  - PER-WAVE: a NEW T9 axis (model of the previous subsystem built + Scout reset to PENDING, no
    BUILDING) -> FIRE -- forces a NEW I-NN wave, not a scout over the old model;
  - anti-FP: a sentinel in backticks/{...} is NOT counted as fact;
  - e2e main(): correct tool (Agent), active hunt, debounce, foreign tool.
The subagent tool name = **Agent** (in this harness Task=0, Agent=970) -- the test pins this down.
Run: py -3 -X utf8 scripts/_methodology/model_first_nudge_replay.py
"""
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile

import os as _os  # P4: path from __file__, not from CWD (it used to fail when run outside the toolkit root)
_HOOK = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "hooks", "model_first_nudge.py")
spec = importlib.util.spec_from_file_location("nudge", _HOOK)
n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(n)

# P4: from __file__ (scripts/_methodology/ -> ../../sessions/_methodology/)
_TK = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
TEMPLATE = _os.path.join(_TK, "sessions", "_methodology", "hypotheses_template.md")

results = []


def check(name, got, expect):
    ok = (bool(got) == expect)
    print("  [%s] %s: got=%s expect=%s" % ("PASS" if ok else "FAIL", name, bool(got), expect))
    results.append(ok)


def mk(ledger_txt):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_txt)
    return d, os.path.join(d, ".hunt_active")


LOOP_HDR = "# t — Hypotheses Registry\n\n## Loop State\n- **Iteration #:** 1\n"
SCOUT_PENDING = "\n## Scout Fan-Out\n**Status:** `PENDING`  ← change to DONE\n"
SCOUT_DONE = "\n## Scout Fan-Out\n**Status:** `DONE 2026-07-28`\n"
# "New wave": the model counter of the PREVIOUS subsystem is set, Scout reset to PENDING, BUILDING NOT set.
# (Russian fixture text below is matched by Russian regexes in the hook -- KEEP.)
PRIOR_MODEL = "- **MODEL (T10/T13):** I-NN всего: 12 / ABSENT: 0 / текущий: — (rentals закрыт)\n"

print("── A. _should_nudge (True = hook fires)")

# 1. REAL untouched template -> scout PENDING, model not being built -> FIRE (template_sentinel_check).
with open(TEMPLATE, "r", encoding="utf-8") as f:
    pristine = f.read()
d, m = mk(pristine)
check("untouched TEMPLATE -> FIRE", n._should_nudge(m), True)
shutil.rmtree(d, ignore_errors=True)

# 2. First wave: scout PENDING, no MODEL line at all -> FIRE.
d, m = mk(LOOP_HDR + SCOUT_PENDING)
check("first wave (scout PENDING, no MODEL) -> FIRE", n._should_nudge(m), True)
shutil.rmtree(d, ignore_errors=True)

# 3. NEW T9 AXIS: model of the previous subsystem built + Scout reset to PENDING, no BUILDING -> FIRE.
d, m = mk(LOOP_HDR + PRIOR_MODEL + SCOUT_PENDING)
check("NEW axis (old model + scout->PENDING, no BUILDING) -> FIRE", n._should_nudge(m), True)
shutil.rmtree(d, ignore_errors=True)

# 4. New axis done correctly: MODEL: BUILDING set (building the new wave) -> silent.
d, m = mk(LOOP_HDR + PRIOR_MODEL + "- **MODEL: BUILDING** (строю волну offchain-mp)\n" + SCOUT_PENDING)  # "building the offchain-mp wave"
check("new axis + MODEL: BUILDING (building a new wave) -> silent", n._should_nudge(m), False)
shutil.rmtree(d, ignore_errors=True)

# 5. MODEL: N/A (T10 not applicable) + scout PENDING -> silent.
d, m = mk(LOOP_HDR + "- **MODEL: N/A — single contract <300 LOC**\n" + SCOUT_PENDING)
check("MODEL: N/A -> silent", n._should_nudge(m), False)
shutil.rmtree(d, ignore_errors=True)

# 6. Scout wave finished (Status DONE) -> silent.
d, m = mk(LOOP_HDR + PRIOR_MODEL + SCOUT_DONE)
check("Scout Status DONE (wave finished) -> silent", n._should_nudge(m), False)
shutil.rmtree(d, ignore_errors=True)

# 7. Anti-FP: sentinel INSIDE backticks/{...} (template instruction) does NOT silence + scout PENDING -> FIRE.
d, m = mk(LOOP_HDR + "- **MODEL:** {сентинел `MODEL: N/A — <причина>` снимает гейт}\n" + SCOUT_PENDING)  # "sentinel `MODEL: N/A - <reason>` lifts the gate"
check("sentinel in backticks/{...} does not silence -> FIRE", n._should_nudge(m), True)
shutil.rmtree(d, ignore_errors=True)

# 8. No Scout Fan-Out section at all (e.g. a small contract with no fan-out) -> silent.
d, m = mk(LOOP_HDR + PRIOR_MODEL)
check("no Scout Fan-Out section -> silent", n._should_nudge(m), False)
shutil.rmtree(d, ignore_errors=True)


print("── A2. OBS-24 _new_axis_needs_wave (T9 axes > WAVE waves -> FIRE at the Agent boundary)")

AXES_N = lambda k: "- **T9 restart axes used:** %d (axes listed)\n" % k
BASE_INV = "## Invariants\n- **I-01** [state] X. check: путь? pred: ENFORCED\n- **I-02** [state] Y. check: путь? pred: ENFORCED\n- **I-03** [state] Z. check: путь? pred: ENFORCED\n"  # "путь" = "path"
WAVE = lambda k: "\n## WAVE-%d — ось-%d conservation\n- **I-1%d** [state] W. check: путь? pred: ENFORCED\n" % (k, k, k)  # "ось" = "axis"


def mk2(ledger_txt, model_txt):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_txt)
    with open(os.path.join(d, "system_model.md"), "w", encoding="utf-8") as f:
        f.write(model_txt)
    return d, os.path.join(d, ".hunt_active")


# ── A3. FIX-1 (OBS-1, ethena-live 2026-08-12): _should_nudge honors a BUILT model.
# Section A above writes ONLY the ledger (mk), NOT system_model.md -> exactly why OBS-1 slipped through (a real
# system_model.md + scout PENDING was never tested). Here mk2 writes BOTH files -- both directions.
print("── A3. FIX-1 _should_nudge honors built system_model.md (OBS-1 symmetry)")
# FIX1-a: scout PENDING + REAL model (real I-NN in system_model.md), no BUILDING/NA -> SILENT (was a false fire).
d, m = mk2(LOOP_HDR + SCOUT_PENDING, BASE_INV)
check("scout PENDING + built model (real I-NN) -> silent [FIX-1]", n._should_nudge(m), False)
shutil.rmtree(d, ignore_errors=True)
# FIX1-b (ethena-repro): ledger with a COUNTER 'MODEL: I-NN всего: 12' (NOT a BUILDING/NA sentinel) + real model -> SILENT.
d, m = mk2(LOOP_HDR + PRIOR_MODEL + SCOUT_PENDING, BASE_INV)
check("ethena-repro: MODEL counter + real system_model.md + scout PENDING -> silent [FIX-1]", n._should_nudge(m), False)
shutil.rmtree(d, ignore_errors=True)
# FIX1-c (reverse direction -- do NOT over-suppress): scout PENDING + EMPTY template (skeleton, no real I-NN) -> FIRE.
d, m = mk2(LOOP_HDR + SCOUT_PENDING, "## Invariants\n| I-01 | | | state | | | | | | | cold | |\n")
check("scout PENDING + empty template system_model.md (skeleton) -> FIRE [FIX-1 does not over-suppress]", n._should_nudge(m), True)
shutil.rmtree(d, ignore_errors=True)

# 9. enzyme-onyx shape: 3 axes declared, base + ONE WAVE -> 1 < 3 -> FIRE (independent of Scout Status).
d, m = mk2(LOOP_HDR + AXES_N(3), BASE_INV + WAVE(2))
check("3 axes / 1 WAVE (enzyme shape) -> FIRE", n._new_axis_needs_wave(m), True)
shutil.rmtree(d, ignore_errors=True)

# 10. Healthy: 3 axes, 3 WAVE waves (WAVE-2/3/4) -> silent (each axis has its own wave).
d, m = mk2(LOOP_HDR + AXES_N(3), BASE_INV + WAVE(2) + WAVE(3) + WAVE(4))
check("3 axes / 3 WAVE (healthy) -> silent", n._new_axis_needs_wave(m), False)
shutil.rmtree(d, ignore_errors=True)

# 11. Building this axis's wave: MODEL: BUILDING -> silent (in progress).
d, m = mk2(LOOP_HDR + AXES_N(2) + "- **MODEL: BUILDING** (строю волну оси-2)\n", BASE_INV)  # "building the axis-2 wave"
check("2 axes / base only + MODEL: BUILDING -> silent", n._new_axis_needs_wave(m), False)
shutil.rmtree(d, ignore_errors=True)

# 12. Axis marked N/A (T10 not applicable to it) -> counted as covered -> silent.
d, m = mk2(LOOP_HDR + AXES_N(2), BASE_INV + WAVE(2) + "\norder-dependent axis: N/A — вне модели / trusted\n")  # "outside the model / trusted"
check("2 axes / 1 WAVE + 1 N/A axis -> silent", n._new_axis_needs_wave(m), False)
shutil.rmtree(d, ignore_errors=True)

# 13. No T9 axes declared yet (wave-1 only) -> silent (the first wave is caught by _should_nudge, not this branch).
d, m = mk2(LOOP_HDR, BASE_INV)
check("0 T9 axes (wave-1 only) -> silent", n._new_axis_needs_wave(m), False)
shutil.rmtree(d, ignore_errors=True)

# 14. Axis counter placeholder `{…}` -> n=0 -> silent (template_sentinel hygiene).
d, m = mk2(LOOP_HDR + "- **T9 restart axes used:** {0-3+, list}\n", BASE_INV + WAVE(2))
check("axis counter in {…} -> n=0 -> silent", n._new_axis_needs_wave(m), False)
shutil.rmtree(d, ignore_errors=True)


# ── A4. _manual_scout_without_hybrid PER-WAVE (enzymefinance 2026-08-19) -- HYBRID fan-out on EVERY wave.
# Previously the global `_hybrid_logged` silenced after wave-1 forever -> waves 2-3 were driven by manual cold
# scouts silently. Now runs < waves -> nudge at the Agent boundary (preventive). Tests PROVE per-wave behavior.
print("── A4. _manual_scout_without_hybrid PER-WAVE (HYBRID on every wave, enzyme)")
FAN = lambda k: "".join("- HYBRID-fanout: ось-%d — wf_run%04d / 5 агентов\n" % (i, i * 13 + 7) for i in range(1, k + 1))  # "axis-N", "5 agents"
SCOUT_PROMPT = "scout по I-13 на всех путях (найди где не enforced), партиции по инвариантам"  # Russian regex input: "scout over I-13 on all paths (find where not enforced), partitions by invariants"
NONSCOUT_PROMPT = "прочитай audit.pdf и верни summary в корпус для модели"  # Russian regex input: "read audit.pdf and return a summary to the corpus for the model"

# A4-1: 2 waves (base+WAVE-2), 1 fan-out run + scout prompt -> FIRE (wave-2 without hybrid: 1<2). MAIN case.
d, m = mk2(LOOP_HDR + FAN(1), BASE_INV + WAVE(2))
check("2 waves + 1 fan-out + scout prompt -> FIRE (wave-2 without hybrid, enzyme)", n._manual_scout_without_hybrid(m, SCOUT_PROMPT), True)
shutil.rmtree(d, ignore_errors=True)
# A4-2: 2 waves, 2 runs -> silent (fan-out keeps up with waves).
d, m = mk2(LOOP_HDR + FAN(2), BASE_INV + WAVE(2))
check("2 waves + 2 fan-outs + scout prompt -> silent (fan-out keeps up)", n._manual_scout_without_hybrid(m, SCOUT_PROMPT), False)
shutil.rmtree(d, ignore_errors=True)
# A4-3: 1 wave, 0 runs + scout -> FIRE (wave-1 without hybrid: 0<1, old behavior preserved).
d, m = mk2(LOOP_HDR, BASE_INV)
check("1 wave + 0 fan-outs + scout prompt -> FIRE (wave-1 without hybrid)", n._manual_scout_without_hybrid(m, SCOUT_PROMPT), True)
shutil.rmtree(d, ignore_errors=True)
# A4-4: 1 wave, 1 run + scout -> silent (hybrid on wave-1 done).
d, m = mk2(LOOP_HDR + FAN(1), BASE_INV)
check("1 wave + 1 fan-out + scout prompt -> silent (hybrid done)", n._manual_scout_without_hybrid(m, SCOUT_PROMPT), False)
shutil.rmtree(d, ignore_errors=True)
# A4-4b (enzymefinance 2026-08-19 counter fix): a BARE runId in a WAVE-MERGE heading counts as a run
# (enzyme logs `### WAVE-N MERGE (HYBRID-веер <id>...)`, not the `wf_` form). 2 waves + 2 bare ids -> silent.
# Without the fix the counter would see 0 bare ids -> 0<2 -> false FIRE.
_BARE_MERGE = ("### WAVE-3 MERGE (HYBRID-веер wz9twjv1b, 8 агентов)\n"
               "### WAVE-4 MERGE (HYBRID-веер w2rfh09y8, 8 агентов)\n")  # "HYBRID fan-out", "8 agents" -- regex input
d, m = mk2(LOOP_HDR + _BARE_MERGE, BASE_INV + WAVE(2))
check("2 waves + 2 bare runIds in MERGE headings + scout -> silent (nudge counter sees bare ids)",
      n._manual_scout_without_hybrid(m, SCOUT_PROMPT), False)
shutil.rmtree(d, ignore_errors=True)
# A4-5 anti-FP: non-scout prompt (research reading) -> silent regardless of fan-outs/waves.
d, m = mk2(LOOP_HDR + FAN(1), BASE_INV + WAVE(2))
check("2 waves + non-scout prompt -> silent (research reading, not a fan-out)", n._manual_scout_without_hybrid(m, NONSCOUT_PROMPT), False)
shutil.rmtree(d, ignore_errors=True)
# A4-6 anti-FP: MODEL: N/A -> silent (CLASSIC/manual ok, T10 not applicable).
d, m = mk2(LOOP_HDR + FAN(1) + "- **MODEL: N/A — single-file** \n", BASE_INV + WAVE(2))
check("MODEL: N/A + scout prompt -> silent (T10 not applicable)", n._manual_scout_without_hybrid(m, SCOUT_PROMPT), False)
shutil.rmtree(d, ignore_errors=True)


# ── A5. _invariants_inline_not_modeled (enzymefinance 2026-08-19) -- invariants IN ARGS, not in the model.
# The hunter launches a fan-out with I-48..I-64 formulated in args, not built in system_model.md
# (model-first violation). We catch: args I-NN not in model.
print("── A5. _invariants_inline_not_modeled (invariants in fan-out args, not in the model, enzyme)")
INLINE_PROMPT = "divergence_fanout по I-48, I-49, I-61 — проверь enforcement на всех путях"     # 3 new ("over ... -- check enforcement on all paths")
EXISTING_PROMPT = "divergence_fanout по I-01, I-02 — проверь enforcement"                        # in the model
ONE_NEW_PROMPT = "scout по I-48 (единичная ссылка)"                                              # 1 new ("single reference")

# A5-1: model = I-01..03, prompt = I-48/49/61 (3 new, not in model) -> FIRE. MAIN enzyme case.
d, m = mk2(LOOP_HDR, BASE_INV)
check("model I-01..03 + args I-48/49/61 (3 new) -> FIRE (invariants in args, not in model)",
      n._invariants_inline_not_modeled(m, INLINE_PROMPT), True)
shutil.rmtree(d, ignore_errors=True)
# A5-2 anti-FP: prompt references EXISTING I-01/02 (in model) -> silent.
d, m = mk2(LOOP_HDR, BASE_INV)
check("model I-01..03 + args I-01/02 (in model) -> silent (not inline)",
      n._invariants_inline_not_modeled(m, EXISTING_PROMPT), False)
shutil.rmtree(d, ignore_errors=True)
# A5-3 anti-FP: 1 new reference (<min_missing=2) -> silent (not an inline wave, single ref).
d, m = mk2(LOOP_HDR, BASE_INV)
check("model I-01..03 + args 1 new I-48 (<2) -> silent (single reference)",
      n._invariants_inline_not_modeled(m, ONE_NEW_PROMPT), False)
shutil.rmtree(d, ignore_errors=True)
# A5-4 anti-FP: MODEL: BUILDING -> silent (building the wave).
d, m = mk2(LOOP_HDR + "- **MODEL: BUILDING** (строю волну)\n", BASE_INV)  # "building the wave"
check("MODEL: BUILDING + args I-48/49/61 -> silent (building the wave)",
      n._invariants_inline_not_modeled(m, INLINE_PROMPT), False)
shutil.rmtree(d, ignore_errors=True)
# A5-5 anti-FP: some of the new ones are already in the model -- missing<2 -> silent. Model I-01..03 + I-48 built, args I-01/48/49?
d, m = mk2(LOOP_HDR, BASE_INV + "- **I-48** [state] W. check: путь? pred: ENFORCED\n")
check("model I-01..03+48 + args I-48/49 (1 missing) -> silent (missing<2)",
      n._invariants_inline_not_modeled(m, "fanout по I-48, I-49"), False)
shutil.rmtree(d, ignore_errors=True)
# A5-6: backfill done -- all args I-NN are now in the model -> silent (satisfiable).
d, m = mk2(LOOP_HDR, BASE_INV + "- **I-48** [s] a. check: c? pred: E\n- **I-49** [s] b. check: c? pred: E\n- **I-61** [s] c. check: c? pred: E\n")
check("backfill: I-48/49/61 in model + same args -> silent (model-first restored)",
      n._invariants_inline_not_modeled(m, INLINE_PROMPT), False)
shutil.rmtree(d, ignore_errors=True)


# ── A6. _scout_signals_new_axis (enzymefinance 2026-08-19) -- new-axis/T9-restart -> entry discipline.
# On continuation the hunter announces "COLD RESTART (T9) on a new axis" and spawns plain cold scouts, bypassing
# axis-queue->I-NN->HYBRID. Robust to a placeholder T9 counter (on which _new_axis_needs_wave is blind).
print("── A6. _scout_signals_new_axis (T9-restart/new-axis -> I-NN+HYBRID, not plain scouts, enzyme)")
T9_PROMPT = "Прогоняю COLD RESTART (T9) на новой оси — core redeem-арифметика. Спавлю 2 cold-субагента."  # Russian regex input: "Running COLD RESTART (T9) on a new axis -- core redeem arithmetic. Spawning 2 cold subagents."
RESEARCH_PROMPT = "прочитай audit.pdf и верни summary в корпус для модели"  # Russian regex input (same as NONSCOUT_PROMPT)

# A6-1: T9-restart signal + model built -> FIRE. MAIN enzyme case.
d, m = mk2(LOOP_HDR, BASE_INV)
check("T9-restart/new-axis prompt + model -> FIRE (entry discipline, not plain scouts) [enzyme]",
      n._scout_signals_new_axis(m, T9_PROMPT), True)
shutil.rmtree(d, ignore_errors=True)
# A6-2 anti-FP: research reading (no new-axis signal) -> silent.
d, m = mk2(LOOP_HDR, BASE_INV)
check("research reading (no new-axis signal) -> silent", n._scout_signals_new_axis(m, RESEARCH_PROMPT), False)
shutil.rmtree(d, ignore_errors=True)
# A6-3 anti-FP: MODEL: BUILDING -> silent (building the axis wave).
d, m = mk2(LOOP_HDR + "- **MODEL: BUILDING**\n", BASE_INV)
check("MODEL: BUILDING + T9 prompt -> silent (building the wave)", n._scout_signals_new_axis(m, T9_PROMPT), False)
shutil.rmtree(d, ignore_errors=True)
# A6-4 anti-FP: no model (skeleton) -> silent (the first wave is caught by _should_nudge).
d, m = mk2(LOOP_HDR, "## Invariants\n| I-01 | | | state | | | | | | | cold | |\n")
check("no model (skeleton) + T9 prompt -> silent (_should_nudge leads)", n._scout_signals_new_axis(m, T9_PROMPT), False)
shutil.rmtree(d, ignore_errors=True)
# A6-5: different signal phrasings -> FIRE. (Russian phrases are regex inputs -- KEEP: "cold-restart on a fresh axis", "axis change to fund-core")
for phrase in ["cold-restart на свежей оси", "new axis: redeem core", "смена оси на fund-core", "fresh axes probe"]:
    d, m = mk2(LOOP_HDR, BASE_INV)
    check("signal '%s' -> FIRE" % phrase[:22], n._scout_signals_new_axis(m, phrase), True)
    shutil.rmtree(d, ignore_errors=True)


# ── A7. _agent_while_fanout_due (capyfi 2026-08-25) -- STATE-based fan-out-due, a task-only cold agent is caught.
# A real cold-agent prompt describes the TASK ("verify deployed-vs-repo"), without scout/new-axis words -> the
# phrase-keyed branches (A4/A6) stay silent. This detector keys on STATE (runs<waves); the prompt is only a negative filter.
print("── A7. _agent_while_fanout_due (STATE-based fan-out due, task-only cold agent, capyfi)")
TASK_ONLY = "You are a cold verification agent. Verify deployed Comptroller-impl vs repo HEAD for bytecode divergence."
RESEARCH_A7 = "Research latest Compound fork incidents on the web and summarize for the model."
T4_FINDING = "Cold verifier maker != checker: re-derive whether finding D-01 is real, adversarial."
# A7-1: 2 waves (WAVE-2), 1 fan-out (runs=1<2), task-only cold agent (no scout words) -> FIRE. MAIN capyfi case.
d, m = mk2(LOOP_HDR + FAN(1), BASE_INV + WAVE(2))
check("2 waves + 1 fan-out + task-only cold agent (no scout words) -> FIRE (state-based, capyfi)",
      n._agent_while_fanout_due(m, TASK_ONLY), True)
shutil.rmtree(d, ignore_errors=True)
# A7-2 anti-FP: research agent -> silent (negative filter).
d, m = mk2(LOOP_HDR + FAN(1), BASE_INV + WAVE(2))
check("2 waves + 1 fan-out + research agent -> silent (research excluded)", n._agent_while_fanout_due(m, RESEARCH_A7), False)
shutil.rmtree(d, ignore_errors=True)
# A7-3 anti-FP: T4 verifier of a FINDING (D-01) -> silent (negative filter; "verify deployed-vs-repo" WITHOUT a finding is NOT excluded).
d, m = mk2(LOOP_HDR + FAN(1), BASE_INV + WAVE(2))
check("2 waves + 1 fan-out + T4 verifier of a finding (D-01) -> silent (T4 excluded)", n._agent_while_fanout_due(m, T4_FINDING), False)
shutil.rmtree(d, ignore_errors=True)
# A7-4 anti-FP: fan-out keeps up (runs>=waves) -> silent (not due).
d, m = mk2(LOOP_HDR + FAN(3), BASE_INV + WAVE(2))
check("3 waves + 3 fan-outs (runs>=waves) + task-only -> silent (fan-out not due)", n._agent_while_fanout_due(m, TASK_ONLY), False)
shutil.rmtree(d, ignore_errors=True)
# A7-5 anti-FP: MODEL: BUILDING -> silent (fan-out too early).
d, m = mk2(LOOP_HDR + FAN(1) + "- **MODEL: BUILDING**\n", BASE_INV + WAVE(2))
check("MODEL: BUILDING + task-only -> silent (fan-out too early)", n._agent_while_fanout_due(m, TASK_ONLY), False)
shutil.rmtree(d, ignore_errors=True)


# ── A8. HARD-BLOCK main() (debridge 2026-08-25: 3rd recurrence, the soft nudge does not stop it) -- ad-hoc cold-Agent
# while fan-out is due -> PreToolUse DENY. Narrow: task-only (no scout words), NOT research/T4, NOT Workflow.
print("── A8. HARD-BLOCK: ad-hoc cold-Agent on a new axis while fan-out is due -> DENY")


def agent_out(prompt, ledger_txt, model_txt, tool="Agent"):
    """main() with a prompt; returns RAW stdout (to check deny/HARD-BLOCK)."""
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_txt)
    with open(os.path.join(d, "system_model.md"), "w", encoding="utf-8") as f:
        f.write(model_txt)
    marker = os.path.join(d, ".hunt_active")
    with open(marker, "w", encoding="utf-8") as f:
        f.write("hunt\ns-hb\n")
    n._owned_markers = lambda cur: [(os.path.getmtime(marker), marker)]
    sb, ob = sys.stdin, sys.stdout
    sys.stdin = io.StringIO(json.dumps({"tool_name": tool, "session_id": "s-hb", "tool_input": {"prompt": prompt}}))
    sys.stdout = io.StringIO()
    try:
        try:
            n.main()
        except SystemExit:
            pass
        out = sys.stdout.getvalue()
    finally:
        sys.stdin, sys.stdout = sb, ob
        shutil.rmtree(d, ignore_errors=True)
    return out


DENY_LEDGER = LOOP_HDR + AXES_N(3)      # T9 axes declared, 0 fan-outs
DENY_MODEL = BASE_INV + WAVE(1)         # model + WAVE-1 -> waves=2; runs=0 -> fan-out due
# A8-1 MAIN: task-only cold-Agent (verify deployed-vs-repo, WITHOUT scout words) -> DENY (capyfi/debridge shape).
_o = agent_out("You are a cold verification agent. Verify deployed Comptroller vs repo HEAD for bytecode divergence.", DENY_LEDGER, DENY_MODEL)
check("task-only cold-Agent + fan-out due -> DENY (hard-block)", ('"deny"' in _o and "HARD-BLOCK" in _o), True)
# A8-2 anti-block: proper scout worker (scout+I-NN) -> NOT deny (soft path). (Russian prompt is a regex input: "... enforced on all paths")
_o = agent_out("scout partition P1 falsify I-06 enforced на всех путях", DENY_LEDGER, DENY_MODEL)
check("scout worker (scout+I-NN) + fan-out due -> NOT deny (soft)", '"deny"' in _o, False)
# A8-3 anti-block: research agent -> NOT deny (negative filter).
_o = agent_out("Research the latest Compound fork incidents on the web and summarize for the model.", DENY_LEDGER, DENY_MODEL)
check("research agent + fan-out due -> NOT deny", '"deny"' in _o, False)
# A8-4 anti-block: T4 verifier of a finding (D-01) -> NOT deny (negative filter).
_o = agent_out("Cold verifier maker != checker: re-derive whether finding D-01 is real, adversarial.", DENY_LEDGER, DENY_MODEL)
check("T4 verifier of a finding (D-01) + fan-out due -> NOT deny", '"deny"' in _o, False)
# A8-5 anti-block: fan-out ALREADY run (runs>=waves) -> task-only NOT deny.
_o = agent_out("cold agent: analyze fee rounding precision loss", DENY_LEDGER + FAN(2), DENY_MODEL)
check("task-only + fan-out NOT due (runs>=waves) -> NOT deny", '"deny"' in _o, False)
# A8-6 anti-block: Workflow (fan-out) -> NOT deny (block only Agent/Task). (Russian prompt is a regex input: "divergence_fanout hybrid fan-out over I-NN")
_o = agent_out("divergence_fanout hybrid веер по I-NN", DENY_LEDGER, DENY_MODEL, tool="Workflow")
check("Workflow (fan-out) + fan-out due -> NOT deny (block only Agent/Task)", '"deny"' in _o, False)


print("── B. main() e2e (tool match, active hunt, debounce)")


def run_main(tool, ledger_txt, sid="sid-1", prime_debounce=False, model_txt=None):
    """Runs main() with _owned_markers monkeypatched to a temp marker; captures stdout."""
    d, marker = mk(ledger_txt)
    if model_txt is not None:
        with open(os.path.join(d, "system_model.md"), "w", encoding="utf-8") as f:
            f.write(model_txt)
    with open(marker, "w", encoding="utf-8") as f:
        f.write("hunt\n%s\n" % sid)  # marker as in production: line 2 = session_id
    if prime_debounce:
        with open(os.path.join(d, ".last_model_nudge"), "w", encoding="utf-8") as f:
            f.write("0")
        os.utime(os.path.join(d, ".last_model_nudge"), None)  # fresh -> debounced
    n._owned_markers = lambda cur: [(os.path.getmtime(marker), marker)]
    stdin_bak, stdout_bak = sys.stdin, sys.stdout
    sys.stdin = io.StringIO(json.dumps({"tool_name": tool, "session_id": sid}))
    sys.stdout = io.StringIO()
    try:
        try:
            n.main()
        except SystemExit:
            pass
        out = sys.stdout.getvalue()
    finally:
        sys.stdin, sys.stdout = stdin_bak, stdout_bak
        shutil.rmtree(d, ignore_errors=True)
    return "MODEL-FIRST" in out


check("Agent + untouched template + active hunt -> FIRE", run_main("Agent", pristine), True)
check("Workflow (scout fan-out) + new axis (old model+PENDING) -> FIRE",
      run_main("Workflow", LOOP_HDR + PRIOR_MODEL + SCOUT_PENDING), True)
check("Bash (not a subagent) -> silent", run_main("Bash", pristine), False)
check("Agent + new axis without a wave (OBS-24, enzyme shape) -> FIRE",
      run_main("Agent", LOOP_HDR + AXES_N(3), model_txt=BASE_INV + WAVE(2)), True)
check("Agent + MODEL: BUILDING -> silent",
      run_main("Agent", LOOP_HDR + "- **MODEL: BUILDING**\n" + SCOUT_PENDING), False)
check("Agent + Scout DONE -> silent", run_main("Agent", LOOP_HDR + PRIOR_MODEL + SCOUT_DONE), False)
check("Agent + debounced (already nudged <120s ago) -> silent",
      run_main("Agent", pristine, prime_debounce=True), False)

# no active hunt -> silent (monkeypatch returns empty)
d, marker = mk(pristine)
n._owned_markers = lambda cur: []
sb, ob = sys.stdin, sys.stdout
sys.stdin = io.StringIO(json.dumps({"tool_name": "Agent", "session_id": "x"}))
sys.stdout = io.StringIO()
try:
    try:
        n.main()
    except SystemExit:
        pass
    _out = sys.stdout.getvalue()
finally:
    sys.stdin, sys.stdout = sb, ob
    shutil.rmtree(d, ignore_errors=True)
check("no active .hunt_active -> silent", "MODEL-FIRST" in _out, False)


print("── C. OBS-23 mid-turn depth-guard (Edit/Write writes Depth-Lead/D-NN before I-NN, solo mode)")

# _writes_depth unit
check("_writes_depth: real Depth-Lead (D-02 — 2/5) -> True",
      n._writes_depth("- **Depth-Lead:** D-02 — 2/5 (oracle→verifier)"), True)
check("_writes_depth: D-NN row -> True",
      n._writes_depth("| D-01 | I-03 | oracle.sol:10 | ABSENT |"), True)
check("_writes_depth: template placeholder {… H-03 — 3/5 …} -> False (not counted)",
      n._writes_depth("- **Depth-Lead:** {… H-03 — 3/5 (chain) …}"), False)
check("_writes_depth: plain text without depth -> False",
      n._writes_depth("- added hypothesis H-05 about oracle"), False)

# ── _model_has_real_invariant: detector-blind-spot fix (1inch long-run B: false fire) ──
# Previously the pipe form required EXACTLY the 7-column contract (`len>6 and cells[2] and cells[6]`) -> a 5-column
# model table and a bullet with pred/check on line breaks were read as "not built" -> the nudge falsely fired on a
# really built model every turn. Fix: pipe of any width (id+desc+>=1 cell) + multi-line bullet.
check("_mhri: 5-column filled table -> True (was False = false nudge)",
      n._model_has_real_invariant(
          "| id | invariant | pred | check | status |\n|---|---|---|---|---|\n"
          "| I-01 | supply cap | pred: total<=cap | check: require at mint | ENFORCED |"), True)
check("_mhri: 7-column contract filled -> True (no regression)",
      n._model_has_real_invariant("| I-01 | band enforced | x | state | y | z | pred text | w |"), True)
check("_mhri: skeleton row `| I-01 | | | state | … |` -> False (nudge correctly fires on an empty one)",
      n._model_has_real_invariant("| I-01 | | | state | | | | | | | cold | |"), False)
check("_mhri: multi-line bullet (pred/check on line breaks) -> True (was False)",
      n._model_has_real_invariant(
          "- **I-01** (invalidation-before-interaction):\n"
          "  pred: state written before external call\n"
          "  check: OrderMixin.sol:337 invalidates pre-hook\n"), True)
check("_mhri: single-line bullet check+pred -> True (no regression)",
      n._model_has_real_invariant(
          "- **I-01** [state] Backing conservation. check: все пути. pred: ENFORCED"), True)  # "all paths"
check("_mhri: empty bullet `- **I-01** (name):` without pred/check -> False",
      n._model_has_real_invariant("- **I-01** (name):"), False)
check("_mhri: bullet, but pred without check in the block -> False (BOTH needed)",
      n._model_has_real_invariant("- **I-01** (x):\n  pred: something holds\n"), False)
check("_mhri: empty contract template (real file) -> False (nudge fires on an empty one)",
      n._model_has_real_invariant(open(
          _os.path.join(_TK, "sessions", "_methodology", "system_model_template.md"),
          encoding="utf-8").read()), False)

# P1 (katana 2026-07-29): "model built" = I-NN with FILLED check+pred (an empty template
# `| I-01 | | | … |` no longer counts). The fixture is the real bullet format with check+pred.
INN_MODEL = ("## Invariants\n"
             "- **I-01** [state] Backing conservation. check: все пути обновляют backing. pred: ENFORCED\n"  # "all paths update backing"
             "- **I-02** [state] Mint 1:1. check: нет пути mint без deposit. pred: ABSENT\n")  # "no mint path without deposit"
DL_WRITE = "- **Depth-Lead:** D-02 — 2/5 (oracle→verifier)"


def run_edit(new, ledger_txt, model_txt=None, sid="e-1"):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_txt)
    if model_txt is not None:
        with open(os.path.join(d, "system_model.md"), "w", encoding="utf-8") as f:
            f.write(model_txt)
    marker = os.path.join(d, ".hunt_active")
    with open(marker, "w", encoding="utf-8") as f:
        f.write("hunt\n%s\n" % sid)
    n._owned_markers = lambda cur: [(os.path.getmtime(marker), marker)]
    sb, ob = sys.stdin, sys.stdout
    sys.stdin = io.StringIO(json.dumps(
        {"tool_name": "Edit", "session_id": sid, "tool_input": {"new_string": new}}))
    sys.stdout = io.StringIO()
    try:
        try:
            n.main()
        except SystemExit:
            pass
        out = sys.stdout.getvalue()
    finally:
        sys.stdin, sys.stdout = sb, ob
        shutil.rmtree(d, ignore_errors=True)
    return "mid-turn depth-guard" in out


check("🔴 Edit Depth-Lead + EMPTY model (ondo case) -> FIRE",
      run_edit(DL_WRITE, LOOP_HDR, model_txt=None), True)
check("🔴 Edit D-NN row + empty model -> FIRE",
      run_edit("| D-02 | I-04 | o.sol:7 | ABSENT |", LOOP_HDR, model_txt=None), True)
check("Edit Depth-Lead + I-NN BUILT (model exists) -> silent",
      run_edit(DL_WRITE, LOOP_HDR, model_txt=INN_MODEL), False)
check("Edit Depth-Lead + MODEL: N/A -> silent",
      run_edit(DL_WRITE, LOOP_HDR + "- **MODEL: N/A — web2 frontend**\n", model_txt=None), False)
check("Edit template depth-lead placeholder -> silent (not a real write)",
      run_edit("- **Depth-Lead:** {… H-03 — 3/5 …}", LOOP_HDR, model_txt=None), False)
check("Edit without depth-lead/D-NN (ordinary edit) -> silent",
      run_edit("- added H-07 about access-control", LOOP_HDR, model_txt=None), False)

print("── C1b. formal-model gap (jetinfosystems 2026-08-14): mature ledger + empty formal model")
# web2/dapphunt flow: the hunter models INFORMALLY in the ledger (endpoint map + H-NN), works via Bash
# probes -> neither the scout trigger (Agent) nor the depth-lead Edit fires. Branch 2b catches by DIVERGENCE:
# >=4 unique H-NN in the ledger, while the formal system_model.md is empty (not has_real_invariant) and not N/A/BUILDING.
MATURE = LOOP_HDR + ("## Active Hypotheses\n- **H-01** auth\n- **H-02** bola\n- **H-03** ssrf\n"
                     "- **H-04** idor\n- **H-05** csrf\n")
YOUNG = LOOP_HDR + "## Active Hypotheses\n- **H-01** auth\n- **H-02** bola\n"   # <4 H-NN


def run_edit_gap(new, ledger_txt, model_txt=None, sid="g-1"):
    """Like run_edit, but checks the branch-2b marker (MODEL_GAP_REMINDER carries 'formal-model gap')."""
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_txt)
    if model_txt is not None:
        with open(os.path.join(d, "system_model.md"), "w", encoding="utf-8") as f:
            f.write(model_txt)
    marker = os.path.join(d, ".hunt_active")
    with open(marker, "w", encoding="utf-8") as f:
        f.write("hunt\n%s\n" % sid)
    n._owned_markers = lambda cur: [(os.path.getmtime(marker), marker)]
    sb, ob = sys.stdin, sys.stdout
    sys.stdin = io.StringIO(json.dumps(
        {"tool_name": "Edit", "session_id": sid, "tool_input": {"new_string": new}}))
    sys.stdout = io.StringIO()
    try:
        try:
            n.main()
        except SystemExit:
            pass
        out = sys.stdout.getvalue()
    finally:
        sys.stdin, sys.stdout = sb, ob
        shutil.rmtree(d, ignore_errors=True)
    return "formal-model gap" in out


check("🔴 mature ledger (5 H-NN) + empty model (None) -> FIRE formal-model gap",
      run_edit_gap("- updated the endpoint map", MATURE, model_txt=None), True)
check("🔴 mature ledger + empty template skeleton (no real I-NN) -> FIRE",
      run_edit_gap("- edit", MATURE, model_txt="## Invariants\n| AC-I01 | | | object-authz | | | | | | | cold | |\n"), True)
check("mature ledger + model BUILT (real I-NN) -> silent",
      run_edit_gap("- edit", MATURE, model_txt=INN_MODEL), False)
check("mature ledger + MODEL: N/A -> silent",
      run_edit_gap("- edit", MATURE + "- **MODEL: N/A — static site**\n", model_txt=None), False)
check("mature ledger + MODEL: BUILDING -> silent (model being built)",
      run_edit_gap("- edit", MATURE + "- **MODEL: BUILDING**\n", model_txt=None), False)
check("IMMATURE ledger (2 H-NN < 4) + empty model -> silent (anti-FP fresh hunt)",
      run_edit_gap("- edit", YOUNG, model_txt=None), False)

print("── C2. OBS-24 solo channel (folksfinance 2026-08-01): Edit on a new axis without a wave -> FIRE")
# folksfinance shape: instance in SOLO (depth-lead-first, scout DEFERRED) reads the code of a new axis and writes
# the ledger via Edit. axes=1 (oracle restart), WAVE-2 NOT yet built -> the new_axis branch catches on ANY
# edit, not only depth-lead (no Agent event in solo). `run_edit` prints on a MODEL-FIRST match.


def edit_fires_axis(new, ledger_txt, model_txt):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_txt)
    with open(os.path.join(d, "system_model.md"), "w", encoding="utf-8") as f:
        f.write(model_txt)
    marker = os.path.join(d, ".hunt_active")
    with open(marker, "w", encoding="utf-8") as f:
        f.write("hunt\ns-fx\n")
    n._owned_markers = lambda cur: [(os.path.getmtime(marker), marker)]
    sb, ob = sys.stdin, sys.stdout
    sys.stdin = io.StringIO(json.dumps({"tool_name": "Edit", "session_id": "s-fx", "tool_input": {"new_string": new}}))
    sys.stdout = io.StringIO()
    try:
        try:
            n.main()
        except SystemExit:
            pass
        out = sys.stdout.getvalue()
    finally:
        sys.stdin, sys.stdout = sb, ob
        shutil.rmtree(d, ignore_errors=True)
    return "OBS-24" in out  # AXIS_REMINDER carries the OBS-24 marker

# 🔴 Edit NOT about depth-lead (ordinary ledger edit), but axis-2 declared without a wave -> FIRE (solo channel).
check("Edit(ordinary) + 1 axis / 0 WAVE (solo, before the wave is built) -> FIRE",
      edit_fires_axis("- reading oracle node code", LOOP_HDR + AXES_N(1), BASE_INV), True)
# Axis wave built (WAVE-2 exists) -> silent even on Edit.
check("Edit + 1 axis / 1 WAVE (wave built) -> silent",
      edit_fires_axis("- edit", LOOP_HDR + AXES_N(1), BASE_INV + WAVE(2)), False)
# MODEL: BUILDING (building the axis wave) -> silent.
check("Edit + 1 axis + MODEL: BUILDING -> silent",
      edit_fires_axis("- building I-NN", LOOP_HDR + AXES_N(1) + "- **MODEL: BUILDING**\n", BASE_INV), False)

print("── C3. OBS-27 scout-prompt WAVE-N (granite 2026-08-04): Agent 'WAVE-2 scout' while the wave is not built")
INV_ONLY = "## Invariants\n- **I-01** [state] x. check: y? pred: ENFORCED\n- **I-02** [state] z. check: w? pred: ENFORCED\n"
WITH_W2 = INV_ONLY + "\n### WAVE-2 инварианты\n| ID | Ф | check | Класс | comp | pred | Статус |\n|---|---|---|---|---|---|---|\n| I-13 | ф | ч | state | c | ENFORCED | ENFORCED |\n"  # Russian table header/section name kept (parsed by the hook)


def agent_scout(prompt, ledger_txt, model_txt):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_txt)
    with open(os.path.join(d, "system_model.md"), "w", encoding="utf-8") as f:
        f.write(model_txt)
    marker = os.path.join(d, ".hunt_active")
    with open(marker, "w", encoding="utf-8") as f:
        f.write("hunt\ns-w2\n")
    n._owned_markers = lambda cur: [(os.path.getmtime(marker), marker)]
    sb, ob = sys.stdin, sys.stdout
    sys.stdin = io.StringIO(json.dumps({"tool_name": "Agent", "session_id": "s-w2",
                                        "tool_input": {"prompt": prompt}}))
    sys.stdout = io.StringIO()
    try:
        try:
            n.main()
        except SystemExit:
            pass
        out = sys.stdout.getvalue()
    finally:
        sys.stdin, sys.stdout = sb, ob
        shutil.rmtree(d, ignore_errors=True)
    return "OBS-24" in out  # AXIS_REMINDER

# 🔴 granite miss: scout explicitly "WAVE-2", no wave in the model, T9 counter=0 -> FIRE (OBS-24 was blind).
check("Agent 'WAVE-2 cold scout stx-claim' + no WAVE-2 in model -> FIRE",
      agent_scout("WAVE-2 cold scout: stx-claim theft", LOOP_HDR + AXES_N(0), INV_ONLY), True)
# WAVE-2 built -> a scout over it is legitimate -> silent.
check("Agent 'WAVE-2 scout' + WAVE-2 built -> silent",
      agent_scout("scout WAVE-2 economic-sequence conservation", LOOP_HDR + AXES_N(0), WITH_W2), False)
# scout without a wave-ref -> silent (not our branch).
check("Agent scout without WAVE-ref -> silent",
      agent_scout("scout oracle boundary enforcement I-05", LOOP_HDR + AXES_N(0), INV_ONLY), False)
# MODEL: BUILDING (building WAVE-2) -> silent.
check("Agent 'WAVE-2 scout' + MODEL: BUILDING -> silent",
      agent_scout("WAVE-2 scout", LOOP_HDR + "- **MODEL: BUILDING**\n", INV_ONLY), False)

print("── C4. OBS-28 scout names an unmodeled subsystem (granite iter-6 governance) + scoping fix")
COVERAGE = ("\n## Subsystem Model Coverage\n| Subsystem | In-scope | Model | Ref |\n|---|---|---|---|\n"
            "| Governance (governance/meta-gov) | yes | unmodeled | — |\n"
            "| Core state + accounting | yes | MODELED | — |\n")
MODEL_W_COV = INV_ONLY + COVERAGE
# governance = unmodeled -> a scout over it = bug-hunt before the model -> FIRE.
check("Agent 'governance scout' + governance unmodeled -> FIRE",
      agent_scout("governance-v1 + meta-gov integrity scout", LOOP_HDR + AXES_N(0), MODEL_W_COV), True)
# core accounting = MODELED -> a scout over it is legitimate -> silent (words of MODELED rows are not in unmodeled).
check("Agent 'accounting scout' + core MODELED -> silent",
      agent_scout("core accounting state borrower scout", LOOP_HDR + AXES_N(0), MODEL_W_COV), False)

# 🔴 scoping fix (granite): a HISTORICAL 'MODEL:BUILDING' in the TRACE must not silence the new-axis nudge.
TRACE_BUILD = (LOOP_HDR + "- **MODEL (T10):** WAVE-1 I-01..02 built\n"
               "- **Per-iteration trace:**\n  - 1 — recon; MODEL:BUILDING → awaiting the corpus\n" + AXES_N(0))
check("scoping: trace 'MODEL:BUILDING' + governance-scout -> FIRE (trace does not silence)",
      agent_scout("governance scout", TRACE_BUILD, MODEL_W_COV), True)
# but a REAL status line 'MODEL: BUILDING' -> silent (the sentinel in a status line works).
check("scoping: STATUS line 'MODEL: BUILDING' + governance-scout -> silent",
      agent_scout("governance scout", LOOP_HDR + "- **MODEL: BUILDING**\n", MODEL_W_COV), False)

print("── C5. OBS-29 model exists -> manual scout instead of HYBRID Workflow (granite/gmtrade 2026-08-04)")
HYBRID_LOG = "- 12 — launched HYBRID Scout Fan-Out (divergence_fanout.workflow.js, 7 divergence I-NN, task w60d6ty1f)\n"
SCOUT_PROMPT = "scout partition P1 falsify I-06 enforced на всех путях"  # Russian regex input: "... enforced on all paths"


def agent_hybrid(prompt, ledger_txt, model_txt):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_txt)
    with open(os.path.join(d, "system_model.md"), "w", encoding="utf-8") as f:
        f.write(model_txt)
    marker = os.path.join(d, ".hunt_active")
    with open(marker, "w", encoding="utf-8") as f:
        f.write("hunt\ns-hy\n")
    n._owned_markers = lambda cur: [(os.path.getmtime(marker), marker)]
    sb, ob = sys.stdin, sys.stdout
    sys.stdin = io.StringIO(json.dumps({"tool_name": "Agent", "session_id": "s-hy", "tool_input": {"prompt": prompt}}))
    sys.stdout = io.StringIO()
    try:
        try:
            n.main()
        except SystemExit:
            pass
        out = sys.stdout.getvalue()
    finally:
        sys.stdin, sys.stdout = sb, ob
        shutil.rmtree(d, ignore_errors=True)
    return "HYBRID SCOUT FAN-OUT" in out

# 🔴 model exists + manual by-invariant scout + HYBRID NOT logged -> FIRE (granite (d)).
check("Agent by-invariant scout + model exists + HYBRID not logged -> FIRE",
      agent_hybrid(SCOUT_PROMPT, LOOP_HDR + AXES_N(0), INV_ONLY), True)
# HYBRID already launched (logged) -> a manual follow-up is legitimate -> silent.
check("Agent scout + HYBRID already logged (launched … task) -> silent",
      agent_hybrid(SCOUT_PROMPT, LOOP_HDR + AXES_N(0) + HYBRID_LOG, INV_ONLY), False)
# non-scout Agent (corpus research) -> silent.
check("Agent 'research pyth docs' (not a scout) + model exists -> silent",
      agent_hybrid("research pyth docs and audits for model", LOOP_HDR + AXES_N(0), INV_ONLY), False)
# model NOT built -> OBS-29 is silent (the first wave is caught by _should_nudge, not this one).
check("Agent scout + model NOT built -> silent (OBS-29)",
      agent_hybrid(SCOUT_PROMPT, LOOP_HDR + AXES_N(0), "## Invariants\n(empty)\n"), False)
# MODEL: N/A -> CLASSIC manual is ok -> silent.
check("Agent scout + MODEL: N/A -> silent (CLASSIC ok)",
      agent_hybrid(SCOUT_PROMPT, LOOP_HDR + "- **MODEL: N/A — single contract**\n", INV_ONLY), False)
# anti-FP: an instructional mention of 'divergence_fanout' in a backtick/blockquote is NOT counted as a log -> FIRE.
check("Agent scout + 'divergence_fanout' only in a backtick instruction -> FIRE (not a log)",
      agent_hybrid(SCOUT_PROMPT, LOOP_HDR + AXES_N(0) + "> запусти `divergence_fanout.workflow.js`\n", INV_ONLY), True)  # "> run `...`"
# FIX-3 (ethena-live 2026-08-12): a HYPHENATED inline-Workflow log is recognized as HYBRID -> silent
# (previously `_HYBRID_LOG_RE` matched only underscore -> inline `ethena-divergence-fanout` was not counted, the nag was false).
check("Agent scout + inline log 'ethena-divergence-fanout' (hyphen) -> silent [FIX-3]",
      agent_hybrid(SCOUT_PROMPT, LOOP_HDR + AXES_N(0) + "- 3 — launched inline ethena-divergence-fanout Workflow (8 agents, wf_b7efcff8)\n", INV_ONLY), False)
# FIX-3 space variant too: 'divergence fanout' in a real log -> silent.
check("Agent scout + 'divergence fanout' (space) in the log -> silent [FIX-3]",
      agent_hybrid(SCOUT_PROMPT, LOOP_HDR + AXES_N(0) + "- 3 — ran divergence fanout over 7 I-NN, 8 agents done\n", INV_ONLY), False)

print("── D. Task 7 (§40.1 tool-output-last) — REMINDER/AXIS_REMINDER carry the new marker, "
      "existing fire/silence logic untouched (prose-only strengthening)")


def run_main_text(tool, ledger_txt, sid="sid-tol", model_txt=None):
    """Like run_main, but returns raw stdout (not a bool) -- needed for a substring grep on the new marker."""
    d, marker = mk(ledger_txt)
    if model_txt is not None:
        with open(os.path.join(d, "system_model.md"), "w", encoding="utf-8") as f:
            f.write(model_txt)
    with open(marker, "w", encoding="utf-8") as f:
        f.write("hunt\n%s\n" % sid)
    n._owned_markers = lambda cur: [(os.path.getmtime(marker), marker)]
    sb, ob = sys.stdin, sys.stdout
    sys.stdin = io.StringIO(json.dumps({"tool_name": tool, "session_id": sid}))
    sys.stdout = io.StringIO()
    try:
        try:
            n.main()
        except SystemExit:
            pass
        out = sys.stdout.getvalue()
    finally:
        sys.stdin, sys.stdout = sb, ob
        shutil.rmtree(d, ignore_errors=True)
    return out


# REMINDER (first wave, scout PENDING, model not started) now names tool-output-last explicitly.
_out_reminder = run_main_text("Agent", pristine)
check("REMINDER carries the TOOL-OUTPUT-LAST marker (§40.1)", "TOOL-OUTPUT-LAST" in _out_reminder, True)
check("REMINDER: MODEL-FIRST still present (not weakened, only extended)",
      "MODEL-FIRST" in _out_reminder, True)

# AXIS_REMINDER (new T9 axis without a wave) also carries the marker, OBS-24 not lost.
_out_axis = run_main_text("Agent", LOOP_HDR + AXES_N(3), model_txt=BASE_INV + WAVE(2))
check("AXIS_REMINDER carries the TOOL-OUTPUT-LAST marker (§40.1)", "TOOL-OUTPUT-LAST" in _out_axis, True)
check("AXIS_REMINDER: OBS-24 marker still present (not weakened)",
      "OBS-24" in _out_axis, True)

# BOLD I-NN (justlenddao 2026-08-18): `| **I-01** |` bold id is recognized -> has_real_invariant sees the model.
BOLD_MODEL = ("## Invariants\n"
              "| **I-01** | invariant description | what to check | comp | pred | ENFORCED | a.sol:1 | 2 | cold | |\n"  # "invariant description", "what to check"
              "| **I-02** | invariant two | what to check | comp | pred | ABSENT | b.sol:2 | 1 | cold | |\n")  # "invariant two"
check("bold `| **I-01** |` model -> has_real_invariant=True (was False -- justlenddao blind spot)",
      n._model_has_real_invariant(BOLD_MODEL), True)
check("regression: plain `| I-01 |` -> has_real_invariant=True",
      n._model_has_real_invariant("| I-01 | invariant | check | c | pred | ENFORCED | x | 1 | cold | |\n"), True)
check("skeleton bold `| **I-01** | | |` (empty) -> has_real_invariant=False (no over-match)",
      n._model_has_real_invariant("## Invariants\n| **I-01** | | | state | | | | | | | cold | |\n"), False)

ok = sum(results)
print("\n%d/%d model_first_nudge cases green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
