#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression test for Worklist Driver Stage 2 -- `next_atom` active dictation (DEFAULT branch).

Plan: methodology/plans/worklist_driver_plan.md §1 Layer-2 / §3 Stage 2 / §8 (G-advisory/G-weak/G-patchdiff).
`next_atom(sid) -> (directive, advisory[])` replaces the static LOOP_CONTINUE_REASON in the DEFAULT branch:
  - directive = PREFIX (DRIVE/HANDOFF/QUEUE_EMPTY, names the registry head) + the FULL LOOP_CONTINUE_REASON
    (the exit contract is NEVER lost -- axis-1), OR a pure LOOP_CONTINUE (fallback: no registry /
    first pass / MODEL:N/A / MANUAL/OFF/EXIT / flag off -> zero blast radius).
  - advisory[] = soft riders (G-weak calibration-note) -- the 2nd channel of Layer-2 (§8 G-advisory).
  - head: _registry_head with tie-break (rank, patch-diff boost, id) -- §8 G-patchdiff.

Rule (feedback_hook_must_prove_firing): the test PROVES active dictation (the directive names the head)
AND fallback silence (byte-for-byte LOOP_CONTINUE where there is no registry). Monkeypatches freshest_active_ledger.
Exit 1 on any FAIL.
Run: py -3 -X utf8 scripts/_methodology/worklist_driver_stage2_replay.py
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

REG_HDR = "## Atom Registry\n\n| id | type | title | src | rank | status | closes |\n|---|---|---|---|---|---|---|\n"


def reg(rows):
    body = "".join("| %s | %s | %s | %s | %s | %s | %s |\n" % r for r in rows)
    return REG_HDR + body + "\n"


def ledger(registry_block, pick="AX-04", it=7, head_extra=""):
    ls = ("# t — Hypotheses Registry\n\n## Loop State\n"
          "- **Iteration #:** " + str(it) + "\n"
          "- **Current pick:** " + pick + "\n")
    return ls + head_extra + "\n" + registry_block + "\n## Active Hypotheses\n\n"


results = []
_LC = g.LOOP_CONTINUE_REASON


def run(name, ledger_txt, expect_kind, expect_advisory=None, flag=True, weak=None):
    """expect_kind: 'DRIVE'|'HANDOFF'|'QUEUE_EMPTY'|'FALLBACK'. expect_advisory: substring of advisory[0]
    (or None = advisory is empty). weak: set for monkeypatching _weak_classes (None = real behavior)."""
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_txt)
    _cur["dir"] = d
    old_flag = g.WORKLIST_DRIVER_ENABLED
    g.WORKLIST_DRIVER_ENABLED = flag
    old_weak = getattr(g, "_weak_classes")
    if weak is not None:
        g._weak_classes = lambda _c={}: set(weak)
    try:
        directive, advisory = g.next_atom("sid")
    finally:
        g.WORKLIST_DRIVER_ENABLED = old_flag
        g._weak_classes = old_weak
        shutil.rmtree(d, ignore_errors=True)

    # the directive must always carry the exit contract (LOOP_CONTINUE) -- axis-1 (the exit contract is never lost).
    has_contract = _LC in directive
    if expect_kind == "FALLBACK":
        kind_ok = (directive == _LC)                       # BYTE-FOR-BYTE pure fallback
    elif expect_kind == "DRIVE":
        # KEEP: Russian string matches the hook output (compared in code)
        kind_ok = directive.startswith("⚙ WORKLIST-DRIVER (Этап 2): машинный реестр") and has_contract
    elif expect_kind == "HANDOFF":
        # KEEP: Russian string matches the hook output (compared in code)
        kind_ok = ("голова реестра сменилась" in directive) and has_contract
    elif expect_kind == "QUEUE_EMPTY":
        # KEEP: Russian string matches the hook output (compared in code)
        kind_ok = ("НЕТ ни одной" in directive) and has_contract
    else:
        kind_ok = False

    if expect_advisory is None:
        adv_ok = (advisory == [])
    else:
        adv_ok = (len(advisory) == 1 and expect_advisory in advisory[0])

    ok = kind_ok and adv_ok
    print("  [%s] %s: kind=%s adv=%s" % ("PASS" if ok else "FAIL", name,
          "ok" if kind_ok else "WRONG(%r…)" % directive[:60], "ok" if adv_ok else "WRONG(%r)" % advisory))
    results.append(ok)


def run_head(name, ledger_txt, expect_head_id):
    """Proves WHICH id is named as the head (G-patchdiff tie-break)."""
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_txt)
    _cur["dir"] = d
    old_flag = g.WORKLIST_DRIVER_ENABLED
    g.WORKLIST_DRIVER_ENABLED = True
    try:
        directive, _ = g.next_atom("sid")
    finally:
        g.WORKLIST_DRIVER_ENABLED = old_flag
        shutil.rmtree(d, ignore_errors=True)
    ok = ("`%s`" % expect_head_id) in directive
    print("  [%s] %s: head=%s" % ("PASS" if ok else "FAIL", name,
          expect_head_id if ok else "NOT-NAMED(%r…)" % directive[:80]))
    results.append(ok)


def run_names(name, ledger_txt, expect_kind, names, not_names):
    """Proves kind + that the `names` atom is named and `not_names` is NOT named (judge-A Defect-1 regression)."""
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger_txt)
    _cur["dir"] = d
    old_flag = g.WORKLIST_DRIVER_ENABLED
    g.WORKLIST_DRIVER_ENABLED = True
    try:
        directive, _ = g.next_atom("sid")
    finally:
        g.WORKLIST_DRIVER_ENABLED = old_flag
        shutil.rmtree(d, ignore_errors=True)
    # KEEP: Russian strings below match the hook output (compared / split in code)
    is_drive = directive.startswith("⚙ WORKLIST-DRIVER (Этап 2): машинный реестр")
    is_handoff = "голова реестра сменилась" in directive
    kind_ok = is_drive if expect_kind == "DRIVE" else (is_handoff if expect_kind == "HANDOFF" else False)
    named_ok = ("`%s`" % names) in directive
    notnamed_ok = ("`%s`" % not_names) not in directive.split("Ниже — полный контракт")[0].split("Контракт петли ниже")[0]
    ok = kind_ok and named_ok and notnamed_ok
    print("  [%s] %s: kind=%s named=%s not-named=%s" % ("PASS" if ok else "FAIL", name,
          "ok" if kind_ok else "WRONG", "ok" if named_ok else "MISS", "ok" if notnamed_ok else "LEAK"))
    results.append(ok)


# ══════════════════════════════════════════════════════════════════════════════
print("── next_atom: active head dictation (healthy registry)")

# DRIVE: head is ACTIVE and is max-rank -> "drive IT, do not re-pick".
run("(a) head ACTIVE = max-rank → DRIVE + names head",
    ledger(reg([("AX-04", "axis", "band-regression", "D-05", "35", "ACTIVE", "-"),
                ("AX-05", "axis", "governance", "T6-pair", "28", "OPEN", "-")]), pick="AX-04"),
    "DRIVE")

# HANDOFF: 0 ACTIVE, there is an OPEN -> "next head = X, mark it ACTIVE" (axis-switch moment).
run("(b) 0 ACTIVE, OPEN head → HANDOFF (axis switch)",
    ledger(reg([("AX-07", "axis", "reentrancy-hook", "D-09", "40", "OPEN", "-"),
                ("AX-08", "axis", "dust", "code-read", "18", "OPEN", "-")]), pick="AX-07"),
    "HANDOFF")

# QUEUE_EMPTY: all CLOSED/PARKED -> regeneration in 3 modes.
run("(c) all CLOSED/PARKED → QUEUE_EMPTY (regeneration)",
    ledger(reg([("AX-04", "axis", "band", "D-05", "35", "CLOSED", "H-07"),
                ("AX-05", "axis", "gov", "T6", "28", "PARKED", "-")]), pick="—"),
    "QUEUE_EMPTY")

print("\n── next_atom: fallback (zero blast radius — byte-for-byte LOOP_CONTINUE)")

# C1: no registry section at all -> pure LOOP_CONTINUE (legacy/web hunts).
run("(d) no `## Atom Registry` (C1) → FALLBACK",
    "# t\n\n## Loop State\n- **Iteration #:** 7\n- **Current pick:** H-07\n\n## Active Hypotheses\n\n",
    "FALLBACK")

# first pass: section exists but only a placeholder (0 valid atoms) -> FALLBACK.
# KEEP: "{имя}" / "{число}" are placeholder fixtures (template placeholders, Russian in the source template)
run("(e) first pass (placeholder registry, 0 valid) → FALLBACK",
    ledger(reg([("{AX-01}", "{axis}", "{имя}", "{D-NN}", "{число}", "{OPEN}", "{-}")]), pick="H-07"),
    "FALLBACK")

# MODEL: N/A + registry -> DRIVE (registry honored: next_atom does NOT force adoption, it only dictates the head if
# a registry exists; consistent with the pick-gate, which also has no N/A off-switch). Pure N/A without a registry
# = C1 fallback (covered by (d)). Opt-in to the registry on a small contract -> the driver works.
run("(f) MODEL: N/A + registry → DRIVE (registry honored, not silenced by N/A)",
    ledger(reg([("AX-04", "axis", "band", "D-05", "35", "ACTIVE", "-")]), pick="AX-04",
           # KEEP: Russian fixture text ("the only thin contract, T10 not applicable")
           head_extra="\nMODEL: N/A — единственный тонкий контракт, T10 неприменим\n"),
    "DRIVE")

# MANUAL / OFF / HUNT-EXIT -> FALLBACK (consistent with the pick-gate).
run("(g) HUNT-MODE: MANUAL → FALLBACK",
    ledger(reg([("AX-04", "axis", "band", "D-05", "35", "ACTIVE", "-")]), pick="AX-04",
           head_extra="\nHUNT-MODE: MANUAL\n"), "FALLBACK")
run("(h) HUNT-MODE: OFF → FALLBACK",
    ledger(reg([("AX-04", "axis", "band", "D-05", "35", "ACTIVE", "-")]), pick="AX-04",
           head_extra="\nHUNT-MODE: OFF\n"), "FALLBACK")
run("(i) HUNT-EXIT T4-CONFIRMED High → FALLBACK",
    ledger(reg([("AX-04", "axis", "band", "D-05", "35", "ACTIVE", "-")]), pick="AX-04",
           head_extra="\nHUNT-EXIT: T4-CONFIRMED High\n"), "FALLBACK")

# flag off -> pure LOOP_CONTINUE (trivial rollback).
run("(j) WORKLIST_DRIVER_ENABLED=False → FALLBACK (byte-for-byte)",
    ledger(reg([("AX-04", "axis", "band", "D-05", "35", "ACTIVE", "-")]), pick="AX-04"),
    "FALLBACK", flag=False)

print("\n── G-weak (§8): advisory rider on the head's weak class (monkeypatched calibration)")

# weak class matches the head's title -> advisory is non-empty (does NOT change the head — only a skepticism note).
run("(k) weak class in head title → advisory note",
    ledger(reg([("H-07", "hypothesis", "oracle-conf-strip", "D-05", "35", "ACTIVE", "-")]), pick="H-07"),
    "DRIVE", expect_advisory="accuracy<30%", weak={"oracle"})

# weak class does NOT match -> advisory is empty (no false rider).
run("(l) weak class does not match head → advisory empty",
    ledger(reg([("H-07", "hypothesis", "reentrancy", "D-05", "35", "ACTIVE", "-")]), pick="H-07"),
    "DRIVE", expect_advisory=None, weak={"oracle"})

# real data: _weak_classes is empty (n<5 per class) -> advisory is empty (armed trigger, currently a no-op).
run("(m) real calibration (n<5) → weak empty → advisory empty",
    ledger(reg([("H-07", "hypothesis", "oracle-conf-strip", "D-05", "35", "ACTIVE", "-")]), pick="H-07"),
    "DRIVE", expect_advisory=None, weak=None)

print("\n── G-patchdiff (§8): tie-break (rank, patch-diff, id) on EQUAL rank")

# equal rank 30, AX-05 src=patch-diff -> head is AX-05 (patch-diff first), NOT AX-04 (id order).
run_head("(n) tie rank=30: patch-diff src → head is the patch-diff atom",
         ledger(reg([("AX-04", "axis", "band", "D-05", "30", "OPEN", "-"),
                     ("AX-05", "axis", "gov", "patch-diff", "30", "OPEN", "-")]), pick="AX-05"),
         "AX-05")

# NOT a tie: AX-04 rank is higher (40) even though AX-05 is patch-diff -> head is AX-04 (rank dominates, boost is irrelevant).
run_head("(o) not a tie: rank dominates the patch-diff boost",
         ledger(reg([("AX-04", "axis", "band", "D-05", "40", "OPEN", "-"),
                     ("AX-05", "axis", "gov", "patch-diff", "30", "OPEN", "-")]), pick="AX-04"),
         "AX-04")

# tie WITHOUT patch-diff -> deterministic by id (AX-05 > AX-04 lexicographically).
run_head("(p) tie without patch-diff → tie-break by id (max)",
         ledger(reg([("AX-04", "axis", "band", "D-05", "30", "OPEN", "-"),
                     ("AX-05", "axis", "gov", "code-read", "30", "OPEN", "-")]), pick="AX-05"),
         "AX-05")

print("\n── judge-A Defect-1: co-maximal ACTIVE on EQUAL rank → DRIVE (not a false HANDOFF)")

# (q) ACTIVE AX-01 shares max-rank 35 with OPEN AX-05, loses the id tie-break -> there WAS a false HANDOFF
#     (Stage-2 told it to leave a legit ACTIVE while the pick-gate was silent). Now DRIVE, names AX-01 itself, not AX-05.
run_names("(q) tie rank=35: ACTIVE AX-01 vs OPEN AX-05 → DRIVE names AX-01 (not HANDOFF/AX-05)",
          ledger(reg([("AX-01", "axis", "band", "D-05", "35", "ACTIVE", "-"),
                      ("AX-05", "axis", "gov", "code-read", "35", "OPEN", "-")]), pick="AX-01"),
          "DRIVE", names="AX-01", not_names="AX-05")

# (q2) same edge + patch-diff on the OPEN neighbor (the boost amplified the tie-break edge) -> still DRIVE on the ACTIVE.
run_names("(q2) tie rank=35 + patch-diff OPEN neighbor → DRIVE on ACTIVE (boost does not force handoff)",
          ledger(reg([("AX-01", "axis", "band", "D-05", "35", "ACTIVE", "-"),
                      ("AX-02", "axis", "gov", "patch-diff", "35", "OPEN", "-")]), pick="AX-01"),
          "DRIVE", names="AX-01", not_names="AX-02")

print("\n── judge-C D2: token-subset match (not substring)")

# (r) weak `auth` is NOT a subset of the tokens of `author-check` -> advisory empty (substring `w in hay` failed).
run("(r) weak `auth` ⊄ `author-check` (token-subset) → advisory empty",
    ledger(reg([("H-07", "hypothesis", "author-check", "D-05", "35", "ACTIVE", "-")]), pick="H-07"),
    "DRIVE", expect_advisory=None, weak={"auth"})

# (r2) multi-token weak `guard-asymmetry` ⊆ `guard-asymmetry-check` -> advisory (subset catches multi-token).
run("(r2) multi-token `guard-asymmetry` ⊆ head → advisory",
    ledger(reg([("H-07", "hypothesis", "guard-asymmetry-check", "D-05", "35", "ACTIVE", "-")]), pick="H-07"),
    "DRIVE", expect_advisory="accuracy<30%", weak={"guard-asymmetry"})

print("\n── axis-6 durability: next_atom is stable across compact (re-read from file)")

# (s) compact-sim: registry in a FILE -> next_atom twice (emulating a re-read after compact) -> same directive + head.
_d = tempfile.mkdtemp()
with open(os.path.join(_d, "hypotheses.md"), "w", encoding="utf-8") as _f:
    _f.write(ledger(reg([("AX-04", "axis", "band-regression", "D-05", "35", "ACTIVE", "-"),
                         ("AX-05", "axis", "gov", "T6", "28", "OPEN", "-")]), pick="AX-04"))
_cur["dir"] = _d
_old = g.WORKLIST_DRIVER_ENABLED
g.WORKLIST_DRIVER_ENABLED = True
try:
    _d1, _a1 = g.next_atom("sid")
    _d2, _a2 = g.next_atom("sid")            # second "Stop" after compact — re-reads the same file
finally:
    g.WORKLIST_DRIVER_ENABLED = _old
    shutil.rmtree(_d, ignore_errors=True)
_stable = (_d1 == _d2) and (_a1 == _a2) and ("`AX-04`" in _d1) and _d1.startswith("⚙ WORKLIST-DRIVER")
print("  [%s] (s) next_atom durable across compact: stable=%s head=AX-04=%s"
      % ("PASS" if _stable else "FAIL", _d1 == _d2, "`AX-04`" in _d1))
results.append(_stable)

print("\n── Stage 3 riders: synthesis cadence (every 5) / identity-Sherlock (every 8) by Iteration #")


def run_cadence(name, it, expect_synth, expect_ident):
    """Checks EXACTLY the composition of advisory[] at the given iteration (riders, NOT a replacement of the directive)."""
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger(reg([("AX-04", "axis", "band", "code-read", "35", "ACTIVE", "-")]),
                       pick="AX-04", it=it))
    _cur["dir"] = d
    old = g.WORKLIST_DRIVER_ENABLED
    g.WORKLIST_DRIVER_ENABLED = True
    try:
        directive, advisory = g.next_atom("sid")
    finally:
        g.WORKLIST_DRIVER_ENABLED = old
        shutil.rmtree(d, ignore_errors=True)
    joined = "\n".join(advisory)
    got_s = "CROSS-THREAD SYNTHESIS" in joined
    got_i = "РЕЖИМ ШЕРЛОКА" in joined  # KEEP: Russian string matches the hook output ("SHERLOCK MODE")
    # the directive is NOT replaced by riders — the head is still dictated (single-pick intact)
    drive_ok = directive.startswith("⚙ WORKLIST-DRIVER") and "`AX-04`" in directive
    ok = (got_s == expect_synth) and (got_i == expect_ident) and drive_ok
    print("  [%s] %s: synth=%s(exp %s) ident=%s(exp %s) drive-intact=%s"
          % ("PASS" if ok else "FAIL", name, got_s, expect_synth, got_i, expect_ident, drive_ok))
    results.append(ok)


run_cadence("(t1) iter=4 → no riders", 4, False, False)
run_cadence("(t2) iter=5 → synthesis (cross-thread forcing)", 5, True, False)
run_cadence("(t3) iter=7 → no riders (default is clean)", 7, False, False)
run_cadence("(t4) iter=8 → identity-Sherlock", 8, False, True)
run_cadence("(t5) iter=40 → BOTH riders (5|40 and 8|40)", 40, True, True)

print("\n%d/%d PASS" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
