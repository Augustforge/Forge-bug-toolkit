#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Replay test B4 ZERO-D-NN escalation (audit 2026-08-09, Mandate 0.9) -- active_zero_divergence_unescalated.

Root cause: a hunt on a real DeFi protocol -- the model was built (T10), but `## Divergences` produced ZERO D-NN
over the whole hunt, and blind_spots.md was untouched. Mandate 0.9: zero D-NN = "the detector did not fire" -> escalate the method + log it.
It used to be prose -- B4 makes it enforced (soft-nudge). The test proves FIRING + anti-FP.

Run: py -3 -X utf8 scripts/_methodology/zero_dnn_replay.py

NOTE: the fixture strings below (model table headers, ledger "extra" lines, model prose) are inputs to the
gate's Russian-matching logic and are kept verbatim in Russian; only comments and test names are English.
"""
import importlib.util
import os
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GATE = os.path.join(ROOT, "scripts", "hooks", "hunt_completeness_gate.py")
spec = importlib.util.spec_from_file_location("gate_b4", GATE)
G = importlib.util.module_from_spec(spec)
spec.loader.exec_module(G)

# Russian header cells below ("invariant" / "what" / "resolution") are parser input: kept verbatim.
MODEL_MATURE = """## Invariants
| I-NN | инвариант | pred | status | component |
|---|---|---|---|---|
| I-01 | a | pred: x | ENFORCED | c1 |
| I-02 | b | pred: y | ENFORCED | c2 |
| I-03 | c | pred: z | ENFORCED | c3 |

## Divergences
| D-NN | что | резолюция |
|---|---|---|
"""
MODEL_WITH_DNN_ROW = MODEL_MATURE + "| D-01 | conservation gap | → H-05 |\n"
MODEL_WITH_DNN_BULLET = MODEL_MATURE + "\n- **D-01** — mint gap → open\n"
MODEL_NA = "MODEL: N/A — single-contract <300 LOC\n"


def _axes(n):
    return ", ".join("axis%d" % (i + 1) for i in range(n))


def _ledger(n_axes, extra="", iter_field=8, trace_n=0):
    """iter_field = the `Iteration #` field; trace_n = how many per-iteration-trace bullets to generate
    (long-trace case: the field is NOT updated, but the trace is long)."""
    trace = ""
    if trace_n:
        trace = "- **Per-iteration trace:**\n" + "".join("  - %d — did stuff\n" % (i + 1) for i in range(trace_n))
    return ("## Loop State\n- **Iteration #:** %d\n- **T9 restart axes used:** %s\n%s%s"
            % (iter_field, _axes(n_axes), trace, extra))


CASES = []  # (name, ledger, model, expect_fires)
# 1. real-hunt-like: mature model, 6 axes, 0 D-NN, blind_spots not mentioned -> FIRES
CASES.append(("real-hunt-like: mature model, 6 axes, 0 D-NN → FIRES", _ledger(6), MODEL_MATURE, True))
# 2. anti-FP: >=1 D-NN as a table row -> silent (the generator worked)
CASES.append(("anti-FP: D-01 row present → silent", _ledger(6), MODEL_WITH_DNN_ROW, False))
# 3. anti-FP: >=1 D-NN as a bullet -> silent
CASES.append(("anti-FP: D-01 bullet present → silent", _ledger(6), MODEL_WITH_DNN_BULLET, False))
# 4. R5 (SUD-MED-1): bare banking of an insight into blind_spots (WITHOUT changing the generator) -> FIRES (not an escalation).
# Ledger extra line is fixture input (Russian: "un-dup: the crowd models a slash that does not exist -> bank ...").
CASES.append(("R5: bare '→ bank blind_spots' without a generator switch → FIRES (not a method escalation)",
              _ledger(6, extra="⚠ un-dup: толпа моделирует slash которого нет → bank blind_spots/pattern-library\n"),
              MODEL_MATURE, True))
# 4b. R5: REAL escalation -- blind-spot + generator switch on one line -> silent (Mandate 0.9 steps 2+3).
# Ledger extra line is fixture input (Russian: "ZERO-D-NN: switched generator to model-vs-live-runtime, the silent one is logged in blind_spots.md").
CASES.append(("R5: real escalation 'switched generator to model-vs-live → blind_spots' → silent",
              _ledger(6, extra="ZERO-D-NN: сменил генератор на model-vs-live-runtime, молчащий записан в blind_spots.md\n"),
              MODEL_MATURE, False))
# 4c. R5: assumption-mining generator switch + blind-spot -> silent.
CASES.append(("R5: 'assumption-mining generator switch → blind_spots' → silent",
              _ledger(6, extra="0 D-NN → switch generator to assumption-mining; logged blind-spot\n"),
              MODEL_MATURE, False))
# 4d. R5 (root of MED-1): model PROSE contains 'blind_spots.md' (as in system_model_template:274), ledger is clean
#     -> FIRES (model prose/template no longer clears it; the off-switch looks ONLY in the ledger).
# Model prose is fixture input (Russian: "Zero divergences -> log it in blind_spots.md (template instruction).").
CASES.append(("R5: model prose 'blind_spots.md' (template-274), ledger clean → FIRES (model text does not clear it)",
              _ledger(6), MODEL_MATURE + "\nНоль дивергенций → запиши в blind_spots.md (инструкция шаблона).\n", True))
# 5. anti-FP: few axes (<3) AND few iterations (<6) -> silent
CASES.append(("anti-FP: 2 axes + iter=2 (both < threshold) → silent",
              _ledger(2, iter_field=2), MODEL_MATURE, False))
# 6. anti-FP: MODEL N/A -> silent
CASES.append(("anti-FP: MODEL N/A → silent", _ledger(6) + "\nMODEL: N/A\n", MODEL_NA, False))
# 7. anti-FP: immature model (1 I-NN) -> silent
CASES.append(("anti-FP: immature model (1 I-NN) → silent", _ledger(6),
              "| I-01 | a | pred: x | ENFORCED | c |\n", False))
# 8. FIRES: exactly at the threshold (3 axes)
CASES.append(("threshold: exactly 3 axes, 0 D-NN → FIRES", _ledger(3), MODEL_MATURE, True))
# 9. long-trace case: 0 axes, but the Iteration field is NOT updated (=1) + long trace (8) -> FIRES via the iter threshold
CASES.append(("long-trace: 0 axes, iter field=1 BUT trace=8, 0 D-NN → FIRES (iter threshold)",
              _ledger(0, iter_field=1, trace_n=8), MODEL_MATURE, True))
# 10. anti-FP: 0 axes + iter=1 + short trace (3 < threshold) -> silent (too early)
CASES.append(("anti-FP: 0 axes, iter=1, trace=3 (< ZERO_DNN_ITER) → silent",
              _ledger(0, iter_field=1, trace_n=3), MODEL_MATURE, False))
# 11. FIRES: Iteration field=6 (exactly the threshold) even without a trace -> FIRES
CASES.append(("threshold: iter field=6, 0 axes, 0 D-NN → FIRES", _ledger(0, iter_field=6), MODEL_MATURE, True))
# ── FEAT-F (live-hunt case): third armed trigger -- the number of MODEL WAVES. A rich multi-wave model, but
# T9 unused (axes<3) and the hunt is short (itr<6), 0 D-NN -> maturity by WAVES.
MODEL_3WAVES = MODEL_MATURE + (
    "\n## WAVE-2\n| I-04 | d | pred: p | ENFORCED | c4 |\n"
    "\n## WAVE-3\n| I-05 | e | pred: q | ENFORCED | c5 |\n")
MODEL_2WAVES = MODEL_MATURE + "\n## WAVE-2\n| I-04 | d | pred: p | ENFORCED | c4 |\n"
# 12. FEAT-F: 3 waves (Invariants+WAVE-2+WAVE-3), axes=0, iter=2 (<threshold), 0 D-NN -> FIRES (wave trigger).
CASES.append(("FEAT-F: 3 model waves, axes=0, iter=2, 0 D-NN → FIRES (wave trigger)",
              _ledger(0, iter_field=2), MODEL_3WAVES, True))
# 13. anti-FP: 2 waves (<ZERO_DNN_WAVES=3), axes=0, iter=2 -> silent (none of the three thresholds reached).
CASES.append(("FEAT-F anti-FP: 2 waves, axes=0, iter=2 → silent (waves<3, axes<3, iter<6)",
              _ledger(0, iter_field=2), MODEL_2WAVES, False))
# 14. anti-FP: 3 waves, but >=1 D-NN -> silent (the generator worked, the wave trigger does not matter).
CASES.append(("FEAT-F anti-FP: 3 waves + 1 D-NN → silent (generator worked)",
              _ledger(0, iter_field=2), MODEL_3WAVES + "\n- **D-01** — gap → open\n", False))


def run():
    ok = fail = 0
    for name, ledger, model, expect in CASES:
        d = tempfile.mkdtemp(prefix="b4_")
        try:
            with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
                f.write(ledger)
            G.freshest_active_ledger = lambda cid, _d=d: (os.path.join(_d, "hypotheses.md"), ROOT)
            G._model_ctx = lambda cid, _l=ledger, _m=model: (_l, _m, None)
            res = G.active_zero_divergence_unescalated("sid")
            fires = res is not None
            if fires == expect:
                ok += 1
                print("  [PASS] %s" % name)
            else:
                fail += 1
                print("  [FAIL] %s  (fires=%s expect=%s res=%r)" % (name, fires, expect, res))
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
    print("\n%d/%d B4 zero-D-NN cases green" % (ok, ok + fail))
    return fail == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
