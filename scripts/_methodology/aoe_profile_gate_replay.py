#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AOE profile-cleared gate replay — PROVES the detector
`active_practicality_kill_unprofiled` fires (AOE §2.1/§4 — the CORE of the track, fixes the premature
practicality refute).

System rule ([[feedback_hook_must_prove_firing]]): a replay test MUST prove FIRING —
it must fail if the detector is removed. Here the detector is called directly from the LIVE hook (importlib, not a copy);
remove the function/reasons -> `call()` returns "MISSING" -> all cases FAIL -> exit 1.

What is proven (brief Task 2, item 7):
  (a) FIRES hard on a practicality-kill ([DE-MINIMIS]) WITHOUT `profile-cleared`, corpus>=2;
  (b) SILENT when `profile-cleared: <ref>` is present; (b2) §5.4 UNRESOLVED-needs-approval is valid;
  (c) corpus-first: <2 cases -> reminder (NOT hard);
  (d) fail-open: broken manifest (-1) -> reminder (NEVER a hard hold on a parse error);
  (e) SYMMETRY on the confirm side: [CAPITAL-DEP] without a ref FIRES; with a ref -> SILENT;
  (+) SILENT on the untouched `hypotheses_template.md` (a fresh hunt is not blocked);
  (+) the real manifest reads as corpus>=2 (Task 1 added 2 cases).

Run: py -3 -X utf8 scripts/_methodology/aoe_profile_gate_replay.py
"""
import importlib.util
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
# The HOOK path can be overridden via argv[1] — to check "the test fails without the detector" against a stripped copy.
HOOK = sys.argv[1] if len(sys.argv) > 1 else \
    os.path.join(ROOT, "bug-bounty-toolkit", "scripts", "hooks", "hunt_completeness_gate.py")
TPL_LEDGER = os.path.join(ROOT, "bug-bounty-toolkit", "sessions", "_methodology", "hypotheses_template.md")


def load_gate():
    spec = importlib.util.spec_from_file_location("gate", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gate = load_gate()
work = tempfile.mkdtemp()
LP = os.path.join(work, "hypotheses.md")


def put(txt):
    with open(LP, "w", encoding="utf-8") as f:
        f.write(txt)
    gate.freshest_active_ledger = lambda sid: (LP, work)


def set_corpus(n):
    gate._false_refute_corpus_count = lambda: n


def call(sid="sid"):
    """Detector from the LIVE hook. Function removed -> 'MISSING' -> all mode/None checks FAIL (proof-of-firing)."""
    try:
        return gate.active_practicality_kill_unprofiled(sid)
    except AttributeError:
        return "MISSING"


results = []


def check(name, cond, why):
    ok = bool(cond)
    print("  [%s] %-48s — %s" % ("PASS" if ok else "FAIL", name, why))
    results.append(ok)


REG = "# T — Hypotheses Registry\n"
KILL_NOCLEAR = (REG + "### H-05 [DE-MINIMIS]: leak dust\n"
                "- Killed by (severity-judgment): leak < 1 unit; not amplifiable\n")
KILL_CLEARED = KILL_NOCLEAR + \
    "- profile-cleared: attacker_capability_baseline.md#eth — flash cannot amplify sub-unit dust\n"
KILL_UNRESOLVED = KILL_NOCLEAR + \
    "- profile-cleared: UNRESOLVED-needs-approval — realism reachable only via active probe\n"
CONFIRM_CAP = (REG + "### H-08 [CAPITAL-DEP]: High only via $100M flash\n"
               "- Severity if confirmed: High\n")
CONFIRM_CLEARED = CONFIRM_CAP + \
    "- profile-cleared: attacker_profile.md#payout — flashloan-excluded by program clause -> Low\n"

print("AOE profile-cleared gate — proof-of-firing (detector from the live hunt_completeness_gate.py)\n")

# (a) FIRES hard — practicality-kill without profile-cleared, corpus>=2 (hard block armed)
set_corpus(2)
put(KILL_NOCLEAR)
r = call()
check("(a) fires HARD on [DE-MINIMIS] w/o profile-cleared", r != "MISSING" and r and r[0] == "hard",
      "corpus>=2 -> holds the exit (gate on the tag STATE, not on vocabulary)")

# (b) SILENT — companion profile-cleared present
put(KILL_CLEARED)
check("(b) SILENT when profile-cleared: <ref> present", call() is None,
      "the companion field lifts the gate")

# (b2) §5.4 — UNRESOLVED-needs-approval is a valid non-blocking status (the gate does NOT force an active probe)
put(KILL_UNRESOLVED)
check("(b2) UNRESOLVED-needs-approval satisfies (§5.4)", call() is None,
      "white-hat: the gate NEVER forces an active probe")

# (c) corpus-first: <2 -> reminder (NOT hard)
set_corpus(1)
put(KILL_NOCLEAR)
r = call()
check("(c) corpus<2 -> REMINDER not hard", r != "MISSING" and r and r[0] == "reminder",
      "the hard block is armed ONLY with >=2 labeled cases (§6)")

# (d) fail-open: broken/missing manifest (-1) -> reminder, never a hard hold
set_corpus(-1)
put(KILL_NOCLEAR)
r = call()
check("(d) fail-open broken manifest -> REMINDER", r != "MISSING" and r and r[0] == "reminder",
      "parse error / no manifest NEVER holds the exit")

# (e) SYMMETRY on the confirm side: [CAPITAL-DEP] without a ref FIRES hard; with a ref -> SILENT
set_corpus(2)
put(CONFIRM_CAP)
r = call()
check("(e) confirm [CAPITAL-DEP] w/o ref fires HARD", r != "MISSING" and r and r[0] == "hard",
      "symmetry §2.1: confirm is also netted against payout clauses")
put(CONFIRM_CLEARED)
check("(e2) confirm SILENT with profile-cleared", call() is None,
      "inflated confirm is netted against payout clauses -> clean")

# (+) SILENT on the untouched template — a fresh hunt is NOT blocked (all tags in {..}/scaffold)
set_corpus(2)
put(open(TPL_LEDGER, encoding="utf-8").read())
check("(+) SILENT on pristine hypotheses_template.md", call() is None,
      "tags [DE-MINIMIS]/[CAPITAL-DEP]/profile-cleared in {placeholder}/scaffold -> not real triggers")

# (+) the corpus reader sees the REAL manifest as >=2 (Task 1 added two example cases)
check("(+) real manifest false_refute_eval >= 2 (Task 1)", load_gate()._false_refute_corpus_count() >= 2,
      "false_refute_eval.cases contains >=2 labeled cases -> hard mode is legitimate")

# (+) proof-of-firing: the detector + reasons must EXIST and be wired into the hook
check("(+) detector + reasons wired into hook", all(hasattr(gate, n) for n in
      ("active_practicality_kill_unprofiled", "PROFILE_CLEARED_REASON", "PROFILE_CLEARED_REMINDER")),
      "remove the detector/reasons -> the test fails (feedback_hook_must_prove_firing)")

shutil.rmtree(work, ignore_errors=True)
n_ok = sum(results)
print("\n%d/%d AOE profile-cleared gate cases green" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
