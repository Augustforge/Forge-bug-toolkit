#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression for FEAT-A: active_lowrel_exit_blocked (live hunt 2026-08-12, T4-v2 Reliability-gate).

HUNT-EXIT High/Crit does NOT release the loop until the final Reliability (2 cold agents + own T4) is recorded
and >=50%. <50% → void + bank [LOW-RELIABILITY], the loop continues. Does NOT touch _has_valid_exit (off-switch
11 sites intact) — lives in the success cascade. proof-of-firing: the test proves FIRING (A1/A3/A7).
Run: py -3 -X utf8 scripts/_methodology/lowrel_exit_replay.py
"""
import importlib.util, os, shutil, sys, tempfile

_HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks", "hunt_completeness_gate.py")
spec = importlib.util.spec_from_file_location("gate", _HOOK)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

_cur = {"dir": None}
g.freshest_active_ledger = lambda sid: (
    (os.path.join(_cur["dir"], "hypotheses.md"), _cur["dir"]) if _cur["dir"] else (None, None))

EXIT = "## Loop State\n- **HUNT-EXIT: T4-CONFIRMED High**\n"
results = []


def run(name, body, expect):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(body)
    _cur["dir"] = d
    try:
        got = bool(g.active_lowrel_exit_blocked("sid"))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok = "PASS" if got == expect else "FAIL"
    print("  [%s] %s: fired=%s expect=%s" % (ok, name, got, expect))
    results.append(ok == "PASS")


print("── active_lowrel_exit_blocked (FEAT-A T4-v2 Reliability payability-gate)")
# A1: HUNT-EXIT High, Reliability not recorded → FIRE (hold the exit, force T4-v2).
run("(A1) HUNT-EXIT + no Reliability → fire", EXIT, True)
# A2: HUNT-EXIT + Final Reliability 72% → silent (release).
run("(A2) HUNT-EXIT + Final Reliability: 72% → silent", EXIT + "- **Final Reliability: 72%**\n", False)
# A3: HUNT-EXIT + Reliability 40% (<50) → FIRE (do not submit even High/Crit).
run("(A3) HUNT-EXIT + Reliability: 40% → fire (<50)", EXIT + "- **Reliability: 40%**\n", True)
# A4: HUNT-EXIT + Reliability 50% (exactly the threshold) → silent.
run("(A4) HUNT-EXIT + Reliability: 50% (threshold) → silent", EXIT + "- **Reliability: 50%**\n", False)
# A5: no HUNT-EXIT → silent (not our concern — exit not declared).
run("(A5) no HUNT-EXIT + Reliability: 40% → silent (exit not declared)",
    "## Loop State\n- **Reliability: 40%**\n", False)
# A6: HUNT-EXIT + MANUAL → silent (manual mode is not forced).
run("(A6) HUNT-EXIT + MANUAL → silent", EXIT + "- **HUNT-MODE: MANUAL**\n", False)
# A7: HUNT-EXIT + Reliability {placeholder} → FIRE (not recorded).
run("(A7) HUNT-EXIT + Reliability {placeholder} → fire", EXIT + "- **Final Reliability: {N%}**\n", True)
# A8: HUNT-EXIT superseded (void) + Reliability 40% → silent (_has_valid_exit False → exit is not in effect).
run("(A8) HUNT-EXIT superseded (void) → silent (exit not in effect)",
    EXIT + "- HUNT-EXIT superseded: reversed on reliability\n- **Reliability: 40%**\n", False)
# A9: the LAST Reliability is taken (draft 30% → final 80%) → silent.
run("(A9) HUNT-EXIT + Reliability 30% then Final 80% → silent (the last one)",
    EXIT + "- Reliability: 30% (draft cold-agent-1)\n- **Final Reliability: 80%**\n", False)
# A10: RULES prose `> Final Reliability: 90%` (blockquote) does NOT clear it (not a field) when the real value is low.
run("(A10) blockquote prose Reliability 90% + real 40% → fire (prose is not a field)",
    EXIT + "> Final Reliability: 90% (пример в RULES)\n- **Reliability: 40%**\n", True)  # Russian fixture text kept (input data)
# A11 (Z2 judge HIGH-2): IN-PLACE fill of the template field with a PAREN `(FEAT-A — …):** 72%` → silent (recognized).
run("(A11/Z2) in-place `**Final Reliability (FEAT-A — x):** 72%` → silent (parenthetical-tolerant)",
    EXIT + "- **Final Reliability (FEAT-A — payability):** 72%\n", False)
# A12 (Z2): same format but 40% → fire (<50).
run("(A12/Z2) in-place `(FEAT-A — x):** 40%` → fire (<50)",
    EXIT + "- **Final Reliability (FEAT-A — payability):** 40%\n", True)

print("\n── active_report_template_unset (FEAT-B: Immunefi template detect)")


def runB(name, body, expect):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(body)
    _cur["dir"] = d
    try:
        got = bool(g.active_report_template_unset("sid"))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok = "PASS" if got == expect else "FAIL"
    print("  [%s] %s: fired=%s expect=%s" % (ok, name, got, expect))
    results.append(ok == "PASS")


IMMU = EXIT + "- **Platform:** Immunefi (Jito)\n"
# B1: HUNT-EXIT + Immunefi + template not chosen → FIRE.
runB("(B1) Immunefi + HUNT-EXIT + template not chosen → fire", IMMU, True)
# B2: + report-template chosen → silent.
runB("(B2) Immunefi + report-template: immunefi_dapp.md → silent", IMMU + "- report-template: immunefi_dapp.md\n", False)
# B3: another platform (HackerOne) → silent (its own flow).
runB("(B3) HackerOne + HUNT-EXIT → silent (not Immunefi)", EXIT + "- **Platform:** HackerOne\n", False)
# B4: no HUNT-EXIT → silent (too early for the template).
runB("(B4) Immunefi without HUNT-EXIT → silent", "## Loop State\n- **Platform:** Immunefi\n", False)
# B5: MANUAL → silent.
runB("(B5) Immunefi + HUNT-EXIT + MANUAL → silent", IMMU + "- **HUNT-MODE: MANUAL**\n", False)
# B6 (Z2 judge MED): a placeholder line with immunefi_dapp.md in the instruction does NOT clear the off-switch → FIRE.
# Russian placeholder text in the next line ("platform" / "choose before submitting") is gate input: kept verbatim.
runB("(B6/Z2) Immunefi + placeholder `{choose: immunefi_dapp.md}` → fire (placeholder is not a choice)",
     IMMU + "- **report-template (FEAT-B — платформа):** {выбери перед подачей: Immunefi → `templates/dapp_reports/immunefi_dapp.md`}\n", True)
# B7 (Z2): a real choice (without {}) → silent.
runB("(B7/Z2) Immunefi + report-template: immunefi_dapp.md (real) → silent",
     IMMU + "- report-template: immunefi_dapp.md выбран\n", False)

print("\n%d/%d PASS" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
