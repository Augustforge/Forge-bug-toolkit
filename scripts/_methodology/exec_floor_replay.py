#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Replay test for B2 EXECUTABLE-FLOOR (audit 2026-08-09) — active_executable_floor_unrun / _has_executable_run.

System rule (HANDOFF §7 item 4): the test MUST prove FIRING on a real scenario + the absence of FPs
on healthy ones. Root cause: an axelar hunt — 21 T9 axes, ZERO fork-PoCs (all depth traces static),
while the fork-diff gate arms only from `PARENT-FORK` (forks) → on a non-fork there was no equivalent.
B2 is the soft-nudge that closes this.

Run: py -3 -X utf8 scripts/_methodology/exec_floor_replay.py
"""
import importlib.util
import os
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GATE = os.path.join(ROOT, "scripts", "hooks", "hunt_completeness_gate.py")
spec = importlib.util.spec_from_file_location("gate_b2", GATE)
G = importlib.util.module_from_spec(spec)
spec.loader.exec_module(G)

# ── synthetic fixtures ────────────────────────────────────────────────────
# Mature model: >=3 I-NN with a status (matured_count >= 3 via _i_rows/_status_of).
MODEL_MATURE = """## Invariants
| I-NN | invariant | pred | status | component |
|---|---|---|---|---|
| I-01 | mint exclusivity | pred: only gateway | ENFORCED | gw |
| I-02 | conservation | pred: sum==0 | ENFORCED | acc |
| I-03 | replay-once | pred: nonce | ENFORCED | state |
| I-04 | flow-limit | pred: bounded | ENFORCED | flow |
"""
MODEL_NA = "MODEL: N/A — single-contract <300 LOC\n"

def _axes(n):
    """Generate the T9 field the way _t9_axes_used parses it (comma-separated list of axes)."""
    return ", ".join("axis%d" % (i + 1) for i in range(n))


def _ledger(n_axes, parent_fork="N/A — not a fork", extra=""):
    return (
        "## Loop State\n"
        "- **Iteration #:** 8\n"
        "- **T9 restart axes used:** %s\n"
        "- **PARENT-FORK:** %s\n"
        "- **Depth-Lead:** boundary — 5/5 (a->b->c->d->e)\n"
        "%s" % (_axes(n_axes), parent_fork, extra)
    )

CASES = []  # (name, ledger, model, files_in_deep, expect_fires)

# 1. axelar-like: many axes, N/A fork, 0 executable → FIRES
CASES.append(("axelar-like: 21 axes, 0 executable → FIRES",
              _ledger(21), MODEL_MATURE, [], True))
# 2. balancer-like: executable file deep/*.t.sol → silent
CASES.append(("balancer-like: deep/*.t.sol present → silent",
              _ledger(17), MODEL_MATURE, ["ECLPSurgeClampBypass.t.sol"], False))
# 3. 1inch-like: ledger carries T11-VERDICT: DONE → silent
CASES.append(("1inch-like: T11-VERDICT: DONE → silent",
              _ledger(6, extra="- **T11-VERDICT:** DONE (fuzz 3×2000 PASS)\n"),
              MODEL_MATURE, [], False))
# 4. ledger [PASS] from forge → silent
CASES.append(("ledger carries [PASS] (forge output) → silent",
              _ledger(7, extra="Verifier Log: [PASS] testFoo\n"), MODEL_MATURE, [], False))
# 5. anti-FP: few axes (< threshold) → silent
CASES.append(("anti-FP: 2 axes (< EXEC_FLOOR_AXES) → silent",
              _ledger(2), MODEL_MATURE, [], False))
# 6. anti-FP: MODEL: N/A → silent (small contract)
CASES.append(("anti-FP: MODEL N/A → silent",
              _ledger(9) + "\nMODEL: N/A — single-contract\n", MODEL_NA, [], False))
# 7. anti-FP: recognized fork → silent (fork_diff_unrun handles it)
CASES.append(("anti-FP: PARENT-FORK Compound → silent (fork path handles it)",
              _ledger(8, parent_fork="Compound v2 — Comptroller/CToken"), MODEL_MATURE, [], False))
# 8. anti-FP: immature model (< 3 I-NN) → silent
CASES.append(("anti-FP: immature model (1 I-NN) → silent",
              _ledger(9),
              "| I-01 | x | pred: y | ENFORCED | z |\n", [], False))
# 9. runs: N (foundry fuzz output) → silent
CASES.append(("ledger carries 'runs: 10000' (fuzz) → silent",
              _ledger(6, extra="testDoUndoFuzz (runs: 10000)\n"), MODEL_MATURE, [], False))
# 10. anti-FP: a bare mention of 'echidna unavailable' is NOT counted as a run → FIRES
CASES.append(("anti-FP: 'echidna DEFERRED/unavailable' = mention, not a run → FIRES",
              _ledger(11, extra="- **T11-VERDICT:** APPLICABLE (native forge/echidna unavailable, DEFERRED)\n"),
              MODEL_MATURE, [], True))


def run():
    ok = 0
    fail = 0
    for name, ledger, model, deep_files, expect in CASES:
        d = tempfile.mkdtemp(prefix="b2_")
        try:
            with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
                f.write(ledger)
            if deep_files:
                os.makedirs(os.path.join(d, "deep"), exist_ok=True)
                for fn in deep_files:
                    with open(os.path.join(d, "deep", fn), "w", encoding="utf-8") as f:
                        f.write("// poc")
            # monkeypatch context accessors
            G.freshest_active_ledger = lambda cid, _d=d: (os.path.join(_d, "hypotheses.md"), ROOT)
            G._model_ctx = lambda cid, _l=ledger, _m=model: (_l, _m, None)
            res = G.active_executable_floor_unrun("sid")
            fires = res is not None
            if fires == expect:
                ok += 1
                print("  [PASS] %s" % name)
            else:
                fail += 1
                print("  [FAIL] %s  (fires=%s expect=%s, res=%r)" % (name, fires, expect, res))
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
    print("\n%d/%d B2 exec-floor cases green" % (ok, ok + fail))
    return fail == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
