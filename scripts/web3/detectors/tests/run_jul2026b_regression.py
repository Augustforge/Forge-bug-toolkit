#!/usr/bin/env python3
"""
Regression for the July-2026 (second-half) detectors — locks in that they keep catching
the real hacks they were built for and stay SILENT on patched/clean/other-class code.

"Measure, don't feel": re-run after ANY edit to these detectors. Seeded from the
11-20 Jul 2026 ingest:
  - Cat 5.14  oracle_report_timestamp_bound.py  Ostium future-dated report   (~$18-24M)
  - Cat 3.16  peg_check_asymmetry.py            Chi Protocol mint/burn peg    ($USC)
  - Cat 9.7   breaker_rearm_cooldown.py         ArcadiaFi cooldown+dual-role  ($3.6M)

Each row asserts finding-count >=1 (must-catch) or ==0 (must-be-silent). Cross-class
silence rows are the precision guarantee — they fail if a regex starts over-matching.

These detectors take a POSITIONAL source path (like checkpoint_staleness.py), not --src.

Usage:
    py -3 -X utf8 run_jul2026b_regression.py       # run matrix, exit 1 on any FAIL
    py -3 -X utf8 run_jul2026b_regression.py -v     # also print raw detector output
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DETDIR = os.path.dirname(HERE)
FIX = os.path.join(HERE, "jul2026b_fixtures")

# (detector, fixture, expect_flagged, note)
MATRIX = [
    # --- Cat 5.14 future-dated oracle report ---
    ("oracle_report_timestamp_bound.py", "ostium_vuln.sol",  True,  "5.14 signer-auth + report ts, no upper bound"),
    ("oracle_report_timestamp_bound.py", "ostium_fixed.sol", False, "5.14 patched (reportTs <= block.timestamp)"),

    # --- Cat 3.16 mint/burn peg-check asymmetry ---
    ("peg_check_asymmetry.py",           "chi_vuln.sol",     True,  "3.16 mint peg-aware, burn hardcoded peg"),
    ("peg_check_asymmetry.py",           "chi_fixed.sol",    False, "3.16 patched (burn re-checks peg)"),

    # --- Cat 9.7 breaker re-arm cooldown + dual-role ---
    ("breaker_rearm_cooldown.py",        "arcadia_vuln.sol", True,  "9.7 breaker cooldown + router call + dual registry"),

    # --- cross-class silence = PRECISION guarantee ---
    ("oracle_report_timestamp_bound.py", "chi_vuln.sol",     False, "oracle scanner silent on 3.16"),
    ("oracle_report_timestamp_bound.py", "arcadia_vuln.sol", False, "oracle scanner silent on 9.7"),
    ("peg_check_asymmetry.py",           "ostium_vuln.sol",  False, "peg scanner silent on 5.14"),
    ("peg_check_asymmetry.py",           "arcadia_vuln.sol", False, "peg scanner silent on 9.7"),
    ("breaker_rearm_cooldown.py",        "chi_vuln.sol",     False, "breaker scanner silent on 3.16"),
    ("breaker_rearm_cooldown.py",        "ostium_vuln.sol",  False, "breaker scanner silent on 5.14"),

    # --- clean baseline: every detector silent on a plain ERC20 ---
    ("oracle_report_timestamp_bound.py", "clean.sol",        False, "clean baseline"),
    ("peg_check_asymmetry.py",           "clean.sol",        False, "clean baseline"),
    ("breaker_rearm_cooldown.py",        "clean.sol",        False, "clean baseline"),
]


def run_detector(script, fixture):
    src = os.path.join(FIX, fixture)
    fd, tmp = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        cmd = [sys.executable, os.path.join(DETDIR, script), src, "--json", tmp]
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=env)
        try:
            with open(tmp, "r", encoding="utf-8") as fh:
                count = len(json.load(fh))
        except (OSError, ValueError):
            count = None
        return count, (proc.stdout or "") + (proc.stderr or "")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def main():
    verbose = "-v" in sys.argv
    passed = failed = 0
    print("Jul-2026b detector regression - %d rows\n" % len(MATRIX))
    for script, fixture, expect_flagged, note in MATRIX:
        count, raw = run_detector(script, fixture)
        if count is None:
            ok, got = False, "ERROR (no JSON)"
        else:
            ok = (count >= 1) if expect_flagged else (count == 0)
            got = "%d finding(s)" % count
        want = "flag" if expect_flagged else "silent"
        tag = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1
        print("  [%s] %-34s %-18s want=%-6s got=%-14s | %s"
              % (tag, script, fixture, want, got, note))
        if not ok or verbose:
            for ln in raw.splitlines():
                if ln.strip():
                    print("         > %s" % ln)
    print("\n--- %d passed, %d failed ---" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
