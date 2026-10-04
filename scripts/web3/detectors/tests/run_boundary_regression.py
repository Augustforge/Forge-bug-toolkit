#!/usr/bin/env python3
"""
Boundary-detector regression — locks in that the three boundary-centric detectors keep
catching the real 2026 hacks they were built for, and stay SILENT on the patched/clean
versions and on other classes' bugs.

Why this exists: detector fixtures rot silently (the checkpoint_*.sol fixtures next door had
NO runner and were dead weight). "Measure, don't feel" — any future edit to a boundary
detector / _boundary_util re-runs this; a broken catch or a new false-positive fails CI here,
not in a live hunt. Seeded from reference_jul2026_boundary_ingest:
  - Cat 14.12  Bonzo Lend / Supra BLS zero-input        ($9.05M, 2026-07-11)
  - Cat 14.13  Aztec escapeHatch + Hinkal prooflessDeposit ($2.98M, 2026-06/07)
  - Cat 3.15   Summer.fi NAV stale-inclusion            ($6.04M, 2026-07-06)

Each row asserts: run <detector> on <fixture> --json → finding-count is >=1 (must-catch) or
==0 (must-be-silent). Cross-class silence rows (a detector silent on ANOTHER class's vuln)
are the precision guarantee — they fail if a regex starts over-matching.

Usage:
    py -3 -X utf8 run_boundary_regression.py            # run the matrix, exit 1 on any FAIL
    py -3 -X utf8 run_boundary_regression.py -v         # also print each detector's raw findings

To extend: add a row to MATRIX. The checkpoint_*.sol fixtures (checkpoint_staleness.py) are a
natural next batch — same shape, different detector.
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DETDIR = os.path.dirname(HERE)                      # .../web3/detectors
FIX = os.path.join(HERE, "boundary_fixtures")

# (detector script, fixture file, expect_flagged, note)
#   expect_flagged True  -> must produce >=1 finding (must-catch)
#   expect_flagged False -> must produce 0 findings  (must-be-silent: patched, clean, or other class)
MATRIX = [
    # --- Cat 14.12 BLS/pairing zero-input (Bonzo/Supra) ---
    ("verifier_binding_audit.py", "boundary_bls_vuln.sol",      True,  "14.12 pairing no input-guard"),
    ("verifier_binding_audit.py", "boundary_bls_fixed.sol",     False, "14.12 patched (sig!=0 + subgroup)"),
    ("bls_pairing_zero_input.py", "boundary_bls_vuln.sol",      True,  "14.12 focused scanner catches"),
    ("bls_pairing_zero_input.py", "boundary_bls_fixed.sol",     False, "14.12 patched, focused silent"),
    # real-world inline-asm form: staticcall(gas,8,...) + `out[0]!=0` result-check (2 FNs fixed on Supra hunt)
    ("bls_pairing_zero_input.py", "boundary_bls_asm_vuln.sol",  True,  "14.12 inline-asm staticcall(gas,8) no input guard"),
    ("verifier_binding_audit.py", "boundary_bls_asm_vuln.sol",  True,  "14.12 asm form caught by binding audit too"),

    # --- Cat 14.13 proof-binding (Aztec escapeHatch + Hinkal prooflessDeposit) ---
    ("verifier_binding_audit.py", "boundary_binding_vuln.sol",  True,  "14.13 recipient-param + proofless"),
    ("verifier_binding_audit.py", "boundary_binding_fixed.sol", False, "14.13 patched (recipient=public input, verify added)"),

    # --- Cat 3.15 NAV stale-inclusion (Summer.fi) ---
    ("orphaned_tvl_enum.py",      "boundary_nav_vuln.sol",      True,  "3.15 capped ark still summed in NAV"),
    ("orphaned_tvl_enum.py",      "boundary_nav_fixed.sol",     False, "3.15 patched (arkCapped skipped)"),

    # --- cross-class silence = PRECISION guarantee (detector must ignore other classes' bugs) ---
    ("bls_pairing_zero_input.py", "boundary_binding_vuln.sol",  False, "bls scanner silent on 14.13 (no pairing)"),
    ("orphaned_tvl_enum.py",      "boundary_bls_vuln.sol",      False, "nav scanner silent on 14.12"),
    ("verifier_binding_audit.py", "boundary_nav_vuln.sol",      False, "verify scanner silent on 3.15 (no verify call)"),

    # --- clean baseline: every detector silent on a plain ERC20 ---
    ("verifier_binding_audit.py", "boundary_clean.sol",         False, "clean baseline"),
    ("bls_pairing_zero_input.py", "boundary_clean.sol",         False, "clean baseline"),
    ("orphaned_tvl_enum.py",      "boundary_clean.sol",         False, "clean baseline"),
]


def run_detector(script, fixture):
    """Run a detector on one fixture via --src/--json, return (count, raw_stdout)."""
    src = os.path.join(FIX, fixture)
    fd, tmp = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        cmd = [sys.executable, os.path.join(DETDIR, script), "--src", src, "--json", tmp]
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=env)
        try:
            with open(tmp, "r", encoding="utf-8") as fh:
                findings = json.load(fh)
            count = len(findings)
        except (OSError, ValueError):
            count = None  # detector didn't write JSON -> treat as error
        return count, (proc.stdout or "") + (proc.stderr or "")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def main():
    verbose = "-v" in sys.argv
    passed = failed = 0
    print("Boundary-detector regression — %d rows\n" % len(MATRIX))
    for script, fixture, expect_flagged, note in MATRIX:
        count, raw = run_detector(script, fixture)
        if count is None:
            ok = False
            got = "ERROR (no JSON)"
        else:
            ok = (count >= 1) if expect_flagged else (count == 0)
            got = "%d finding(s)" % count
        want = "flag" if expect_flagged else "silent"
        tag = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1
        print("  [%s] %-28s %-26s want=%-6s got=%-14s | %s"
              % (tag, script, fixture, want, got, note))
        if not ok or verbose:
            for ln in raw.splitlines():
                if ln.strip():
                    print("         > %s" % ln)
    print("\n--- %d passed, %d failed ---" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
