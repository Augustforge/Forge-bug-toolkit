#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Replay test for B6 EXIT-DIFF on human exit ("we're leaving") (audit 2026-08-09) — _exit_diff.

Root cause: a human exit ("we're leaving") zeroed out ALL completeness gates — Un-Dup Sweep /
PRIOR-PATTERNS / EXPOSURE / D-NN stayed TODO/empty (1inch), with no warning. On RELEASE, B6 collects
the unclosed soft gates → stderr INFO (NOT a block — exiting is the operator's prerogative).
Test: FIRING + anti-FP.

Run: py -3 -X utf8 bug-bounty-toolkit/scripts/_methodology/exit_diff_replay.py
"""
import contextlib
import importlib.util
import io
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GATE = os.path.join(ROOT, "scripts", "hooks", "hunt_completeness_gate.py")
spec = importlib.util.spec_from_file_location("gate_b6", GATE)
G = importlib.util.module_from_spec(spec)
spec.loader.exec_module(G)

_DETS = ("active_undup_sweep_incomplete", "active_pattern_replay_skipped",
         "active_exposure_scan_skipped", "active_zero_divergence_unescalated",
         "active_executable_floor_unrun")


def _set(**vals):
    """Mock the detectors: name -> return value (truthy = gate open)."""
    for name in _DETS:
        setattr(G, name, lambda s, _v=vals.get(name): _v)


def _capture():
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        G._exit_diff("sid")
    return buf.getvalue()


def run():
    ok = fail = 0

    def check(name, cond):
        nonlocal ok, fail
        if cond:
            ok += 1
            print("  [PASS] %s" % name)
        else:
            fail += 1
            print("  [FAIL] %s" % name)

    # 1. FIRING: 2 gates open → exit-diff outputs both
    _set(active_undup_sweep_incomplete="x", active_exposure_scan_skipped="y")
    out = _capture()
    check("FIRING: exit-diff is output when gates unclosed", "EXIT-ДИФФ" in out)  # Russian marker kept: matches the hook's actual output
    check("FIRING: Un-Dup Sweep listed", "Un-Dup" in out)
    check("FIRING: EXPOSURE listed", "EXPOSURE" in out)
    check("FIRING: NOT a block (text 'does not block exit')", "прерогатива" in out)  # Russian marker kept: matches the hook's actual output

    # 2. anti-FP: all gates closed → silence
    _set()
    check("anti-FP: all closed → no output", _capture() == "")

    # 3. zero-D-NN open (Mandate 0.9) → into the diff
    _set(active_zero_divergence_unescalated=5)
    out = _capture()
    check("FIRING: 0 D-NN lands in exit-diff", "D-NN" in out and "0.9" in out)

    # 4. executable-floor open → into the diff
    _set(active_executable_floor_unrun=21)
    out = _capture()
    check("FIRING: executable-floor lands in exit-diff", "executable" in out)

    # 5. detector raises an exception → fail-open (does not crash the exit)
    def _boom(s):
        raise RuntimeError("boom")
    for n in _DETS:
        setattr(G, n, _boom)
    try:
        _capture()
        check("fail-open: detector exception does not crash _exit_diff", True)
    except Exception:
        check("fail-open: detector exception does not crash _exit_diff", False)

    print("\n%d/%d B6 exit-diff cases green" % (ok, ok + fail))
    return fail == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
