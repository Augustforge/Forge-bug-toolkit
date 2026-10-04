#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression for the active_axes_without_waves gate (OBS-10, 2026-07-30).

Catches "an axis change WITHOUT a new I-NN wave": Loop State claims `T9 restart axes used: N`, but the model
has built < N extra `## WAVE-*` waves (+ explicit N/A axes). A counting invariant, not a marker-in-prose.

Rule (feedback_hook_must_prove_firing): the test MUST prove FIRING on the real shape of the
failure, not just the absence of false positives. Fixtures 1-2 = the verbatim shape of the real failures (3 axes / 0 waves).
Monkeypatches freshest_active_ledger; the model is placed NEXT TO it, as in production. Exit 1 on any FAIL.
Run: py -3 -X utf8 scripts/_methodology/axes_waves_gate_replay.py
"""
import importlib.util
import os
import shutil
import sys
import tempfile

_HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks", "hunt_completeness_gate.py")
spec = importlib.util.spec_from_file_location("gate", _HOOK)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

_cur = {"dir": None}
g.freshest_active_ledger = lambda sid: (
    (os.path.join(_cur["dir"], "hypotheses.md"), _cur["dir"]) if _cur["dir"] else (None, None)
)

# NOTE: Cyrillic table headers / fixture cells below are kept as-is — they mirror the real ledger/model format that the hook parses.
TABLE = (
    "| ID | Формула | check | Класс | Источник | component | pred | Статус | file:line | tests | crowd-heat | lib |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
)


def row(i):
    return "| I-%02d | f%d | что проверить | state | docs | vault | ENFORCED | ENFORCED | a.sol:%d | 2 | cold | |\n" % (i, i, 10 + i)


def base_wave(n=3):
    return "## Invariants\n" + TABLE + "".join(row(i) for i in range(1, n + 1))


# Bullet-form model shape (2026-07-31): model as BULLETS, enforcement in `pred:` (the Статус/Status column is empty, the real
# status is in prose). Before the fix _status_of=empty -> statused=0<3 -> the gate silently switched off. We prove it is un-blinded.
def bullet_wave(n=3):
    lines = ["## Invariants (I-NN) — `pred:` set BEFORE code (bullet form)\n"]
    for i in range(1, n + 1):
        lines.append("- **I-%02d** [state] инвариант %d. check: гард на всех путях? pred: ENFORCED.\n" % (i, i))  # fixture text kept (Russian prose)
    return "".join(lines)


def extra_wave(idx, axis, n=2, base=100):
    return "\n## WAVE-%d — %s\n" % (idx, axis) + TABLE + "".join(row(base + j) for j in range(1, n + 1))


def na_line(axis, reason="вне модели / trusted"):  # reason default kept (fixture): "outside the model / trusted"
    return "\n%s: N/A — %s\n" % (axis, reason)


def ledger(axes_line):
    return "# t — Hypotheses Registry\n\n## Loop State\n- **Iteration #:** 7\n" + axes_line + "\n"


AXES3 = "- **T9 restart axes used:** 3 (1 treasury→H-07, 2 position→H-08 KILLED, 3 oracle IN-FLIGHT)"
AXES3_STRUCK = "- ~~**T9 restart axes used:** 3~~ → superseded"
AXES_TEMPLATE = "- **T9 restart axes used:** {0-3+, list axes; after 3 dry → surfaced status + continue}"
WAVE_NEXT = "- **T9 restart axes used:** 3 (a,b,c)\n- **WAVE-NEXT:** cross-subsystem isolation"

results = []


def run(name, ledger_txt, model_txt, expect):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_txt)
    if model_txt is not None:
        with open(os.path.join(d, "system_model.md"), "w", encoding="utf-8") as f:
            f.write(model_txt)
    _cur["dir"] = d
    try:
        got = bool(g.active_axes_without_waves("sid"))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok = "PASS" if got == expect else "FAIL"
    print("  [%s] %s: fired=%s expect=%s" % (ok, name, got, expect))
    results.append(ok == "PASS")


print("── active_axes_without_waves (OBS-10: axis change without a new wave)")

# 1-2: VERBATIM shape of the real failures — 3 axes claimed, 0 extra waves -> FIRE.
run("real-failure shape: 3 axes / 0 extra waves -> fire", ledger(AXES3), base_wave(3), True)
run("3 axes / base wave of 12 I-NN, but 0 WAVE-N -> fire", ledger(AXES3), base_wave(12), True)

# 3: healthy multi-wave — 3 axes, 3 extra waves -> silent.
run("3 axes / 3 extra waves WAVE-2..4 -> silent",
    ledger(AXES3),
    base_wave(3) + extra_wave(2, "cross-function", base=100) + extra_wave(3, "temporal", base=200) + extra_wave(4, "isolation", base=300),
    False)

# 4: mixed — 1 wave + 2 N/A axes = 3 covered -> silent.
run("3 axes / 1 extra wave + 2 N/A axes -> silent",
    ledger(AXES3),
    base_wave(3) + extra_wave(2, "cross-function", base=100) + na_line("order-dependent") + na_line("economic-sequence"),
    False)

# 5: partial coverage — 3 axes, 1 wave, 0 N/A = 1 < 3 -> FIRE (the residual class is caught too).
run("3 axes / 1 extra wave / 0 N/A (2 axes bare) -> fire",
    ledger(AXES3),
    base_wave(3) + extra_wave(2, "cross-function", base=100),
    True)

# 6: no axes claimed (only a {…} template) -> silent (template_sentinel hygiene).
run("template {0-3+…} -> n=0 -> silent", ledger(AXES_TEMPLATE), base_wave(3), False)

# 7: the claim is struck through (~~…~~ superseded) -> n=0 -> silent.
run("struck-through ~~3~~ -> n=0 -> silent", ledger(AXES3_STRUCK), base_wave(3), False)

# 8: the agent is building the next wave (WAVE-NEXT: in the ledger) -> silent (in progress).
run("3 axes + WAVE-NEXT: -> building -> silent", ledger("") .replace("\n\n## Loop State", "\n\n## Loop State\n" + WAVE_NEXT), base_wave(3), False)

# 9: thin model (<3 statused I-NN) -> silent (model_incomplete owns it).
run("3 axes / thin model 2 I-NN -> silent", ledger(AXES3), base_wave(2), False)

# 10: MODEL: N/A — gates lifted -> silent.
run("MODEL: N/A -> silent",
    ledger(AXES3) + "- **MODEL: N/A — single contract <300 LOC**\n", base_wave(3), False)

# 11-12: bullet / pred-only form — un-blind. Before the fix statused=0 -> silent (bug); after -> same as table.
run("BULLET pred-only: 3 axes / 0 extra waves -> fire (un-blind)", ledger(AXES3), bullet_wave(3), True)
run("BULLET pred-only: 3 axes / thin 2 I-NN -> silent", ledger(AXES3), bullet_wave(2), False)

# 13-14: namespaced wave IDs (TB-I*/W3-I*), 2026-08-04. Before the fix `_I_ROW_RE` did not see them ->
# wave_i_counts=0 -> false-fire on a correct multi-wave. After — they are counted as invariants.
NS_TABLE = "| ID | Формула | check | Класс | component | pred | Статус |\n|---|---|---|---|---|---|---|\n"
def ns_wave(idx, prefix, n=3):
    body = "".join("| %s-I%d | ф | что | state | comp | ENFORCED | ENFORCED |\n" % (prefix, j) for j in range(1, n + 1))
    return "\n## WAVE-%d — namespaced ось\n" % idx + NS_TABLE + body  # "namespaced ось" = "namespaced axis" (fixture heading, kept)
run("namespaced TB-I*/W3-I* waves: 1 axis / 2 NS waves -> silent (recognized)",
    ledger("- **T9 restart axes used:** 1 (oracle)"),
    base_wave(3) + ns_wave(2, "TB") + ns_wave(3, "W3"), False)
run("namespaced: 3 axes / only 1 NS wave -> fire (partial coverage is caught)",
    ledger(AXES3), base_wave(3) + ns_wave(2, "TB"), True)

# 15: markdown-bold status `**ENFORCED-PARTIAL**` counts as mature (a bold pred used to drop out of maturity).
BOLD_TABLE = ("| ID | Ф | check | Класс | Ист | component | pred | Статус | file | tests | ch | lib |\n"
              "|---|---|---|---|---|---|---|---|---|---|---|---|\n")
bold_model = "## Invariants\n" + BOLD_TABLE + "".join(
    "| I-%02d | f | что | state | docs | c | **ENFORCED-PARTIAL** | **ENFORCED-PARTIAL** | a:%d | 2 | cold | |\n" % (i, i)
    for i in range(1, 4))
# 3 bold invariants + 3 axes / 0 waves -> FIRE (meaning the model is NOT deemed thin — bold is recognized as mature).
run("markdown-bold pred is mature (not a thin model) -> fire", ledger(AXES3), bold_model, True)

print("\n%d/%d PASS" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
