#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression for `_has_valid_exit` — detection of the HUNT-EXIT token (money-critical loop-release).

Context (1inch re-pilot MED-4 / judge round-2 HIGH): `_EXIT_RE.search(lt)` matched the SPECIFIC
`HUNT-EXIT: T4-CONFIRMED High/Critical` even inside backtick-wrapped prose / a RULES pointer → it
falsely silenced the ENTIRE completeness cascade (all 11 off-switch call-sites + ledger_success_exit)
and falsely RELEASED the auto-loop. Fix = a single `_has_valid_exit`: skip backtick code spans AT THE
SEGMENT LEVEL (not the whole line — a real exit line may carry a backtick file reference), + the
positional void semantics are preserved (Berachain).

Rule (feedback_hook_must_prove_firing): the test proves BOTH directions — a real exit RELEASES,
backtick prose does NOT release. Money-critical: the only success exit of the auto-loop. Exit 1 on any FAIL.
Run: py -3 -X utf8 scripts/_methodology/exit_detection_replay.py
"""
import importlib.util
import os
import sys

_HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks", "hunt_completeness_gate.py")
spec = importlib.util.spec_from_file_location("gate", _HOOK)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

results = []


def check(name, text, expect):
    got = g._has_valid_exit(text)
    ok = (bool(got) == expect)
    print("  [%s] %s: valid_exit=%s expect=%s" % ("PASS" if ok else "FAIL", name, bool(got), expect))
    results.append(ok)


# ── REAL exit RELEASES (Loop-State field, not backtick) ──
check("real High (Loop-State field)", "## Loop State\n- **HUNT-EXIT: T4-CONFIRMED High**\n", True)
check("real Critical", "- **HUNT-EXIT: T4-CONFIRMED Critical**\n", True)
check("real + separator markdown", "HUNT-EXIT: T4-CONFIRMED: High\n", True)
# segment precision: a real exit line CARRIES a backtick file reference — the exit must NOT be lost.
check("real High + backtick file-ref same line",
      "- **HUNT-EXIT: T4-CONFIRMED Critical** — H-09 proven (`vault.sol:88`)\n", True)
# a real exit AFTER a backtick example in the same ledger (mixed) → releases.
check("backtick example ABOVE + real below",
      "RULES: exit = `HUNT-EXIT: T4-CONFIRMED High`.\n\n- **HUNT-EXIT: T4-CONFIRMED High**\n", True)

# ── backtick-wrapped SPECIFIC token does NOT release (MED-4) ──
check("backtick-wrapped concrete High (prose)", "RULES: the only exit = `HUNT-EXIT: T4-CONFIRMED High`.\n", False)
check("backtick Critical example", "see `HUNT-EXIT: T4-CONFIRMED Critical` ends the loop\n", False)
check("backtick inside RULES bullet", "6. The loop exit is EXACTLY ONE = `HUNT-EXIT: T4-CONFIRMED High`\n", False)

# ── placeholder / Medium / empty do NOT release (no regression) ──
check("placeholder <High|Critical>", "- **HUNT-EXIT: T4-CONFIRMED <High|Critical>**\n", False)
check("Medium token", "- **HUNT-EXIT: T4-CONFIRMED Medium**\n", False)
check("no token", "## Loop State\n- **Iteration #:** 7\n", False)
check("empty", "", False)
check("None", None, False)

# ── positional void semantics (Berachain 2026-07-13) PRESERVED ──
check("real then void (reversed) → void wins",
      "- **HUNT-EXIT: T4-CONFIRMED High**\n- HUNT-EXIT superseded: reversed on dedup\n", False)
check("void then real (reconfirm after reversal) → valid",
      "- HUNT-EXIT superseded: reversed\n- **HUNT-EXIT: T4-CONFIRMED High**\n", True)
check("real, void, real (re-reconfirm) → valid",
      "- **HUNT-EXIT: T4-CONFIRMED High**\n- HUNT-EXIT reversed\n- **HUNT-EXIT: T4-CONFIRMED Critical**\n", True)
check("real, real, void (last is void) → invalid",
      "- **HUNT-EXIT: T4-CONFIRMED High**\n- **HUNT-EXIT: T4-CONFIRMED Critical**\n- HUNT-EXIT retracted\n", False)
# a void line itself inside backticks → not counted as void (the backtick skip is symmetric for void)
check("backtick void + real exit → valid (backtick void not counted)",
      "cancellation example: `HUNT-EXIT superseded`\n- **HUNT-EXIT: T4-CONFIRMED High**\n", True)

# ── ledger_success_exit delegates to _has_valid_exit (unification) ──
_cur = {"t": None}
g._read_ledger = lambda sid: _cur["t"]
_cur["t"] = "- **HUNT-EXIT: T4-CONFIRMED High**\n"
r1 = g.ledger_success_exit("sid")
_cur["t"] = "RULES: exit = `HUNT-EXIT: T4-CONFIRMED High`\n"
r2 = g.ledger_success_exit("sid")
ok = (r1 is True and r2 is False)
print("  [%s] ledger_success_exit delegates: real=%s btick=%s" % ("PASS" if ok else "FAIL", r1, r2))
results.append(ok)

print("\n%d/%d PASS" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
