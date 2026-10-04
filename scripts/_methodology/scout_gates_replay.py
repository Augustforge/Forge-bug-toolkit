#!/usr/bin/env python3
"""Regression for the 3 Scout Fan-Out enforcement gates (Rootstock 2026-07-12):
P-B boundary-scout skipped (BOUNDARY-MAP placeholder), OPTIONAL-menu not consulted (OPT-TODO),
WAVE-2 forgotten (WAVE-2 PENDING). Run after any edit to those gate fns. Exit 1 on any FAIL.
Run: py -3 -X utf8 scripts/_methodology/scout_gates_replay.py
"""
import sys
import importlib.util, os, tempfile
import os as _os  # P4: path from __file__, not from CWD
_HOOK = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "hooks", "hunt_completeness_gate.py")
spec = importlib.util.spec_from_file_location("gate", _HOOK)
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)

def mk(txt):
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
    f.write(txt); f.close(); return f.name

# monkeypatch freshest_active_ledger to return our fixture
_cur = {"p": None}
g.freshest_active_ledger = lambda sid: (_cur["p"], os.getcwd()) if _cur["p"] else (None, None)

SCOUT_DONE = "## Scout Fan-Out\n**Status:** `DONE 2026-07-12`\n| P-B boundary/trust-perimeter (MANDATORY) | s | 2 | H-1 |\n"
def run(name, txt, fn, expect):
    _cur["p"] = mk(txt)
    got = bool(fn("sid"))
    ok = "PASS" if got == expect else "FAIL"
    print(f"  [{ok}] {name}: fired={got} expect={expect}")
    return ok == "PASS"

results = []
# 1. DONE + BOUNDARY-MAP placeholder -> boundary skip FIRES
results.append(run("boundary placeholder->fire", SCOUT_DONE + "- **BOUNDARY-MAP:** {boundary1; …}\n", g.active_ledger_boundary_scout_skipped, True))
# 2. DONE + BOUNDARY-MAP filled -> NO fire
results.append(run("boundary filled->silent", SCOUT_DONE + "- **BOUNDARY-MAP:** oracle-verifier; bridge-mint\n", g.active_ledger_boundary_scout_skipped, False))
# 3. DONE + BOUNDARY-MAP N/A -> NO fire
results.append(run("boundary N/A->silent", SCOUT_DONE + "- **BOUNDARY-MAP:** N/A — no external trust boundary\n", g.active_ledger_boundary_scout_skipped, False))
# 4. Scout PENDING -> boundary NO fire (scout_pending handles)
results.append(run("scout pending->boundary silent", "## Scout Fan-Out\n**Status:** `PENDING`\n- **BOUNDARY-MAP:** {x}\nboundary/trust-perimeter\n", g.active_ledger_boundary_scout_skipped, False))
# 5. web F1-F5 ledger (no boundary row) -> NO fire (anti-FP)
results.append(run("web-flow->boundary silent", "## Scout Fan-Out\n**Status:** `DONE`\n| F1 stake | s | 1 | H-1 |\n", g.active_ledger_boundary_scout_skipped, False))
# 6. DONE + OPT-TODO present -> optmenu FIRES
results.append(run("opt-todo->fire", SCOUT_DONE + "- **OPTIONAL-menu triage [OPT-TODO]:** {…}\n", g.active_ledger_optmenu_todo, True))
# 7. DONE + OPT-TODO removed -> NO fire
results.append(run("opt filled->silent", SCOUT_DONE + "- **OPTIONAL triage:** P8 MATCHED->scout; P7 skip-if\n", g.active_ledger_optmenu_todo, False))
# 8. WAVE-2 PENDING -> wave FIRES
results.append(run("wave-2 pending->fire", SCOUT_DONE + "- **WAVE-2:** P8 cross-chain — PENDING\n", g.active_ledger_wave_pending, True))
# 9. WAVE-2 DONE -> NO fire
results.append(run("wave-2 done->silent", SCOUT_DONE + "- **WAVE-2:** P8 cross-chain — DONE\n", g.active_ledger_wave_pending, False))
# 10. no wave line -> NO fire
results.append(run("no-wave->silent", SCOUT_DONE + "- **WAVE-2:** N/A\n", g.active_ledger_wave_pending, False))

# --- 11-18: active_ledger_scout_pending — Status canonicality (OBS-20, hyperlane 2026-07-29) ---
# The gate passes ONLY DONE/N/A/DEFERRED; PENDING AND any home-made value (IN-FLIGHT) → block.
SEC = "## Scout Fan-Out\n**Status:** `%s`\n"
results.append(run("scout PENDING -> fire", SEC % "PENDING", g.active_ledger_scout_pending, True))
results.append(run("scout IN-FLIGHT (gaming-bypass) -> fire [OBS-20]", SEC % "IN-FLIGHT (wave-1)",
                   g.active_ledger_scout_pending, True))
results.append(run("scout WIP (home-made) -> fire", SEC % "WIP", g.active_ledger_scout_pending, True))
results.append(run("scout DONE -> silent", SEC % "DONE 2026-07-29", g.active_ledger_scout_pending, False))
results.append(run("scout N/A -> silent", SEC % "N/A — single-contract", g.active_ledger_scout_pending, False))
results.append(run("scout DEFERRED -> silent", SEC % "DEFERRED → after fingerprint",
                   g.active_ledger_scout_pending, False))
results.append(run("MODEL: BUILDING + PENDING -> silent (OBS-2, model is building)",
                   "- **MODEL: BUILDING**\n" + SEC % "PENDING", g.active_ledger_scout_pending, False))
results.append(run("no Scout Fan-Out section -> silent",
                   "## Loop State\n- Iteration 1\n", g.active_ledger_scout_pending, False))

# 19-20: FP-fix (jito 2026-08-12) — template RULES prose carries `## Scout Fan-Out` in backticks (Rule 7)
# + Atom Registry stray `| status |` / Loop State "surface-status)" BEFORE the real section heading.
# naive low.find() latched onto the RULES mention and grabbed the stray status → a legit DONE read as block.
# A line-start anchor (`^## Scout Fan-Out`) fixes it: real heading, mid-line RULES mention ignored.
_RULES_FP = ("7. The `## Scout Fan-Out` section below reads `PENDING` until it is filled.\n"
             "| id | type | title | src | rank | status | closes |\n"
             "- **surface-status)** run\n\n")
results.append(run("FP: RULES-mention+stray-status + real DONE -> silent",
                   _RULES_FP + "## Scout Fan-Out (explore-wide)\n**Status:** `DONE 2026-08-12`\n",
                   g.active_ledger_scout_pending, False))
results.append(run("FP-guard: RULES-mention + real PENDING -> STILL fire",
                   _RULES_FP + "## Scout Fan-Out (explore-wide)\n**Status:** `PENDING`\n",
                   g.active_ledger_scout_pending, True))

ok = sum(results)
print(f"\n{ok}/{len(results)} scout-gate cases green")
sys.exit(0 if ok == len(results) else 1)
