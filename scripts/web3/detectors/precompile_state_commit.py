#!/usr/bin/env python3
"""
precompile_state_commit.py — standalone Go scanner for EVM-on-Cosmos premature state-commit.

NOT a Slither detector (this is Go chain code, not Solidity). Standalone, like halo2_underconstraint.py.

CLASS (asymmetric.re "Evmos Precompile State Commit Infinite Mint", Critical):
A custom precompile (Cosmos-EVM hybrid: Evmos/Berachain/dYdX-class) calls `StateDB.Commit()` /
`CommitStateDB` DURING execution, mid-transaction. That flushes the in-memory cache to permanent
storage AND clears `journal.dirties`. A later `revert` rolls back the in-memory `stateObjects`,
but the already-committed object survives in permanent storage and is no longer tracked as dirty,
so the final Commit doesn't remove it. Net: A→B→A duplication; repeat for unbounded mint.

INVARIANT: `StateDB.Commit()` must be called exactly once, at end-of-tx — NEVER inside a precompile.

DETECTION SIGNAL: a `.Commit(` on a StateDB-like receiver inside a precompile execution path
(file under .../precompiles/..., or a method named Run/RunNativeAction implementing the precompile
interface), and NOT in an EndBlock / post-tx / Finalize context.

Heuristic triage aid — flag → manual check: "is this Commit() inside a precompile Run path?"

Usage: py -3 -X utf8 precompile_state_commit.py <src-dir|file> [--json out.json] [--all]
"""
import argparse
import json
import os
import re
import sys

COMMIT_RE = re.compile(r"\b(\w*[Ss]tateDB|stateDB|k\.\w+|\w+)\.Commit\s*\(|CommitStateDB\s*\(")
PRECOMPILE_PATH = re.compile(r"precompile", re.IGNORECASE)
PRECOMPILE_FUNC = re.compile(r"func\s+\([^)]*\)\s+(Run|RunNativeAction|Execute)\s*\(")
# contexts where a commit is legitimate (mitigation / not-a-precompile)
SAFE_CONTEXT = re.compile(r"EndBlock|Finalize|PostTxProcessing|BeginBlock|abci", re.IGNORECASE)


def iter_go(path):
    if os.path.isfile(path):
        if path.endswith(".go"):
            yield path
        return
    for root, _d, files in os.walk(path):
        if any(s in root for s in (os.sep + "vendor", os.sep + ".git")):
            continue
        for f in files:
            if f.endswith(".go"):
                yield os.path.join(root, f)


def scan_file(fp):
    try:
        with open(fp, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
            lines = text.splitlines()
    except OSError:
        return []
    in_precompile_path = bool(PRECOMPILE_PATH.search(fp))
    has_precompile_func = bool(PRECOMPILE_FUNC.search(text))
    findings = []
    for i, line in enumerate(lines):
        if not COMMIT_RE.search(line):
            continue
        lo, hi = max(0, i - 25), min(len(lines), i + 25)
        ctx = "\n".join(lines[lo:hi])
        if SAFE_CONTEXT.search(ctx):
            continue  # commit in EndBlock/Finalize = legitimate
        risk = 0
        reasons = []
        if in_precompile_path:
            risk += 2
            reasons.append("file is in a precompile path")
        if has_precompile_func:
            risk += 1
            reasons.append("file implements a precompile Run()/Execute()")
        if risk == 0:
            reasons.append("StateDB.Commit outside precompile/EndBlock context (review)")
        findings.append({
            "file": fp, "line": i + 1, "risk": risk,
            "code": line.strip(), "reasons": reasons,
        })
    return findings


def main():
    ap = argparse.ArgumentParser(description="EVM-on-Cosmos precompile premature state-commit scanner")
    ap.add_argument("path")
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--all", action="store_true", help="show every StateDB.Commit site")
    args = ap.parse_args()
    if not os.path.exists(args.path):
        print("path not found: %s" % args.path, file=sys.stderr)
        return 2

    found = []
    for fp in iter_go(args.path):
        found.extend(scan_file(fp))
    shown = found if args.all else [f for f in found if f["risk"] >= 1]
    shown.sort(key=lambda f: (-f["risk"], f["file"], f["line"]))

    print("precompile state-commit scan: %d StateDB.Commit sites, %d flagged (precompile path, not EndBlock)"
          % (len(found), len([f for f in found if f["risk"] >= 1])))
    print("Manual check: is this Commit() inside a precompile Run path (mid-tx)? -> A->B->A infinite-mint risk")
    print("-" * 72)
    for f in shown:
        print("[risk %d] %s:%d" % (f["risk"], f["file"], f["line"]))
        print("    %s" % f["code"])
        print("    why: %s" % "; ".join(f["reasons"]))

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(found, fh, indent=2)
        print("-" * 72)
        print("wrote %d findings -> %s" % (len(found), args.json_out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
