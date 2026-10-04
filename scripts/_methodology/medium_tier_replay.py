# -*- coding: utf-8 -*-
"""Replay for active_medium_tier_undriven (2026-08-18).

Defect: the hunter structurally banked + ran T6, BUT the whole bank is Low/info (0 Medium) — the Medium tier as a
DEDICATED DRIVE was not run (griefing/temp-freeze/gas-DoS/positive-slippage/permanent-freeze), only banked
incidental Low during a Crit/High hunt. Reviewer: "Medium is hunted ON EQUAL footing, and you keep forgetting it".

Measure-first: severity in HYPOTHESES is not machine-tagged, "Medium" in prose = boilerplate → unreliable.
The severity column of the ## Banked Findings table is parsed RELIABLY. Fire ⇔ T6-DONE AND >=1 banked-row AND all
Low/info AND no Medium row/marker.

feedback_hook_must_prove_firing: we prove FIRING (the all-Low+T6→fire class) AND protections (Medium
row / marker / T6-not-done / empty-bank / HUNT-EXIT / MANUAL). feedback_detector_state_not_phrase:
the key is the severity column + T6-done state, not the word form "Medium" from boilerplate. Isolated slug."""
import importlib.util, os, sys, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SESSIONS = os.path.join(ROOT, "sessions")
HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks", "hunt_completeness_gate.py")
spec = importlib.util.spec_from_file_location("gate", HOOK)
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)

SLUG = "_mttest"
SID = "mt-sid-1"
results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))

HEAD = "# _mttest — Registry\n## Loop State\n- HUNT-MODE: AUTONOMOUS\n- Iteration: 8\n## Active\n- **I-01** a\n- **I-02** b\n- **I-03** c\n"
T6_DONE = "- **Banked T6-pass (A5):** DONE (N=2) — no chainable pair\n"
TBL_LOW = ("## Banked Findings\n| # | Severity | H-NN | Что | output | input | tier | found_by | ст |\n"  # Cyrillic column names kept (fixture mirrors real ledger format)
           "|---|---|---|---|---|---|---|---|---|\n"
           "| B-01 | Low/de-minimis | H-LZ | dust | leak | precond | none | self | confirmed |\n"
           "| B-02 | Low/defense-in-depth | D-06 | binding | state | precond | none | self | confirmed |\n")
TBL_MED = TBL_LOW.replace("| B-02 | Low/defense-in-depth", "| B-02 | Medium")
TBL_EMPTY = ("## Banked Findings\n| # | Severity | H-NN | Что | output | input | tier | found_by | ст |\n"  # Cyrillic column names kept (fixture mirrors real ledger format)
             "|---|---|---|---|---|---|---|---|---|\n| | | | | | | | | |\n")


def write_ledger(body):
    d = os.path.join(SESSIONS, SLUG)
    if os.path.exists(d):
        shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(body)
    import time as _t
    with open(os.path.join(d, ".hunt_active"), "w", encoding="utf-8") as f:
        f.write("%d\n%s" % (int(_t.time()), SID))


def fires():
    return g.active_medium_tier_undriven(SID) is not None


try:
    # 1) FIRE: T6-done + the whole bank is Low + no marker → the Medium tier was not driven.
    write_ledger(HEAD + T6_DONE + TBL_LOW)
    check("1 FIRE: T6-done + all-Low bank + no marker → fire (0x)", fires(),
          "sevs=%s t6=%s" % (g._banked_row_severities(HEAD + T6_DONE + TBL_LOW), g._banked_t6_done_count(HEAD + T6_DONE + TBL_LOW)))

    # 2) SILENT: >=1 Medium row in the bank → the tier was touched.
    write_ledger(HEAD + T6_DONE + TBL_MED)
    check("2 SILENT: banked contains a Medium row → no fire", not fires())

    # 3) SILENT: explicit Medium-tier marker (drove, refuted) → satisfiable.
    write_ledger(HEAD + T6_DONE + TBL_LOW + "\nMedium-tier: driven — refuted griefing/gas-DoS (guard PriceValidator.sol:33)\n")
    check("3 SILENT: Medium-tier marker (driven/refuted) → no fire", not fires())

    # 4) SILENT: T6 NOT done (the bank is still accumulating → composite leads) → too early.
    write_ledger(HEAD + TBL_LOW)
    check("4 SILENT: T6 not DONE → no fire (composite leads)", not fires(),
          "t6=%s" % g._banked_t6_done_count(HEAD + TBL_LOW))

    # 5) SILENT: empty bank (prose/atom gates) → not here.
    write_ledger(HEAD + T6_DONE + TBL_EMPTY)
    check("5 SILENT: empty bank → no fire", not fires(),
          "rows=%d" % g._banked_rows(HEAD + T6_DONE + TBL_EMPTY))

    # 6) OFF: HUNT-EXIT.
    write_ledger(HEAD + T6_DONE + TBL_LOW + "\nHUNT-EXIT: T4-CONFIRMED High\n")
    check("6 OFF: HUNT-EXIT → no fire", not fires())

    # 7) OFF: MANUAL.
    write_ledger(HEAD + "- **HUNT-MODE: MANUAL**\n" + T6_DONE + TBL_LOW)
    check("7 OFF: MANUAL → no fire", not fires())

    # 8) helper: severity extraction (header/blank row do not count).
    check("8 _banked_row_severities: 2 Low rows, header filtered out",
          g._banked_row_severities(TBL_LOW) == ["Low/de-minimis", "Low/defense-in-depth"],
          "got=%s" % g._banked_row_severities(TBL_LOW))

    # 9) anti-FP: the boilerplate "Medium — full DRIVE" is NOT counted as a marker.
    check("9 anti-FP: boilerplate 'Medium — DRIVE' is not a marker",
          not g._has_medium_tier_marker("Medium — полноценный DRIVE (глубже сразу). Medium/Low banked."),  # Russian input text kept (logic fixture)
          "")

finally:
    d = os.path.join(SESSIONS, SLUG)
    if os.path.exists(d):
        shutil.rmtree(d, ignore_errors=True)

print("=== MEDIUM-TIER-UNDRIVEN REPLAY (bank all Low + T6 done → drive Medium as a DRIVE) ===\n")
ok = 0
for name, passed, detail in results:
    print(("  [PASS] " if passed else "  [FAIL] ") + name + (("  — " + detail) if detail and not passed else ""))
    ok += 1 if passed else 0
print("\n%d/%d checks green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
