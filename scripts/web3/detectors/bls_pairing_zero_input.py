#!/usr/bin/env python3
"""
BLS / pairing zero-input verifier bypass (Cat 14.12, focused).

A signature verifier that computes a pairing check and trusts the boolean result
WITHOUT rejecting degenerate inputs is trivially bypassable:

    e(0, X) == e(X, 0) == identity == e(g, g)^0

so a pairing equality  e(sig, g2) == e(H(m), pk)  is satisfied for ANY message when
sig and/or pk are zero (or the point at infinity / identity element / off-subgroup).

    Bonzo Lend / Supra oracle 2026-07-11 ($9.05M, Hedera): the Supra BLS price-update
    verifier accepted a zeroed signature [0,0]; pairing on Hedera precompile 0.0.8
    returned true for zero inputs -> fake SAUCE price (~1e30) -> drained the lending pool.
    Root cause lived in the third-party oracle verifier, OUTSIDE Bonzo's audited perimeter
    (3x Halborn, all clean) — the canonical trust-boundary bug.

This is the sharpest, greppable half of verifier_binding_audit.py: it isolates pairing/BLS
call-sites and checks whether every curve input is non-zero + subgroup-guarded before the
result is trusted. Language-agnostic (Solidity / Rust / Cairo / Go precompile wrappers).

Usage:
    py -3 -X utf8 bls_pairing_zero_input.py --src <path-to-repo-or-file>
    py -3 -X utf8 bls_pairing_zero_input.py --src ./verifier --json out.json

Transfer note: Supra is read on many chains; any protocol trusting the same aggregated-
signature verifier is a live transfer-candidate (feedback_protocol_family_bug_transfer).
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _boundary_util import func_spans, enclosing_block, iter_source_files

SRC_EXT = (".sol", ".rs", ".cairo", ".vy", ".go", ".move")

# Pairing / BLS call-sites (camelCase-aware: blsPairing, ecPairing, verifyBls) and the
# EVM/Hedera precompiles that back them.
PAIRING_SITE = re.compile(
    r"\b\w*[Pp]airing\s*\(|\b\w*[Bb]ls[_A-Za-z]*(?:Verify|Pairing|Aggregate)\w*\s*\(|"
    r"\bmillerLoop\s*\(|\bfinalExp\w*\s*\(|\bbn256\w*\s*\(|\baggregateVerify\s*\(|\bfastAggregateVerify\s*\(|"
    r"staticcall\(\s*0x0?8\b|address\(0x0?8\)|precompile\s*0\.0\.8|\b0\.0\.8\b|"
    # inline-assembly EVM pairing precompile: staticcall(<gas>, 8, ...) — 8 is the 2nd (address) arg.
    r"staticcall\([^,]+,\s*8\b",
)

# Guards that make a pairing input safe. Absence in the surrounding block = flag.
# NOTE: no bare `!= 0` — it false-matches the pairing RESULT check `out[0] != 0` (which every
# BN254 lib has) and made the detector silent on real verifiers. Input guards are recognized only
# via require/assert forms, isZero/subgroup/on-curve helpers, or an explicit call to a validator.
GUARD = re.compile(
    r"(isZero|is_zero|"
    r"point[_ ]?at[_ ]?infinity|isInfinity|is_infinity|"
    r"subgroup|inSubgroup|is_in_group|isInGroup|isOnCurve|is_on_curve|clearCofactor|"
    r"isValidSignature|"
    r"require\([^)]*!=\s*(?:0|bytes32\(0\))|assert[!(][^)]*!=\s*0)",
    re.I,
)

# Explicit degenerate literals near a pairing input = strong signal.
ZERO_LIKE = re.compile(
    r"\[\s*0\s*,\s*0\s*\]|G1\.zero|G2\.zero|G1Point\(0\s*,\s*0\)|point\(0\s*,\s*0\)|"
    r"Fq\.zero|infinity\(\)|Identity\b",
    re.I,
)


def scan_file(path, ctx=10):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return []
    spans = func_spans(lines)
    out = []
    for i, line in enumerate(lines):
        if line.lstrip().startswith(("//", "*", "#", "/*")):
            continue  # skip comment lines
        if not PAIRING_SITE.search(line):
            continue
        block = enclosing_block(lines, i, spans, ctx)
        guarded = bool(GUARD.search(block))
        zero_seen = bool(ZERO_LIKE.search(block))
        if guarded and not zero_seen:
            continue  # inputs appear guarded — not the degenerate-input class
        sev = "HIGH" if (zero_seen or not guarded) else "MED"
        why = "pairing/BLS site with NO non-zero+subgroup guard on inputs — e(0,X)=identity bypass (Bonzo/Supra $9.05M)"
        if zero_seen:
            why = "zero/identity literal near a pairing input — " + why
        out.append({"file": path, "line": i + 1, "severity": sev, "code": line.strip()[:200], "why": why})
    return out


def main():
    ap = argparse.ArgumentParser(description="BLS/pairing zero-input verifier bypass (Cat 14.12).")
    ap.add_argument("--src", required=True, help="repo dir or single source file")
    ap.add_argument("--json", help="also write structured findings to this JSON file")
    args = ap.parse_args()

    if not os.path.exists(args.src):
        print("src not found: %s" % args.src, file=sys.stderr)
        return 2

    findings = []
    for path in iter_source_files(args.src, SRC_EXT, extra_skip=("test", "mock")):
        findings.extend(scan_file(path))

    for f in findings:
        print("%s:%d  [%s]" % (f["file"], f["line"], f["severity"]))
        print("    %s" % f["code"])
        print("    %s\n" % f["why"])

    print("--- %d pairing/BLS site(s) flagged. Heuristic — verify every curve input is "
          "non-zero + in-subgroup BEFORE the result is trusted. ---" % len(findings))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(findings, fh, indent=2)
        print("wrote %s" % args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
