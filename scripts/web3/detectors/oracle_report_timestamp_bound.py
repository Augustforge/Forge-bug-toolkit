#!/usr/bin/env python3
"""
Future-dated / no-upper-bound oracle report-timestamp detector (Cat 5.14).

NOT a Slither detector — a grep-grade heuristic triage aid. It surfaces oracle
verifier functions that authenticate a SIGNED price report (recover the signer and
check an authorized-signer allowlist) yet DO NOT bound the report's own timestamp
against `block.timestamp` — the mirror of the classic staleness lower-bound.

    Classic staleness (present):   require(block.timestamp - reportTs <= maxDelay); // too OLD
    Missing mirror (Cat 5.14):     require(reportTs <= block.timestamp + tolerance); // too NEW / future

This is the Ostium Jul-2026 class (~$18-24M, Arbitrum): the verifier checked ECDSA
sig + signer authorization but not the report timestamp, so a compromised/insider
signer pushed a FUTURE-dated report and, if "newer timestamp wins," overwrote the
real price with an attacker value.

The detector flags a function when it has BOTH:
  (A) signer authentication  (ecrecover / .recover / bls / verify + an authorized[] / onlyOracle gate)
  (B) it consumes a report timestamp   (reportTimestamp / publishTime / report.time / .timestamp field)
and LACKS:
  (C) an upper-bound compare of that timestamp vs block.timestamp
      (`reportTs <= block.timestamp`  or  `> block.timestamp ... revert`)

A site with (A)+(B) and NO (C) is the Ostium shape. This does NOT prove a bug —
each flag needs the manual "is the report timestamp bounded on BOTH sides, and is the
price sanity-banded vs the previous?" check.

See: bug-bounty-toolkit/methodology/hypothesis_taxonomy.md Cat 5.14.

Usage:
    py -3 -X utf8 oracle_report_timestamp_bound.py <path-to-sol-src> [--json out.json] [--all]
"""

import argparse
import json
import os
import re
import sys

# (A) signer authentication primitives
AUTH_SIG_RE = re.compile(
    r"\b(ecrecover|\.recover\s*\(|recoverSigner|bls[_A-Za-z]*[Vv]erify|"
    r"verifyReport|verifySignature|checkSignature|_verify)\b",
    re.IGNORECASE,
)
# an authorized-signer gate (allowlist / role / onlyOracle)
AUTH_GATE_RE = re.compile(
    r"\b(authorized|isSigner|isOracle|allowedSigner|onlyOracle|onlyRelayer|"
    r"trustedSigner|signers\s*\[|whitelist(ed)?Signer)\b",
    re.IGNORECASE,
)
# (B) a report timestamp field being consumed
REPORT_TS_RE = re.compile(
    r"\b(reportTimestamp|report\.?time(stamp)?|publishTime|observationsTimestamp|"
    r"priceTimestamp|feedTimestamp|updatedAt|report\.ts|data\.timestamp|msg\.time)\b",
    re.IGNORECASE,
)
# (C) an UPPER-bound compare against block.timestamp (future-dated guard present -> safe)
#     reportTs <= block.timestamp   OR   reportTs > block.timestamp (then revert)
UPPER_BOUND_RE = re.compile(
    r"(\w*(timestamp|time|ts|publishtime|updatedat)\w*)\s*(<=|<|>|>=)\s*block\.timestamp"
    r"|block\.timestamp\s*(>=|>|<=|<)\s*(\w*(timestamp|time|ts|publishtime|updatedat)\w*)",
    re.IGNORECASE,
)

FUNC_RE = re.compile(r"\bfunction\s+(\w+)\s*\(")

SKIP_SEGS = (os.sep + "node_modules", os.sep + ".git", os.sep + "lib" + os.sep, os.sep + "out")


def iter_sol_files(path):
    if os.path.isfile(path):
        if path.endswith(".sol"):
            yield path
        return
    for root, _dirs, files in os.walk(path):
        if any(seg in root for seg in SKIP_SEGS):
            continue
        for f in files:
            if f.endswith(".sol"):
                yield os.path.join(root, f)


def iter_functions(lines):
    """Yield (name, start_idx, end_idx) for each function via brace matching."""
    i = 0
    n = len(lines)
    while i < n:
        m = FUNC_RE.search(lines[i])
        if not m:
            i += 1
            continue
        name = m.group(1)
        depth = 0
        seen_brace = False
        j = i
        while j < n:
            depth += lines[j].count("{") - lines[j].count("}")
            if "{" in lines[j]:
                seen_brace = True
            if seen_brace and depth <= 0:
                break
            j += 1
        yield name, i, min(j, n - 1)
        i = j + 1


def scan_file(fp):
    findings = []
    try:
        with open(fp, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return findings

    for name, s, e in iter_functions(lines):
        blob = "".join(lines[s:e + 1])
        has_auth_sig = bool(AUTH_SIG_RE.search(blob))
        has_auth_gate = bool(AUTH_GATE_RE.search(blob))
        has_report_ts = bool(REPORT_TS_RE.search(blob))
        has_upper_bound = bool(UPPER_BOUND_RE.search(blob))

        # need signer auth (sig OR gate) AND a report timestamp being consumed
        if not (has_auth_sig or has_auth_gate):
            continue
        if not has_report_ts:
            continue

        score = 0
        reasons = []
        if has_auth_sig:
            score += 1
            reasons.append("signer recovery/verify present")
        if has_auth_gate:
            score += 1
            reasons.append("authorized-signer gate present")
        if has_report_ts:
            score += 1
            reasons.append("consumes a report timestamp field")
        if has_upper_bound:
            reasons.append("HAS an upper-bound timestamp compare vs block.timestamp -> likely SAFE (informational)")
        else:
            score += 2
            reasons.append("NO `reportTs <= block.timestamp` upper-bound -> future-dated report accepted (Ostium shape)")

        # only interesting if the upper bound is MISSING
        if has_upper_bound:
            continue

        findings.append({
            "file": fp,
            "line": s + 1,
            "function": name,
            "risk": score,
            "reasons": reasons,
        })
    return findings


def main():
    ap = argparse.ArgumentParser(description="future-dated oracle report-timestamp triage scanner (Cat 5.14)")
    ap.add_argument("path", help="Solidity source dir (recursed) or single .sol file")
    ap.add_argument("--json", dest="json_out", help="write findings to JSON file")
    ap.add_argument("--all", action="store_true", help="list every candidate (default: risk>=3)")
    args = ap.parse_args()

    if not os.path.exists(args.path):
        print("path not found: %s" % args.path, file=sys.stderr)
        return 2

    all_findings = []
    for fp in iter_sol_files(args.path):
        all_findings.extend(scan_file(fp))

    threshold = 0 if args.all else 3
    shown = [f for f in all_findings if f["risk"] >= threshold]
    shown.sort(key=lambda f: (-f["risk"], f["file"], f["line"]))

    print("oracle report-timestamp bound scan (Cat 5.14): %d signed-report verifiers missing a future-dated guard"
          % len(all_findings))
    print("Manual question per site: is the report timestamp bounded on BOTH sides (not just 'too old'),")
    print("and is the price sanity-banded vs the previous value? -> Ostium future-dated class.")
    print("-" * 72)
    for f in shown:
        print("[risk %d] %s:%d in %s()" % (f["risk"], f["file"], f["line"], f["function"]))
        print("    why: %s" % "; ".join(f["reasons"]))

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(all_findings, fh, indent=2)
        print("-" * 72)
        print("wrote %d findings -> %s" % (len(all_findings), args.json_out))

    return 0


if __name__ == "__main__":
    sys.exit(main())
