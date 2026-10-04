#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression for the AXIS QUEUE discipline (originprotocol-audit 2026-08-13).

Two gates in `hunt_completeness_gate.py`:
  • active_axis_reranked_midqueue     — "the main thing is to go in queue order": a new axis is raised ABOVE the tails of
    the live queue and taken out of order (`re-ranked ABOVE stale queue-tails`) = a jump. Order = law:
    write OPEN, finish the head, class-exhaustive rebuild on exhaustion.
  • active_axis_closed_critical_only  — "why only critical?": an axis is closed on "no unprivileged
    Critical" without an explicit High/Medium assessment. Loop-exit = High/Critical (High on equal footing), Medium = DRIVE+bank.

Rule (feedback_hook_must_prove_firing): the test PROVES firing on the real shape of the miss + the off-switch.
Monkeypatches freshest_active_ledger. Exit 1 on any FAIL.
Run: py -3 -X utf8 scripts/_methodology/axis_order_gate_replay.py
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

results = []


def run(name, fn_name, ledger_txt, expect):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_txt)
    _cur["dir"] = d
    try:
        got = bool(getattr(g, fn_name)("sid"))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok = got == expect
    print("  [%s] %s: fired=%s expect=%s" % ("PASS" if ok else "FAIL", name, got, expect))
    results.append(ok)


HDR = "# t — Registry\n\n## Loop State\n- **Iteration #:** 5\n"
TAIL = "\n## Active Hypotheses\n\n"
EXIT = "\nHUNT-EXIT: T4-CONFIRMED High\n"
MANUAL = "\n- **HUNT-MODE: MANUAL**\n"

# ══════════════════════════════════════════════════════════════════════════════
print("── active_axis_reranked_midqueue (order = law; do not jump out of the queue)")

# (a) the real originprotocol shape: re-ranked ABOVE stale queue-tails → fire
REORDER = ("- **Axis-Queue HEAD (ACTIVE, popped T9):** AMO economic manip — src:T9-frame · "
           "⚠ re-ranked ABOVE stale queue-tails (higher in-scope EV).\n")
run("(a) re-ranked ABOVE stale queue-tails → fire", "active_axis_reranked_midqueue",
    HDR + REORDER + TAIL, True)
# (b) popped T9 ... above → fire
run("(b) popped T9 <axis> above queue-tails → fire", "active_axis_reranked_midqueue",
    HDR + "- HEAD popped T9 AMO-ось above queue-tails\n" + TAIL, True)  # Russian fixture text kept (input data)
# (c) the Russian form "raised above the tails" → fire
run("(c) raised above the queue tails (Russian phrasing) → fire", "active_axis_reranked_midqueue",
    HDR + "- новую ось поднял выше хвостов очереди — EV сильнее\n" + TAIL, True)  # Russian fixture text kept (input data)
# (d) placeholder template {re-rank above queue} → silent
run("(d) placeholder {re-rank above queue} → silent", "active_axis_reranked_midqueue",
    HDR + "- {re-ranked above queue-tails — пример anti-gaming}\n" + TAIL, False)  # Russian fixture text kept (input data)
# (e) prose rule in a blockquote → silent
run("(e) > prose rule about re-rank above → silent", "active_axis_reranked_midqueue",
    HDR + "> НЕ переставляй ось re-ranked above queue-tails мимо порядка\n" + TAIL, False)  # Russian fixture text kept (input data)
# (f) clean ledger (no reorder) → silent
run("(f) no reorder marker → silent", "active_axis_reranked_midqueue",
    HDR + "- **Current pick:** H-03 из очереди по rank\n" + TAIL, False)  # Russian fixture text kept (input data)
# (g) MANUAL → silent
run("(g) MANUAL → silent", "active_axis_reranked_midqueue", HDR + REORDER + MANUAL + TAIL, False)
# (h) HUNT-EXIT → silent
run("(h) HUNT-EXIT → silent", "active_axis_reranked_midqueue", HDR + REORDER + EXIT + TAIL, False)

# ══════════════════════════════════════════════════════════════════════════════
print("\n── active_axis_closed_critical_only (loop-exit = High/Critical, not only Critical)")

# (i) "no unprivileged Critical" without High/Med nearby → fire
run("(i) 'no unprivileged Critical' without High/Med → fire", "active_axis_closed_critical_only",
    HDR + "- **AMO axis:** cold-scout вернул: no unprivileged Critical — closed.\n" + TAIL, True)  # Russian fixture text kept (input data)
# (j) 'no critical' BUT Medium banked nearby → silent (severity assessed)
run("(j) 'no Critical' + Medium banked nearby → silent", "active_axis_closed_critical_only",
    HDR + "- **AMO axis:** no unprivileged Critical.\n- BB-14 Medium banked → Banked Findings.\n" + TAIL, False)
# (k) full frame: no High/Critical + Medium assessed → silent
run("(k) 'no High/Critical' + 'Medium: none' → silent (full severity frame)", "active_axis_closed_critical_only",
    HDR + "- ось: no unprivileged high/critical; Medium: none found; Low: dust harvested.\n" + TAIL, False)  # Russian fixture text kept (input data)
# (l) 'nothing exploitable' without a severity assessment → fire
run("(l) 'nothing exploitable' without High/Med → fire", "active_axis_closed_critical_only",
    HDR + "- **axis closed:** nothing exploitable here.\n" + TAIL, True)
# (m) placeholder → silent
run("(m) placeholder {no critical} → silent", "active_axis_closed_critical_only",
    HDR + "- {no critical — пример вердикта}\n" + TAIL, False)  # Russian fixture text kept (input data)
# (n) 'no critical' + 'severity:' nearby → silent (severity explicitly set)
run("(n) 'no Critical' + 'Severity: High' nearby → silent", "active_axis_closed_critical_only",
    HDR + "- axis: no unprivileged critical path.\n- **Severity:** High if Morpho manip.\n" + TAIL, False)
# (o) MANUAL → silent
run("(o) MANUAL → silent", "active_axis_closed_critical_only",
    HDR + "- no unprivileged Critical.\n" + MANUAL + TAIL, False)
# (p) HUNT-EXIT → silent
run("(p) HUNT-EXIT → silent", "active_axis_closed_critical_only",
    HDR + "- no unprivileged Critical.\n" + EXIT + TAIL, False)

print("\n%d/%d PASS" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
