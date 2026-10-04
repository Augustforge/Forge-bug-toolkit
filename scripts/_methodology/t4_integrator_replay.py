# -*- coding: utf-8 -*-
"""Replay for active_t4_integrator_missing (2026-08-18, T4-v2 3-agent).

Design: T4-v2 = split specialists A1 (validity+repro+dedup) / A2 (scope+payability+$-at-risk+triage) go
deep but are structurally blind to the validity×payability seam (veda D-01: compromised-strategist, which
revives a cap-bypass = exactly what triage would close as centralization). High/Crit needs A3 = a 3rd COLD
agent, BLIND to A1/A2's conclusions, independently re-deriving both domains + hunting the seam + tie-break.
Med/Low = 2 specialists.

feedback_hook_must_prove_firing: we prove FIRING (High/Crit exit without A3 → fire) AND the guards (A3+seam
recorded → silent; Med/Low = no valid exit → silent; A3 only in a {}-template → still fire; MANUAL)."""
import importlib.util, os, sys, time, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SESSIONS = os.path.join(ROOT, "sessions")
HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks", "hunt_completeness_gate.py")
spec = importlib.util.spec_from_file_location("gate", HOOK)
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)

SLUG = "_t4itest"
SID = "t4i-sid-1"
results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))

HEAD = "# _t4itest — Registry\n## Loop State\n- HUNT-MODE: AUTONOMOUS\n## Active\n- **I-01** a\n- **I-02** b\n- **I-03** c\n"
EXIT_HIGH = "\nHUNT-EXIT: T4-CONFIRMED High\nFinal Reliability: 72%\n"
EXIT_CRIT = "\nHUNT-EXIT: T4-CONFIRMED Critical\nFinal Reliability: 80%\n"
A1A2 = ("## Verifier Log\n- T4-A1 [validity+dedup]: CONFIRM — repro PASS, dedup clean — checker:cold-subagent\n"
        "- T4-A2 [scope+payability]: CONFIRM — in-scope, severity High, $at-risk 200k — checker:cold-subagent\n")
A3_LINE = "- T4-A3 [integrator]: SEAM-CLEAR — overall CONFIRM — seam: validity precond independent of the scope clause — checker:cold-subagent(blind)\n"


def write_ledger(body):
    d = os.path.join(SESSIONS, SLUG)
    if os.path.exists(d):
        shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(body)
    with open(os.path.join(d, ".hunt_active"), "w", encoding="utf-8") as f:
        f.write("%d\n%s" % (int(time.time()), SID))


def fires():
    return g.active_t4_integrator_missing(SID) is not None


try:
    # 1) FIRE: High submission, A1/A2 present but NO A3.
    write_ledger(HEAD + A1A2 + EXIT_HIGH)
    check("1 FIRE: High exit + A1/A2 without A3 → fire", fires())

    # 2) FIRE: Critical submission without A3.
    write_ledger(HEAD + A1A2 + EXIT_CRIT)
    check("2 FIRE: Critical exit without A3 → fire", fires())

    # 3) SILENT: High submission with A3 + seam verdict → satisfiable.
    write_ledger(HEAD + A1A2 + A3_LINE + EXIT_HIGH)
    check("3 SILENT: High exit + A3 SEAM-CLEAR → no fire", not fires())

    # 4) SILENT: Medium (no valid High/Crit exit) → A3 not required.
    write_ledger(HEAD + A1A2 + "\nHUNT-EXIT: T4-CONFIRMED Medium\n")
    check("4 SILENT: Medium (no valid exit) → no fire (A3 only on High/Crit)", not fires(),
          "valid_exit=%s" % g._has_valid_exit(HEAD + A1A2 + "\nHUNT-EXIT: T4-CONFIRMED Medium\n"))

    # 5) FIRE: A3 only in a {}-template (placeholder) → not counted → still fire.
    write_ledger(HEAD + A1A2 + "\n{T4-A3 [integrator]: SEAM-CLEAR — template example}\n" + EXIT_HIGH)
    check("5 FIRE: A3 in a {}-template → not counted → fire", fires())

    # 6) FIRE: A3 entry present but no seam verdict (incomplete) → fire.
    write_ledger(HEAD + A1A2 + "- T4-A3 [integrator]: looking at both domains\n" + EXIT_HIGH)
    check("6 FIRE: A3 without seam verdict → fire", fires())

    # 7) OFF: MANUAL.
    write_ledger(HEAD + "- **HUNT-MODE: MANUAL**\n" + A1A2 + EXIT_HIGH)
    check("7 OFF: MANUAL → no fire", not fires())

    # 8) SILENT: no exit at all (hunt in progress) → not our concern.
    write_ledger(HEAD + A1A2)
    check("8 SILENT: no HUNT-EXIT → no fire", not fires())

finally:
    d = os.path.join(SESSIONS, SLUG)
    if os.path.exists(d):
        shutil.rmtree(d, ignore_errors=True)

print("=== T4 A3-INTEGRATOR REPLAY (High/Crit submission requires a cold seam integrator) ===\n")
ok = 0
for name, passed, detail in results:
    print(("  [PASS] " if passed else "  [FAIL] ") + name + (("  — " + detail) if detail and not passed else ""))
    ok += 1 if passed else 0
print("\n%d/%d checks green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
