#!/usr/bin/env python3
"""
halo2 under-constrained witness detector (standalone Rust source scanner).

NOT a Slither detector — halo2 circuits are Rust, not Solidity. This is a grep-grade
heuristic triage aid that surfaces `assign_advice()` (and similar non-constraining
assignment) call sites for the manual question:

    "Can this witness value be changed to anything other than what an honest prover
     assigns, WITHOUT violating any other circuit constraint?"

If yes -> candidate under-constraint (soundness bug). This is exactly the follow-up
sweep Taylor Hornby ran on halo2 after finding the Orchard counterfeiting vuln
(May 2026): a base point fed to the incomplete-addition stage of variable-base
scalar-mul was set via `assign_advice()` with no constraint binding it to the real
base, so a malicious prover could pick any base and forge [ivk]g_d = pk_d, enabling
double-spend / unbounded undetectable inflation. Fix was `assign_advice` -> `copy_advice`.

See: sessions/_methodology/learning_paths/zk.md (worked example),
memory project_zcash_orchard_halo2.

This tool does NOT prove a bug. It ranks call sites so a human (or AI agent) reviews
the highest-risk ones first. False positives are expected — every flagged site needs
the manual "is this value otherwise constrained?" check.

Usage:
    py -3 -X utf8 halo2_underconstraint.py <path-to-rust-src> [--json out.json] [--all]

    <path>   directory (recursed) or single .rs file
    --json   also write structured findings to a JSON file
    --all    list every assign_advice site (default: only risk >= 1)
"""

import argparse
import json
import os
import re
import sys

# Non-constraining assignment calls (assign a witness without generating a constraint
# tying it to a specific value). copy_advice / constrain_* DO generate constraints.
NONCONSTRAINING = re.compile(r"\b(assign_advice|assign_advice_from_instance|assign_fixed)\s*\(")
CONSTRAINING = re.compile(r"\b(copy_advice|constrain_equal|constrain_constant|assign_advice_from_constant)\b")

# The inline column label, e.g. region.assign_advice(|| "x_p", ...) -> "x_p"
LABEL_RE = re.compile(r"""assign_advice\w*\s*\(\s*\|\|\s*["']([^"']+)["']""")

# Context markers that raise suspicion: ECC / scalar-mul / point-coordinate territory,
# where an unconstrained witness is most likely to be soundness-critical.
HOT_CONTEXT = [
    "scalar_mul", "scalarmul", "double_and_add", "incomplete", "complete",
    "ecc", "/mul/", "var_base", "variable_base", "fixed_base", "endoscale",
]
# Witness names that, if assigned without a constraint, are classic soundness sinks:
# base/point coordinates, scalars, accumulators feeding an algebraic check.
HOT_NAMES = [
    "x_p", "y_p", "x_a", "y_a", "x_q", "y_q", "base", "point",
    "lambda", "acc", "z", "scalar", "k_", "running_sum",
]

# How many lines around a site to scan for a nearby constraining call (mitigation).
WINDOW = 8


def iter_rust_files(path):
    if os.path.isfile(path):
        if path.endswith(".rs"):
            yield path
        return
    for root, _dirs, files in os.walk(path):
        # skip vendored/build dirs
        if any(seg in root for seg in (os.sep + "target", os.sep + ".git")):
            continue
        for f in files:
            if f.endswith(".rs"):
                yield os.path.join(root, f)


def score_site(line, label, context_blob, has_nearby_constraint):
    """Heuristic 0-3 risk. Higher = review first. Honest: this is triage, not proof."""
    score = 0
    reasons = []
    ctx = context_blob.lower()
    if any(m in ctx for m in HOT_CONTEXT):
        score += 1
        reasons.append("ecc/scalar-mul context")
    name = (label or line).lower()
    if any(n in name for n in HOT_NAMES):
        score += 1
        reasons.append("witness name is a point/scalar sink")
    if not has_nearby_constraint:
        score += 1
        reasons.append("no copy_advice/constrain_* within window")
    else:
        reasons.append("constraining call nearby (likely mitigated)")
    return score, reasons


def scan_file(fp):
    findings = []
    try:
        with open(fp, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return findings

    for i, line in enumerate(lines):
        if not NONCONSTRAINING.search(line):
            continue
        lo = max(0, i - WINDOW)
        hi = min(len(lines), i + WINDOW + 1)
        window_blob = "".join(lines[lo:hi])
        has_nearby_constraint = bool(CONSTRAINING.search(window_blob))
        m = LABEL_RE.search(line)
        label = m.group(1) if m else None
        score, reasons = score_site(line, label, window_blob, has_nearby_constraint)
        findings.append({
            "file": fp,
            "line": i + 1,
            "label": label,
            "code": line.strip(),
            "risk": score,
            "reasons": reasons,
        })
    return findings


def main():
    ap = argparse.ArgumentParser(description="halo2 under-constrained witness triage scanner")
    ap.add_argument("path", help="Rust source dir (recursed) or single .rs file")
    ap.add_argument("--json", dest="json_out", help="write findings to JSON file")
    ap.add_argument("--all", action="store_true", help="list every site (default: risk>=1)")
    args = ap.parse_args()

    if not os.path.exists(args.path):
        print("path not found: %s" % args.path, file=sys.stderr)
        return 2

    all_findings = []
    for fp in iter_rust_files(args.path):
        all_findings.extend(scan_file(fp))

    shown = all_findings if args.all else [f for f in all_findings if f["risk"] >= 1]
    shown.sort(key=lambda f: (-f["risk"], f["file"], f["line"]))

    print("halo2 under-constraint scan: %d assign sites, %d flagged (risk>=1)"
          % (len(all_findings), len([f for f in all_findings if f["risk"] >= 1])))
    print("Manual question per site: can this witness be set to anything else without")
    print("violating another constraint? If yes -> soundness bug (Orchard class).")
    print("-" * 72)
    for f in shown:
        lbl = (' "%s"' % f["label"]) if f["label"] else ""
        print("[risk %d] %s:%d%s" % (f["risk"], f["file"], f["line"], lbl))
        print("    %s" % f["code"])
        print("    why: %s" % "; ".join(f["reasons"]))

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(all_findings, fh, indent=2)
        print("-" * 72)
        print("wrote %d findings -> %s" % (len(all_findings), args.json_out))

    return 0


if __name__ == "__main__":
    sys.exit(main())
