#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression for the active_axis_queue_empty gate (Hunt Strategy Layer, 2026-08-08).

The operator's pain "I forget where to go next" = there is no forward queue of axes. The gate holds the exit when >=1 axis is
CLOSED (`T9 restart axes used: N>=1`) and the `Axis-Queue` field is empty/`none`/stubs — AND I am actually
BETWEEN axes (0 live Active H-NN, `Depth-Lead: none yet`). On an extensive axis (mid-drive: a live H-NN
OR Depth-Lead is driving a thread) the gate is SILENT — it does not force an axis change prematurely (operator 2026-08-08).

Rule (feedback_hook_must_prove_firing): the test MUST prove FIRING on the real shape of the
failure, not just the absence of false positives. FIRE cases (a)/(j) = the failure shape; rolling back the gate breaks (a),
rolling back the mid-drive off-switch -> (h)/(i) start to FIRE, rolling back anti-gaming (the valid `src:` requirement)
-> (j) goes silent. Monkeypatches freshest_active_ledger; the ledger is put in a temp folder, as in production.
Exit 1 on any FAIL.
Run: py -3 -X utf8 scripts/_methodology/axis_queue_gate_replay.py
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

# ── Ledger building blocks ───────────────────────────────────────────────────
AXES2 = "- **T9 restart axes used:** 2 (treasury→H-07, oracle→H-08 KILLED)"
AXES0 = "- **T9 restart axes used:** 0"
AXES_TMPL = "- **T9 restart axes used:** {0-3+, list axes; after 3 dry → surfaced status + continue on axis 4}"

# Axis-Queue field values
Q_NONE = "none"
Q_FILLED = ("\n  1) liquidation-accounting — src:D-03 · rank:high"
            "\n  2) governance-timelock — src:T6-pair · rank:med")
Q_STUB = "\n  1) TBD\n  2) —\n  3) later"       # stubs without `src:` (anti-gaming)
# Q_TMPL: Cyrillic template placeholder kept as-is (mirrors the real template; recognized via the `{...}` sentinel).
# Meaning: "{RICH ranked queue of FUTURE axes (many, not 1-2). Each item on its OWN line: ... `none` while empty.}"
Q_TMPL = ("{БОГАТАЯ ranked-очередь БУДУЩИХ осей (много, не 1-2). Каждый элемент — ОТДЕЛЬНОЙ строкой: "
          "`N) <ось> — src:<D-NN|T14-gap|score-4-file|T6-pair|prior-pattern|T9-frame> · rank:<...>`. "
          "`none` пока пусто.}")

LIVE_H = "### H-09: attacker drains vault via stale oracle\n- **State:** C-PoC-attempting\n- **Confidence:** high\n"
DEAD_H = "### H-08 [KILLED]: reentrancy on withdraw\n- **Killed by:** nonReentrant guard oracle.sol:44\n"

DL_NONE = "none yet"
DL_ACTIVE = "H-09 — 4/5 (call→state→external→hook)"


def ledger(axes_line, queue_val, depth_lead=DL_NONE, active_block="", extra=""):
    """Builds a ledger with Loop State + Active Hypotheses. The Axis-Queue field comes before Depth-Lead (order does not
    matter in the real template — the gate looks for each field independently)."""
    return (
        "# t — Hypotheses Registry\n\n## Loop State\n"
        "- **Iteration #:** 7\n"
        "- **Last SELECT-branch:** e\n"
        "- **Axis-Queue (forward, ranked; голова = Depth-Lead):** " + queue_val + "\n"  # "голова" = "head" (label kept: mirrors real template)
        "- **Depth-Lead:** " + depth_lead + "\n"
        + axes_line + "\n"
        + (extra + "\n" if extra else "")
        + "\n## Active Hypotheses\n" + active_block + "\n"
    )


# Untouched template: the real trio lines + T9 from the template (all with `{...}` placeholders) -> t9=0 -> silent.
# (depth_lead placeholder is Cyrillic, kept: "{strongest thread ... `none yet` until a thread is chosen}")
UNTOUCHED = ledger(AXES_TMPL, Q_TMPL, depth_lead="{сильнейшая нить … `none yet` пока нить не выбрана}")

# Legacy ledger: no Axis-Queue field at all (a session from before the Hunt Strategy Layer) -> anti-FP, silent.
LEGACY = ("# t — Hypotheses Registry\n\n## Loop State\n- **Iteration #:** 7\n"
          "- **Depth-Lead:** none yet\n" + AXES2 + "\n\n## Active Hypotheses\n\n")

results = []


def run(name, ledger_txt, expect):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_txt)
    _cur["dir"] = d
    try:
        got = bool(g.active_axis_queue_empty("sid"))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok = "PASS" if got == expect else "FAIL"
    print("  [%s] %s: fired=%s expect=%s" % (ok, name, got, expect))
    results.append(ok == "PASS")


print("── active_axis_queue_empty (Hunt Strategy Layer: forward queue of axes)")

# (a) VERBATIM failure shape: axis closed, queue empty (none), I am BETWEEN axes -> FIRE.
run("(a) 2 axes closed / Axis-Queue none / between axes (0 H, DL none) -> fire",
    ledger(AXES2, Q_NONE), True)

# (b) queue is non-empty (2 axes with a valid src) -> silent.
run("(b) 2 axes / Axis-Queue filled (src:D-03/T6-pair) -> silent",
    ledger(AXES2, Q_FILLED), False)

# (c) first pass: 0 axes closed, queue empty -> silent (the queue is legitimately none).
run("(c) 0 axes closed / Axis-Queue none -> silent (first pass)",
    ledger(AXES0, Q_NONE), False)

# (d) HUNT-MODE: MANUAL -> silent (emergency manual mode).
run("(d) 2 axes / queue empty / MANUAL -> silent",
    ledger(AXES2, Q_NONE, extra="- **HUNT-MODE: MANUAL**"), False)

# (e) HUNT-EXIT: T4-CONFIRMED High -> silent (hunt is done).
run("(e) 2 axes / queue empty / HUNT-EXIT High -> silent",
    ledger(AXES2, Q_NONE, extra="- **HUNT-EXIT: T4-CONFIRMED High**"), False)

# (f) untouched template (T9 `{...}` -> t9=0, queue `{...}`) -> silent (template-safe).
run("(f) untouched template (T9 {…}, Axis-Queue {…}) -> silent (template-safe)", UNTOUCHED, False)

# (h) extensive axis: axis closed, queue empty, but a LIVE Active H-NN -> silent (mid-drive).
run("(h) 2 axes / queue empty / live Active H-NN -> silent (mid-drive)",
    ledger(AXES2, Q_NONE, active_block=LIVE_H), False)

# (i) extensive axis: axis closed, queue empty, Depth-Lead is driving a thread -> silent (mid-drive).
run("(i) 2 axes / queue empty / Depth-Lead != none -> silent (mid-drive)",
    ledger(AXES2, Q_NONE, depth_lead=DL_ACTIVE), False)

# (j) anti-gaming: axis closed, queue = stubs (`1) TBD` without src:), between axes -> FIRE.
run("(j) 2 axes / queue = TBD stubs (no src:) / between axes -> fire (anti-gaming)",
    ledger(AXES2, Q_STUB), True)

# (k) legacy ledger with no Axis-Queue field at all -> silent (anti-FP, old session).
run("(k) legacy ledger without an Axis-Queue field -> silent (anti-FP)", LEGACY, False)

# (h2) killed H-NN (not live) with an empty queue between axes -> FIRE (a dead H does not count as mid-drive).
run("(h2) 2 axes / queue none / only KILLED H-NN (not live) -> fire",
    ledger(AXES2, Q_NONE, active_block=DEAD_H), True)

print("\n%d/%d PASS" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
