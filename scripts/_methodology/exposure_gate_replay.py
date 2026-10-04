#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Replay test of the gate `active_exposure_scan_skipped` (P0-2, Exposure Engine, SlowMist Aug-2026).

System rule: replay test FIRST, gate SECOND. The test PROVES firing (fire on `{TODO}`/empty
with a mature model) AND the off-switch (silent on a real value / N/A / missing line / thin model /
MODEL: N/A / missing model). Monkeypatches freshest_active_ledger; the model is placed NEXT TO the ledger,
as in production (same helpers as model_gates_replay). Exit 1 on any FAIL.
Run: py -3 -X utf8 scripts/_methodology/exposure_gate_replay.py
"""
import importlib.util
import os
import shutil
import sys
import tempfile

_HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "hooks", "hunt_completeness_gate.py")
spec = importlib.util.spec_from_file_location("gate", _HOOK)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

_cur = {"dir": None}
g.freshest_active_ledger = lambda sid: (
    (os.path.join(_cur["dir"], "hypotheses.md"), _cur["dir"]) if _cur["dir"] else (None, None)
)

LEDGER_OK = "# t — Hypotheses Registry\n\n## Loop State\n- **Iteration #:** 3\n"
LEDGER_NA = LEDGER_OK + "- **MODEL: N/A — single contract <300 LOC**\n"

HDR = (
    "## Invariants\n"
    "| ID | Формула | check | Класс | Источник | component | pred | Статус | file:line | tests | crowd-heat | lib |\n"  # Russian column names kept: fixture mirrors the real ledger table format (parsed)
    "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
)


def row(i, status="ENFORCED", pred="ENFORCED"):
    return ("| I-%02d | f%d | что проверить | state | docs | vault | %s | %s | a.sol:10 | 2 | cold |  |\n"
            % (i, i, pred, status))


NEG = "\n## Missing Negatives\n\n| Тест | Негатив | Ось | Бьёт по |\n|---|---|---|---|\n| t.sol:10 | X | y | I-01 |\n"
CANON = "\n- [x] оператор канона прогнан по всем I-NN\n"


def model(rows):
    return HDR + "".join(rows) + CANON + NEG


GOOD3 = model([row(1), row(2), row(3, status="ABSENT", pred="ABSENT")])   # 3 statused → matured>=3
THIN2 = model([row(1), row(2)])                                            # <3 → off-switch

# EXPOSURE-SCAN ledger lines in various states
EX_TODO = "- **EXPOSURE-SCAN:** {TODO}\n"
EX_REAL = "- **EXPOSURE-SCAN:** 2 secrets / 0 pii / 0 data / 0\n"
EX_RUNTIME = "- **EXPOSURE-SCAN:** 1 secrets / 0 pii / 0 data / 0 [runtime]\n"
EX_NA = "- **EXPOSURE-SCAN:** N/A — репо недоступно\n"  # Russian reason text kept (fixture)
EX_EMPTY = "- **EXPOSURE-SCAN:**\n"


def setup(ledger_txt, model_txt, artifact=False):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_txt)
    if model_txt is not None:
        with open(os.path.join(d, "system_model.md"), "w", encoding="utf-8") as f:
            f.write(model_txt)
    if artifact:   # the secret_exposure_scanner producer was really run → left exposure_scan.md
        with open(os.path.join(d, "exposure_scan.md"), "w", encoding="utf-8") as f:
            f.write("# exposure scan\n")
    _cur["dir"] = d
    return d


results = []


def run(name, ledger_txt, model_txt, expect, artifact=False):
    d = setup(ledger_txt, model_txt, artifact=artifact)
    try:
        got = bool(g.active_exposure_scan_skipped("sid"))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok = got == expect
    print("  [%s] %s: fired=%s expect=%s" % ("PASS" if ok else "FAIL", name, got, expect))
    results.append(ok)


print("── active_exposure_scan_skipped (P0-Exposure sentinel-gate)")
# FIRING
run("mature model + EXPOSURE-SCAN: {TODO} → FIRE", LEDGER_OK + EX_TODO, GOOD3, True)
run("mature model + EXPOSURE-SCAN: (empty) → FIRE", LEDGER_OK + EX_EMPTY, GOOD3, True)
# NEW (jetinfosystems): a real value WITHOUT an artifact = ad-hoc grep deception → still FIRE
run("mature + real value WITHOUT exposure_scan.md → FIRE (ad-hoc grep, producer not run)",
    LEDGER_OK + EX_REAL, GOOD3, True, artifact=False)
# SILENT (producer really run / deliberately cleared / runtime path)
run("mature + real value WITH the exposure_scan.md artifact → silent (producer run)",
    LEDGER_OK + EX_REAL, GOOD3, False, artifact=True)
run("mature + [runtime] tag WITHOUT an artifact → silent (the live path writes no artifact)",
    LEDGER_OK + EX_RUNTIME, GOOD3, False, artifact=False)
run("mature model + EXPOSURE-SCAN: N/A — reason → silent", LEDGER_OK + EX_NA, GOOD3, False)
# anti-FP: no line at all (a ledger from before P0-Exposure)
run("mature model + NO EXPOSURE-SCAN line at all → silent (pre-P0 ledger, anti-FP)",
    LEDGER_OK, GOOD3, False)
# off-switch (same family as pattern_replay)
run("off-switch: thin model (2 statused < 3) + {TODO} → silent (first scout pass)",
    LEDGER_OK + EX_TODO, THIN2, False)
run("off-switch: MODEL: N/A sentinel + {TODO} → silent (ctx None)", LEDGER_NA + EX_TODO, GOOD3, False)
run("off-switch: no model at all + {TODO} → silent", LEDGER_OK + EX_TODO, None, False)

# direct contract of the _exposure_scan_unfilled parser (ledger_dir=None → the artifact check is skipped)
print("── _exposure_scan_unfilled (parser, no ledger_dir)")
for txt, exp, label in [
    (EX_TODO, True, "{TODO} → unfilled"),
    (EX_EMPTY, True, "empty → unfilled"),
    (EX_REAL, False, "real value (no ledger_dir) → filled"),
    (EX_RUNTIME, False, "[runtime] tag → filled"),
    (EX_NA, False, "N/A → filled (deliberately cleared)"),
    ("нет такой строки", False, "no such line → not-unfilled (anti-FP)"),  # first element is Russian fixture text (kept)
]:
    got = g._exposure_scan_unfilled(txt)
    ok = got == exp
    print("  [%s] %s: got=%s" % ("PASS" if ok else "FAIL", label, got))
    results.append(ok)

# parser WITH ledger_dir: a real value → the artifact decides
print("── _exposure_scan_unfilled (parser, with ledger_dir — artifact gate)")
_tmpd = tempfile.mkdtemp()
try:
    # without an artifact → held (ad-hoc deception)
    got = g._exposure_scan_unfilled(EX_REAL, _tmpd)
    print("  [%s] real value + no exposure_scan.md → unfilled(held): got=%s" %
          ("PASS" if got is True else "FAIL", got)); results.append(got is True)
    # with an artifact → filled
    with open(os.path.join(_tmpd, "exposure_scan.md"), "w", encoding="utf-8") as f:
        f.write("x")
    got = g._exposure_scan_unfilled(EX_REAL, _tmpd)
    print("  [%s] real value + exposure_scan.md present → filled: got=%s" %
          ("PASS" if got is False else "FAIL", got)); results.append(got is False)
    # [runtime] tag without an artifact → filled (live path)
    got = g._exposure_scan_unfilled(EX_RUNTIME, tempfile.mkdtemp())
    print("  [%s] [runtime] tag + no artifact → filled: got=%s" %
          ("PASS" if got is False else "FAIL", got)); results.append(got is False)
finally:
    shutil.rmtree(_tmpd, ignore_errors=True)

total = len(results)
passed = sum(results)
print("\nexposure_gate_replay: %d/%d passed" % (passed, total))
sys.exit(0 if passed == total else 1)
