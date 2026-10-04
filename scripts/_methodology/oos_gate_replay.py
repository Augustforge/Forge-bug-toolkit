#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression for Out-of-Scope enforcement (money-critical — a report was closed as OOS, $0).

Two gates in `hunt_completeness_gate.py`:
  * active_ledger_missing_oos          — intake: holds the exit while the `OOS-TODO` sentinel is present
    (Out-of-Scope disqualifiers were not extracted from /scope/). Mirror of active_ledger_missing_impacts.
  * active_submit_without_oos_check    — submit-time (success-exit path): HUNT-EXIT is declared, OOS was
    really captured, but there is no `OOS-CHECK:` line → the finding was not checked against Out-of-Scope.
    Off: OOS N/A / no OOS field.

Rule (feedback_hook_must_prove_firing): the test PROVES firing on the real shape of the miss + an off-switch.
Monkeypatches freshest_active_ledger. Exit 1 on any FAIL.
Run: py -3 -X utf8 scripts/_methodology/oos_gate_replay.py
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


HDR = "# t — Registry\n\n**Target:** x\n**Assets in Scope:** contract A\n"
OOS_REAL = "**Out-of-Scope (disqualifiers):** centralization risks, admin-key, known-issues\n"
OOS_NA = "**Out-of-Scope (disqualifiers):** N/A — no formal OOS list\n"
# Sentinel text after OOS-TODO is Russian ("extract /scope/ ..."): kept verbatim, may be matched by the gate.
OOS_TODO = "**Out-of-Scope (disqualifiers):** {OOS-TODO — вычитать /scope/ …}\n"
EXIT = "\nHUNT-EXIT: T4-CONFIRMED High\n"
TAIL = "\n## Active Hypotheses\n\n"

# ══════════════════════════════════════════════════════════════════════════════
print("── active_ledger_missing_oos (intake: the OOS-TODO sentinel holds the exit)")

run("(a) OOS-TODO present → fire", "active_ledger_missing_oos", HDR + OOS_TODO + TAIL, True)
run("(b) OOS filled with real disqualifiers → silent", "active_ledger_missing_oos",
    HDR + OOS_REAL + TAIL, False)
run("(c) OOS = N/A (no-program) → silent", "active_ledger_missing_oos", HDR + OOS_NA + TAIL, False)
run("(d) legacy ledger with no OOS field at all → silent (anti-FP on old ones)", "active_ledger_missing_oos",
    HDR + TAIL, False)

# ══════════════════════════════════════════════════════════════════════════════
print("\n── active_submit_without_oos_check (submit: HUNT-EXIT without OOS-CHECK with a real OOS)")

# (e) HUNT-EXIT + real OOS captured, but NO OOS-CHECK → fire (finding not checked).
run("(e) HUNT-EXIT + real OOS + no OOS-CHECK → fire", "active_submit_without_oos_check",
    HDR + OOS_REAL + EXIT + TAIL, True)

# (f) HUNT-EXIT + real OOS + OOS-CHECK: PASS → silent (checked).
run("(f) HUNT-EXIT + real OOS + OOS-CHECK PASS → silent", "active_submit_without_oos_check",
    HDR + OOS_REAL + EXIT + "\nOOS-CHECK: share-inflation vs out-of-scope → PASS\n" + TAIL, False)

# (g) HUNT-EXIT + OOS = N/A → silent (nothing to check against, no-program).
run("(g) HUNT-EXIT + OOS N/A → silent (nothing to check)", "active_submit_without_oos_check",
    HDR + OOS_NA + EXIT + TAIL, False)

# (h) HUNT-EXIT + NO OOS field (legacy/e2e) → silent (no real OOS to check against).
run("(h) HUNT-EXIT + no OOS field (legacy) → silent (don't break old ones)", "active_submit_without_oos_check",
    HDR + EXIT + TAIL, False)

# (i) real OOS + no OOS-CHECK, but WITHOUT HUNT-EXIT → SILENT.
#     NOTE: CONTRACT TIGHTENED (judge-2, final acceptance): the function used to return truthy
#     mid-hunt too, and safety rested ONLY on the call-site inside `if ledger_success_exit(...)` —
#     fragile against a refactor / an over-eager sweep of all `active_*` (OOS is filled by the intake gate
#     at the very start → the condition holds in the middle of a hunt). Now there is an internal
#     `_has_valid_exit` guard, like the sibling `active_banked_without_oos_check`. main() behavior did
#     not change (same path there); the robustness of the function did. See (J2-guard) below.
run("(i) real OOS + no OOS-CHECK, WITHOUT HUNT-EXIT → silent (internal exit-guard, symmetric with sibling)",
    "active_submit_without_oos_check", HDR + OOS_REAL + TAIL, False)

# (j) HUNT-EXIT + real OOS + no OOS-CHECK + MANUAL → silent (emergency manual mode).
run("(j) HUNT-EXIT + real OOS + MANUAL → silent", "active_submit_without_oos_check",
    HDR + OOS_REAL + EXIT + "\nHUNT-MODE: MANUAL\n" + TAIL, False)

# (k) OOS-CHECK DISQUALIFIED (the finding fell into OOS) → silent (checked, gate lifted; do NOT submit —
#     but that is the instance's decision, the gate only requires the PRESENCE of a check).
run("(k) OOS-CHECK DISQUALIFIED → silent (check performed)", "active_submit_without_oos_check",
    HDR + OOS_REAL + EXIT + "\nOOS-CHECK: finding vs out-of-scope → DISQUALIFIED: centralization\n" + TAIL, False)

# ══════════════════════════════════════════════════════════════════════════════
print("\n── active_banked_without_oos_check (a banked Medium/Low is submitted without an OOS check — the incident hole)")

# Table header cells "Что" (what) / "Статус" (status) are literal Russian ledger column keys: KEEP.
BANKED = ("\n## Banked Findings\n| Severity | H-NN | Что | output | input | tier | found_by | Статус |\n"
          "|---|---|---|---|---|---|---|---|\n"
          "| Medium | H-05 | oracle conf-strip | over-valuation | — | $3K | scan | confirmed |\n")
CHECK_PASS = "\nOOS-CHECK: H-05 vs out-of-scope → PASS\n"

# (l) banked row + real OOS + no OOS-CHECK → fire (the main hole: a Medium leaves without a check).
run("(l) banked + real OOS + no OOS-CHECK → fire", "active_banked_without_oos_check",
    HDR + OOS_REAL + BANKED + TAIL, True)

# (m) banked + real OOS + OOS-CHECK PASS → silent (checked).
run("(m) banked + real OOS + OOS-CHECK PASS → silent", "active_banked_without_oos_check",
    HDR + OOS_REAL + BANKED + CHECK_PASS + TAIL, False)

# (n) banked + OOS = N/A → silent (no-program, nothing to check against).
run("(n) banked + OOS N/A → silent", "active_banked_without_oos_check",
    HDR + OOS_NA + BANKED + TAIL, False)

# (o) no banked rows + real OOS → silent (nothing to submit).
run("(o) no banked + real OOS → silent", "active_banked_without_oos_check",
    HDR + OOS_REAL + TAIL, False)

# (p) banked + real OOS + HUNT-EXIT → silent (the submit gate covers the High/Crit path).
run("(p) banked + real OOS + HUNT-EXIT → silent (submit gate covers it)", "active_banked_without_oos_check",
    HDR + OOS_REAL + BANKED + EXIT + TAIL, False)

# (q) banked + real OOS + MANUAL → silent.
run("(q) banked + real OOS + MANUAL → silent", "active_banked_without_oos_check",
    HDR + OOS_REAL + BANKED + "\nHUNT-MODE: MANUAL\n" + TAIL, False)

# ══════════════════════════════════════════════════════════════════════════════
print("\n── verdict-strictness: OOS-CHECK requires a real verdict (not a bare `OOS-CHECK:`)")

# (r) submit: bare `OOS-CHECK: TODO` (no verdict) → the submit gate STILL fires (presence-only is closed).
run("(r) HUNT-EXIT + real OOS + `OOS-CHECK: TODO` (no verdict) → fire", "active_submit_without_oos_check",
    HDR + OOS_REAL + EXIT + "\nOOS-CHECK: TODO not checked yet\n" + TAIL, True)

# (s) banked: bare `OOS-CHECK: pending` → the banked gate still fires.
run("(s) banked + real OOS + `OOS-CHECK: pending` (no verdict) → fire", "active_banked_without_oos_check",
    HDR + OOS_REAL + BANKED + "\nOOS-CHECK: pending review\n" + TAIL, True)

# (t) a real verdict `→ DISQUALIFIED` lifts it (check performed, the finding is dropped by the instance).
run("(t) banked + `OOS-CHECK: → DISQUALIFIED` → silent (verdict present)", "active_banked_without_oos_check",
    HDR + OOS_REAL + BANKED + "\nOOS-CHECK: H-05 vs out-of-scope → DISQUALIFIED: centralization\n" + TAIL, False)

# ══════════════════════════════════════════════════════════════════════════════
print("\n── red-team fixes (D1 success-path / D4 N/A-substring / D7 header-scope)")

# (D1) intake fires even with HUNT-EXIT (a fast exit must not release with an unextracted OOS;
#      the success-path now calls intake). Unit: active_ledger_missing_oos on OOS-TODO + HUNT-EXIT → fire.
run("(D1) OOS-TODO + HUNT-EXIT → intake fire (success-path does not release with an unextracted OOS)",
    "active_ledger_missing_oos", HDR + OOS_TODO + EXIT + TAIL, True)

# (D4) a real OOS list that MENTIONS 'N/A' as a substring → _oos_captured_real=True → submit fire.
run("(D4) HUNT-EXIT + OOS='centralization; testnet N/A; admin-key' + no OOS-CHECK → fire (N/A is not a substring)",
    "active_submit_without_oos_check",
    HDR + "**Out-of-Scope (disqualifiers):** centralization risks; testnet N/A; admin-key\n" + EXIT + TAIL, True)

# (D4-control) a pure '^N/A' at the start of the value → still N/A → silent.
run("(D4-ctrl) OOS='N/A — no formal OOS' → silent (anchor ^N/A)", "active_submit_without_oos_check",
    HDR + OOS_NA + EXIT + TAIL, False)

# (D7) the OOS-TODO sentinel in the hypothesis BODY (after Loop State, not in the header) with OOS filled → intake
#      silent (header = frontmatter up to `## Loop State`; the hypothesis body after it is excluded).
run("(D7) OOS filled + 'OOS-TODO' in the hypothesis body (after Loop State) → intake silent (header-scope)",
    "active_ledger_missing_oos",
    HDR + OOS_REAL + "\n## Loop State\n- **Iteration #:** 3\n"
    + "\n## Active Hypotheses\n### H-01: discussing the OOS-TODO gate mechanism itself\n- State: A\n", False)

# (D7-control) OOS-TODO in the header → intake fire.
run("(D7-ctrl) OOS-TODO in the header → intake fire", "active_ledger_missing_oos", HDR + OOS_TODO + TAIL, True)

# ── Judge-2 (final acceptance): internal exit-guard = SYMMETRY with active_banked_without_oos_check.
# A submit-level gate; mid-hunt (no HUNT-EXIT) it must not fire BY ITSELF even if OOS is filled —
# this used to rest ONLY on the call-site inside the success branch (fragile against a refactor / over-eager sweep).
run("(J2-guard) OOS filled, NO HUNT-EXIT → submit-OOS silent (mid-hunt is not our business)",
    "active_submit_without_oos_check",
    HDR + "**Out-of-Scope (disqualifiers):** centralization risks; admin-key\n"
    + "\n## Loop State\n- **Iteration #:** 5\n" + TAIL, False)
# control: the same ledger + HUNT-EXIT → fires (submit moment, no OOS-CHECK).
run("(J2-guard-ctrl) same + HUNT-EXIT → fire (submit moment)",
    "active_submit_without_oos_check",
    HDR + "**Out-of-Scope (disqualifiers):** centralization risks; admin-key\n" + EXIT + TAIL, True)

# ══════════════════════════════════════════════════════════════════════════════
# Asset-reconciliation — the ASSETS-RECON sentinel holds the exit
# until N total assets are reconciled with M extracted (M<N/N>12 → Playwright itself). Mirror of missing_impacts.
print("\n── active_ledger_assets_unreconciled (intake: the ASSETS-RECON sentinel holds the exit)")
# Russian text in the two fixtures below ("reconcile N total with M extracted" / "extracted") kept verbatim: may be matched by the gate.
ASSETS_TODO = "**Assets in Scope:** {ASSETS-RECON — сверь N total с M извлечёнными; M<N/N>12 → Playwright сам}\n"
ASSETS_DONE = "**Assets in Scope:** 52 total / 52 извлечено · playwright-full\n"
ASSETS_NA = "**Assets in Scope:** N/A — repo/no-program\n"
# HDR carries its own `**Assets in Scope:** contract A` — for these cases the header is built without it.
HDR2 = "# t — Registry\n\n**Target:** x\n"
run("(u) ASSETS-RECON present → fire", "active_ledger_assets_unreconciled", HDR2 + ASSETS_TODO + TAIL, True)
run("(v) reconciled (playwright-full) → silent", "active_ledger_assets_unreconciled", HDR2 + ASSETS_DONE + TAIL, False)
run("(w) N/A (repo/no-program) → silent", "active_ledger_assets_unreconciled", HDR2 + ASSETS_NA + TAIL, False)
run("(x) legacy with no Assets field at all → silent (anti-FP on old ones)", "active_ledger_assets_unreconciled",
    HDR2 + TAIL, False)
# (y) ASSETS-RECON in the hypothesis BODY (after Loop State) with a reconciled header → silent (header-scope, red-team D7).
run("(y) Assets reconciled + 'ASSETS-RECON' in the body (after Loop State) → silent (header-scope)",
    "active_ledger_assets_unreconciled",
    HDR2 + ASSETS_DONE + "\n## Loop State\n- **Iteration #:** 3\n"
    + "\n## Active Hypotheses\n### H-01: discussing the ASSETS-RECON gate mechanism itself\n- State: A\n", False)
# (z) ASSETS-RECON + HUNT-EXIT → intake fire (success-path does not release with unreconciled assets).
run("(z) ASSETS-RECON + HUNT-EXIT → fire (a fast exit does not release unreconciled assets)",
    "active_ledger_assets_unreconciled", HDR2 + ASSETS_TODO + EXIT + TAIL, True)

print("\n%d/%d PASS" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
