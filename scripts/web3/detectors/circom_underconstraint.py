#!/usr/bin/env python3
"""
Circom under-constrained signal detector (standalone .circom source scanner).

Sibling of halo2_underconstraint.py, but for the R1CS / Circom family (taxonomy Cat 14.7).
Where halo2's sink is `assign_advice()` without `copy_advice()`, Circom's sink is the
`<--` operator: it ASSIGNS a witness signal but adds NO constraint. Only `<==` (assign +
constrain) and `===` (constrain) bind a signal into the R1CS. A signal written with `<--`
and never constrained by a matching `<==` / `===` is free for a malicious prover to choose
-> the circuit proves a false statement (soundness bug).

    Manual question per site: "is the signal written by `<--` ALSO constrained somewhere
    (a `<==` or `=== ` involving it)? If not, the prover can set it to anything." If free
    -> candidate under-constraint.

Common safe idiom (NOT a bug): `x <-- a / b;` immediately followed by `x * b === a;` — the
`<--` computes the witness, the `===` constrains it. The detector looks for a constraining
reference to the SAME signal name within a window; absence raises risk.

Also flags (separately, in .sol files) the **proof-malleability / proof-as-nullifier**
anti-pattern: using `keccak256(proof)` (or the raw proof bytes) as a uniqueness/replay key,
which a malleable proof system bypasses — the nullifier must key on the public nullifier
signal, not the proof. (Cat 14.7 second half.)

This is grep-grade triage, NOT proof. False positives expected — every flagged site needs
the manual "is this signal otherwise constrained?" check.

Usage:
    py -3 -X utf8 circom_underconstraint.py <path> [--json out.json] [--all]

    <path>   directory (recursed) or single .circom / .sol file
    --json   also write structured findings to a JSON file
    --all    list every <-- site (default: only risk >= 1)

See: methodology/hypothesis_taxonomy.md Cat 14.7; memory project_zcash_orchard_halo2 (halo2 kin).
"""

import argparse
import json
import os
import re
import sys

# `<--` assigns a witness WITHOUT a constraint. `<==` and `===` DO constrain.
# Match `<--` but NOT `<-->` (rare) and NOT inside `<==`.
NONCONSTRAINING = re.compile(r"(?<![<=])<--(?!-)")
# A constraining operator referencing a signal: `<==` (assign+constrain) or `===` (constrain).
CONSTRAINING = re.compile(r"<==|===")

# Extract the LHS signal name from `sig <-- expr;` or `out[i] <-- expr;`
LHS_RE = re.compile(r"([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*<--")

# .sol proof-as-nullifier anti-pattern (Cat 14.7 second half).
PROOF_NULLIFIER = re.compile(
    r"(keccak256\s*\(\s*(?:abi\.encode\w*\s*\(\s*)?_?proof|"
    r"\b(used|seen|spent|nullifiers?)\s*\[\s*keccak256\s*\(\s*_?proof|"
    r"\bbytes32\s+\w*[Pp]roof[Hh]ash\s*=\s*keccak256)"
)

WINDOW = 6  # lines around a `<--` to look for a constraint on the same signal


def iter_src_files(path, exts):
    if os.path.isfile(path):
        if path.endswith(exts):
            yield path
        return
    for root, _dirs, files in os.walk(path):
        if any(seg in root for seg in (os.sep + "node_modules", os.sep + ".git",
                                       os.sep + "target", os.sep + "build")):
            continue
        for f in files:
            if f.endswith(exts):
                yield os.path.join(root, f)


def score_circom_site(lhs, window_blob):
    """Heuristic 0-3 risk for a `<--` site. Higher = review first."""
    score = 0
    reasons = []
    # Is the SAME signal constrained nearby (the safe `x <-- ...; x*b === a;` idiom)?
    constrained_here = False
    if lhs:
        # a `<==`/`===` line that mentions the signal name within the window
        if re.search(r"\b" + re.escape(lhs) + r"\b[^\n]*(<==|===)|(<==|===)[^\n]*\b" + re.escape(lhs) + r"\b",
                     window_blob):
            constrained_here = True
    if not constrained_here:
        score += 2
        reasons.append("no <== / === on this signal within window (free witness)")
    else:
        reasons.append("constraining op on same signal nearby (likely safe idiom)")
    # Hot sinks: output signals, things feeding comparisons/hashes/Merkle paths.
    ctx = window_blob.lower()
    if any(h in ctx for h in ("signal output", "out <", "root", "nullifier", "commitment",
                              "ismember", "merkle", "poseidon", "hash")):
        score += 1
        reasons.append("signal feeds output / nullifier / hash / merkle sink")
    return score, reasons


def scan_circom(fp):
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
        m = LHS_RE.search(line)
        lhs = m.group(1) if m else None
        score, reasons = score_circom_site(lhs, window_blob)
        findings.append({
            "file": fp, "line": i + 1, "kind": "circom_underconstraint",
            "signal": lhs, "code": line.strip(), "risk": score, "reasons": reasons,
        })
    return findings


def scan_sol_proof(fp):
    findings = []
    try:
        with open(fp, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return findings
    for i, line in enumerate(lines):
        if PROOF_NULLIFIER.search(line):
            findings.append({
                "file": fp, "line": i + 1, "kind": "proof_as_nullifier",
                "signal": None, "code": line.strip(), "risk": 2,
                "reasons": ["proof bytes used as uniqueness/replay key — malleable proof bypasses; "
                            "key on the public nullifier signal, not the proof"],
            })
    return findings


def main():
    ap = argparse.ArgumentParser(description="Circom under-constrained signal + proof-malleability triage scanner")
    ap.add_argument("path", help="source dir (recursed) or single .circom/.sol file")
    ap.add_argument("--json", dest="json_out", help="write findings to JSON file")
    ap.add_argument("--all", action="store_true", help="list every site (default: risk>=1)")
    args = ap.parse_args()

    if not os.path.exists(args.path):
        print("path not found: %s" % args.path, file=sys.stderr)
        return 2

    all_findings = []
    for fp in iter_src_files(args.path, (".circom",)):
        all_findings.extend(scan_circom(fp))
    for fp in iter_src_files(args.path, (".sol",)):
        all_findings.extend(scan_sol_proof(fp))

    shown = all_findings if args.all else [f for f in all_findings if f["risk"] >= 1]
    shown.sort(key=lambda f: (-f["risk"], f["file"], f["line"]))

    n_uc = len([f for f in all_findings if f["kind"] == "circom_underconstraint"])
    print("Circom under-constraint scan: %d `<--` sites, %d proof-nullifier sites, %d flagged (risk>=1)"
          % (n_uc, len(all_findings) - n_uc, len([f for f in all_findings if f["risk"] >= 1])))
    print("Manual question per `<--`: is this signal ALSO constrained (<== / ===)? If not -> soundness bug (Cat 14.7).")
    print("-" * 72)
    for f in shown:
        sig = (' "%s"' % f["signal"]) if f["signal"] else ""
        print("[risk %d] %s %s:%d%s" % (f["risk"], f["kind"], f["file"], f["line"], sig))
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
