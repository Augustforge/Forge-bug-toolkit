#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression for the active_banked_composite_unchecked gate (A5, Wave 1 2026-08-08).

banked findings = PROVEN building blocks (more reliable than refuted hypotheses). Before batch-submit —
a mandatory T6 pass over the bank: output->input pairs (Low x Low -> precondition, Low+High -> escalate,
Medium x Medium -> Crit). The gate holds the banked submission while >=2 banked findings AND there is no T6-pass mark.
A satisfiable soft nudge: do the pass / mark "no pairs".

Rule (feedback_hook_must_prove_firing): the test MUST prove FIRING on the real shape of the
failure. FIRE = (a)/(g); rolling back the gate breaks (a); rolling back the `>=2` threshold -> (c) starts to FIRE; rolling back
DONE-detection -> (b)/(h) start to FIRE. Monkeypatches freshest_active_ledger. Exit 1 on any FAIL.
Run: py -3 -X utf8 scripts/_methodology/banked_composite_gate_replay.py
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

# NOTE: Cyrillic table headers / placeholders below are kept as-is — they mirror the real ledger format the hook parses.
# ("Что (1 строка)" = "What (1 line)", "что нужно" = "what is needed", "Статус" = "Status")
HDR = ("| # | Severity | H-NN | Что (1 строка) | output (leak/state/precond) | input (что нужно) "
       "| Payout-tier | found_by | Статус |\n"
       "|---|---|---|---|---|---|---|---|---|")
EMPTY_ROW = "| | | | | | | | | |"
ROW1 = ("| 1 | Medium | H-03 | reflected XSS via token symbol | attacker-controlled DOM string "
        "| admin session | tier2 | scout-P5 | confirmed |")
ROW2 = ("| 2 | Low | H-07 | address disclosure in API | victim EOA leaked | target address "
        "| tier4 | deephunt-J5 | confirmed |")
ROW3 = ("| 3 | Low | H-09 | verbose error schema leak | field names | mass-assign candidate "
        "| tier4 | error-oracle | confirmed |")

T6_PLACEHOLDER = "- **Banked T6-pass:** {none yet}"
T6_DONE_NONE = "- **Banked T6-pass:** DONE — no chainable pairs"
T6_DONE_CHAIN = "- **Banked T6-pass:** DONE — chain: banked-2.output→banked-1.input (Low+Med → High)"


def ledger(rows, t6_line=T6_PLACEHOLDER, extra=""):
    tbl = HDR + "\n" + ("\n".join(rows) if rows else EMPTY_ROW)
    return (
        "# t — Hypotheses Registry\n\n## Loop State\n- **Iteration #:** 7\n"
        + (extra + "\n" if extra else "")
        + "\n## Banked Findings (confirmed Medium/Low — ожидают batch-submit)\n\n"  # "ожидают" = "awaiting" (heading text kept: mirrors real template)
        + tbl + "\n\n"
        + (t6_line + "\n" if t6_line is not None else "")
        + "\n## Active Hypotheses\n\n"
    )


# Untouched template: only an empty placeholder row + T6-pass `{none yet}` -> 0 banked -> silent.
UNTOUCHED = ledger([], T6_PLACEHOLDER)
# Legacy: no Banked Findings section at all (a session from before A5) -> 0 rows -> silent.
LEGACY = "# t — Hypotheses Registry\n\n## Loop State\n- **Iteration #:** 3\n\n## Active Hypotheses\n\n"

results = []


def run(name, ledger_txt, expect):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_txt)
    _cur["dir"] = d
    try:
        got = bool(g.active_banked_composite_unchecked("sid"))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok = "PASS" if got == expect else "FAIL"
    print("  [%s] %s: fired=%s expect=%s" % (ok, name, got, expect))
    results.append(ok == "PASS")


print("── active_banked_composite_unchecked (A5: banked x T6 composite)")

# (a) VERBATIM failure shape: >=2 banked + T6-pass not done (placeholder) -> FIRE.
run("(a) 2 banked / T6-pass {none yet} → fire", ledger([ROW1, ROW2]), True)
# (b) >=2 banked + T6-pass DONE (no pairs) -> silent.
run("(b) 2 banked / T6-pass DONE-no-pairs → silent", ledger([ROW1, ROW2], T6_DONE_NONE), False)
# (c) <2 banked (1 row) + placeholder -> silent (threshold not reached).
run("(c) 1 banked / placeholder → silent (<2)", ledger([ROW1]), False)
# (d) untouched template (0 real rows) -> silent (template-safe).
run("(d) untouched (0 banked rows) → silent (template-safe)", UNTOUCHED, False)
# (e) MANUAL -> silent.
run("(e) 2 banked / MANUAL → silent", ledger([ROW1, ROW2], extra="- **HUNT-MODE: MANUAL**"), False)
# (f) HUNT-EXIT High -> silent.
run("(f) 2 banked / HUNT-EXIT High → silent",
    ledger([ROW1, ROW2], extra="- **HUNT-EXIT: T4-CONFIRMED High**"), False)
# (g) 3 banked + NO T6-pass field at all -> FIRE (no mark = pass not done).
run("(g) 3 banked / no T6-pass field → fire", ledger([ROW1, ROW2, ROW3], t6_line=None), True)
# (h) >=2 banked + T6-pass DONE-chain -> silent.
run("(h) 2 banked / T6-pass DONE-chain → silent", ledger([ROW1, ROW3], T6_DONE_CHAIN), False)
# (i) legacy with no Banked section at all -> silent (anti-FP).
run("(i) legacy without a Banked section → silent (anti-FP)", LEGACY, False)

# ── SUD-MED-2 (live hunt 2026-08-12): re-arm on bank GROWTH. The T6 pass stuck on any DONE ->
# the bank grew (2->4->6), new output->input pairs were not checked. Operator: "T6 banked should be done
# several times, the count grows". `DONE (N=k)` = checked when there were k banked; banked>k -> re-arm.
T6_DONE_N2 = "- **Banked T6-pass:** DONE (N=2) — no chainable pairs"
T6_DONE_N3 = "- **Banked T6-pass:** DONE (N=3) — chain: banked-2.output→banked-1.input"
# (j) 2 banked + DONE(N=2) -> silent (checked exactly on the current bank).
run("(j/MED-2) 2 banked / DONE(N=2) → silent [covered]", ledger([ROW1, ROW2], T6_DONE_N2), False)
# (k) the bank GREW to 3, while the T6 pass was at N=2 -> FIRE (1 new banked not in the T6 pass — re-arm).
run("(k/MED-2) 3 banked / DONE(N=2) → fire [bank grew, re-arm]", ledger([ROW1, ROW2, ROW3], T6_DONE_N2), True)
# (l) 3 banked + DONE(N=3) -> silent (the pass caught up with the bank).
run("(l/MED-2) 3 banked / DONE(N=3) → silent [pass caught up]", ledger([ROW1, ROW2, ROW3], T6_DONE_N3), False)
# (m) 2 banked + DONE(N=5) -> silent (N>=banked, edge — the pass covered with margin).
run("(m/MED-2) 2 banked / DONE(N=5) → silent [N>=banked]", ledger([ROW1, ROW2], T6_DONE_N2.replace("N=2", "N=5")), False)
# (n/backward-compat) an old DONE WITHOUT N with a grown bank -> silent (we don't break the legacy DONE form).
run("(n/MED-2 compat) 3 banked / DONE without N → silent [legacy DONE lifts]",
    ledger([ROW1, ROW2, ROW3], T6_DONE_NONE), False)

# ── FEAT-L (live hunt 2026-08-12): active_value_at_risk_unquantified — $-at-risk before submitting banked.
print("── active_value_at_risk_unquantified (FEAT-L: $-at-risk quantification before submission)")


def _runL(name, ledger_txt, expect):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_txt)
    _cur["dir"] = d
    try:
        got = bool(g.active_value_at_risk_unquantified("sid"))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok = "PASS" if got == expect else "FAIL"
    print("  [%s] %s: fired=%s expect=%s" % (ok, name, got, expect))
    results.append(ok == "PASS")


VAR_FIELD = "- **Value-at-risk:** $2.4M (fork: deep/fork_profit_delta.json)"
VAR_PLACEHOLDER = "- **Value-at-risk:** {оцени на форке}"  # placeholder kept (fixture): "{estimate on a fork}"
# (L1) >=1 banked, value-at-risk not set -> FIRE.
_runL("(L1) 2 banked / no value-at-risk → fire", ledger([ROW1, ROW2]), True)
# (L2) >=1 banked + Value-at-risk with a number+fork -> silent.
_runL("(L2) 2 banked / Value-at-risk $2.4M (fork) → silent", ledger([ROW1, ROW2], extra=VAR_FIELD), False)
# (L3) 0 banked -> silent (nothing to quantify).
_runL("(L3) 0 banked → silent", ledger([]), False)
# (L4) banked + value-at-risk placeholder -> FIRE (not quantified).
_runL("(L4) 2 banked / Value-at-risk {placeholder} → fire", ledger([ROW1, ROW2], extra=VAR_PLACEHOLDER), True)
# (L5) MANUAL -> silent.
_runL("(L5) 2 banked / MANUAL → silent", ledger([ROW1, ROW2], extra="- **HUNT-MODE: MANUAL**"), False)
# (L6) HUNT-EXIT -> silent (the submit path closes it).
_runL("(L6) 2 banked / HUNT-EXIT → silent", ledger([ROW1, ROW2], extra="- **HUNT-EXIT: T4-CONFIRMED High**"), False)
# (L7 Z2 judge MED): IN-PLACE fill of a template field with a PARENTHETICAL `(FEAT-L — …):** $2M` -> silent (parenthetical-tolerant).
# (the parenthetical "приоритет" = "priority" is kept: fixture mirroring the real template label)
_runL("(L7/Z2) in-place `**Value-at-risk (FEAT-L — x):** $2.4M (fork)` → silent",
      ledger([ROW1, ROW2], extra="- **Value-at-risk (FEAT-L — приоритет):** $2.4M (fork: deep/fpd.json)"), False)

# ── FEAT-K (live hunt 2026-08-12): active_banked_staleness_unchecked — re-check freshness before submission.
print("── active_banked_staleness_unchecked (FEAT-K: banked-staleness re-check)")


def _runK(name, ledger_txt, expect):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_txt)
    _cur["dir"] = d
    try:
        got = bool(g.active_banked_staleness_unchecked("sid"))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ok = "PASS" if got == expect else "FAIL"
    print("  [%s] %s: fired=%s expect=%s" % (ok, name, got, expect))
    results.append(ok == "PASS")


# (K1) 2 banked + iter 12 (>=10) + no freshness -> FIRE.
_runK("(K1) 2 banked / iter 12 / no freshness → fire", ledger([ROW1, ROW2]).replace("Iteration #:** 7", "Iteration #:** 12"), True)
# (K2) 2 banked + iter 12 + freshness check -> silent.
_runK("(K2) 2 banked / iter 12 / banked-freshness entry → silent",
      ledger([ROW1, ROW2], extra="- banked-freshness: H-03 — still-live").replace("Iteration #:** 7", "Iteration #:** 12"), False)
# (K3) 2 banked + iter 5 (<10) -> silent (fresh).
_runK("(K3) 2 banked / iter 5 (<10) → silent (fresh)", ledger([ROW1, ROW2]).replace("Iteration #:** 7", "Iteration #:** 5"), False)
# (K4) 0 banked + iter 12 -> silent.
_runK("(K4) 0 banked / iter 12 → silent", ledger([]).replace("Iteration #:** 7", "Iteration #:** 12"), False)
# (K5) MANUAL -> silent.
_runK("(K5) 2 banked / iter 12 / MANUAL → silent",
      ledger([ROW1, ROW2], extra="- **HUNT-MODE: MANUAL**").replace("Iteration #:** 7", "Iteration #:** 12"), False)

print("\n%d/%d PASS" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
