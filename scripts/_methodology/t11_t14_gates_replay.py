#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression for the gates active_t11_undecided (OBS-11) and active_attention_gap_skipped (OBS-12).

Both are a fix for "built, but not gated → skipped" (two past audits: the T11 detector said
APPLICABLE, but over 4 hunts it was never run; T14 — 0 artifacts). Decision sentinel: the gate forces a conscious
decision (run + record a verdict / N/A), not the expensive step itself.

Rule (feedback_hook_must_prove_firing): the test MUST prove FIRING on the shape of the skip, not
only the absence of false positives. Exit 1 on any FAIL.
Run: py -3 -X utf8 scripts/_methodology/t11_t14_gates_replay.py
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

# Header cells "Класс" (class) / "Статус" (status) are literal Russian ledger column keys parsed by the gate: KEEP.
TABLE = ("| ID | F | check | Класс | Ист | component | pred | Статус | file:line | tests | crowd-heat | lib |\n"
         "|---|---|---|---|---|---|---|---|---|---|---|---|\n")
def _row(i, st="ENFORCED"):
    return "| I-%02d | f%d | what | state | docs | vault | %s | %s | a.sol:%d | 2 | cold | |\n" % (i, i, st, st, 10 + i)

# Header cells (place / source / overlaps / taken) are literal Russian ledger column keys: KEEP.
ATTN_HDR = "\n## Attention Gaps\n| Место | Источник | Пересекается | Взято |\n|---|---|---|---|\n"


def model(statused=3, attn=None, div=None):
    m = "## Invariants\n" + TABLE + "".join(_row(i) for i in range(1, statused + 1))
    if attn == "empty":
        m += ATTN_HDR
    elif attn == "filled":
        m += ATTN_HDR + "| Vault.sol:40 | audit-hole (T14-A) | D-01 | yes |\n"
    elif attn == "na":
        m += "\n## Attention Gaps\nAttention Gaps: N/A — no audits, shallow git\n"
    # Divergences header cells (where / status / rank / resolution) are literal Russian ledger keys: KEEP.
    if div == "open":
        m += "\n## Divergences\n| ID | I-NN | Где | Статус | Ранг | Резолюция |\n|---|---|---|---|---|---|\n| D-01 | I-03 | a.sol:9 | ABSENT | high |  |\n"  # Russian header cells ("Where" / "Status" / "Rank" / "Resolution") are parser input: kept
    elif div == "resolved":
        m += "\n## Divergences\n| ID | I-NN | Где | Статус | Ранг | Резолюция |\n|---|---|---|---|---|---|\n| D-01 | I-03 | a.sol:9 | ABSENT | high | → H-03 |\n"  # Russian header cells ("Where" / "Status" / "Rank" / "Resolution") are parser input: kept
    return m


def ledger(extra=""):
    return "# t\n**Impacts in Scope:** N/A — no formal impacts list\n## Loop State\n- **Iteration #:** 8\n- **Exit:** T4 High/Crit only.\n" + extra


# 2026-07-31 shape: the model in BULLETS, enforcement in `pred:`, status in prose. Before the fix
# _status_of=empty → statused=0<3 → t11/attention silently turned off. Optional attention section in bullets.
def bullet_model(statused=3, attn=None):
    m = "## Invariants (I-NN) — `pred:` set BEFORE code (bullet form)\n"
    for i in range(1, statused + 1):
        m += "- **I-%02d** [state] invariant %d. check: guard on all paths? pred: ENFORCED.\n" % (i, i)
    if attn == "prose":                       # T14 done in BULLETS (as in that case) — filled, not N/A
        m += "\n## Attention Gaps (T14)\n- Crowd heat: the audit is concentrated on the core, ports are colder.\n- Author-rush: redelegation was added AFTER the audit → unaudited.\n"
    elif attn == "empty":
        m += "\n## Attention Gaps (T14)\n"
    return m


results = []


def run(name, fn, ledger_txt, model_txt, expect):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_txt)
    if model_txt is not None:
        with open(os.path.join(d, "system_model.md"), "w", encoding="utf-8") as f:
            f.write(model_txt)
    _cur["dir"] = d
    try:
        got = bool(fn("sid"))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok = "PASS" if got == expect else "FAIL"
    print("  [%s] %s: fired=%s expect=%s" % (ok, name, got, expect))
    results.append(ok == "PASS")


print("── active_t11_undecided (OBS-11: T11 applicable, but no verdict recorded)")
run("mature model / no T11-VERDICT → fire", g.active_t11_undecided, ledger(), model(3), True)
run("T11-VERDICT: SKIP — no build → silent", g.active_t11_undecided, ledger("- **T11-VERDICT:** SKIP — web2, no build\n"), model(3), False)
run("T11-VERDICT: APPLICABLE → silent", g.active_t11_undecided, ledger("- **T11-VERDICT:** APPLICABLE (Trident)\n"), model(3), False)
run("placeholder {APPLICABLE|SKIP} → fire (a brace is not a verdict)", g.active_t11_undecided, ledger("- **T11-VERDICT:** {APPLICABLE|MAYBE|SKIP|N/A}\n"), model(3), True)
run("thin model (2 statused) → silent", g.active_t11_undecided, ledger(), model(2), False)
run("MODEL: N/A → silent", g.active_t11_undecided, ledger("- **MODEL: N/A — single contract**\n"), model(3), False)

print("── active_attention_gap_skipped (OBS-12: T14 not run before concluding \"nothing here\")")
run("mature / 0 D-NN / attn empty → fire", g.active_attention_gap_skipped, ledger(), model(3, attn="empty", div="resolved"), True)
run("attn filled with a row → silent", g.active_attention_gap_skipped, ledger(), model(3, attn="filled", div="resolved"), False)
run("Attention Gaps: N/A → silent", g.active_attention_gap_skipped, ledger(), model(3, attn="na", div="resolved"), False)
run("open D-NN + attn empty → silent (drive the D-NN)", g.active_attention_gap_skipped, ledger(), model(3, attn="empty", div="open"), False)
run("no Attention Gaps section at all / 0 D-NN → fire", g.active_attention_gap_skipped, ledger(), model(3, div="resolved"), True)
run("building a wave (WAVE-NEXT) → silent", g.active_attention_gap_skipped, ledger("- **WAVE-NEXT:** cross-function\n"), model(3, attn="empty", div="resolved"), False)
run("thin model → silent", g.active_attention_gap_skipped, ledger(), model(2, attn="empty"), False)

print("── BULLET/pred-only form (2026-07-31) — un-blind the maturity cluster")
run("BULLET: mature / no T11-VERDICT → fire (un-blind)", g.active_t11_undecided, ledger(), bullet_model(3), True)
run("BULLET: mature + T11-VERDICT: SKIP → silent", g.active_t11_undecided, ledger("- **T11-VERDICT:** SKIP — web2\n"), bullet_model(3), False)
run("BULLET: thin 2 I-NN → silent", g.active_t11_undecided, ledger(), bullet_model(2), False)
run("BULLET: attn filled with bullets → silent (not an FP)", g.active_attention_gap_skipped, ledger(), bullet_model(3, attn="prose"), False)
run("BULLET: attn empty / 0 D-NN → fire", g.active_attention_gap_skipped, ledger(), bullet_model(3, attn="empty"), True)

print("\n%d/%d PASS" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
