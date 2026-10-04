#!/usr/bin/env python3
"""
Per-block idempotency-guard staleness detector (standalone Solidity source scanner).

NOT a Slither detector — this is a grep-grade heuristic triage aid for taxonomy class
9.6. It surfaces accounting-sync functions (`_checkpoint`, `_update`, `_sync`, `_accrue`)
that SKIP when already run in the current block (a gas optimization), for the manual
question:

    "Can an attacker trigger this sync FIRST (snapshotting the old value), then change
     the underlying real balance in the SAME block, so that a downstream
     (realBalance - recordedSupply) delta is read while the snapshot is stale?"

If yes -> candidate stale-accounting bug (attacker is credited the unrecorded growth).
This is the Tranchess 2026 class (chainsiren, $200K bounty, ~$95M at risk):

    function _checkpoint() private {
        if (lastCheckpoint >= block.timestamp) return;   // <-- per-block skip
        recordedSupply = actualBalance;
    }
    // attacker, one block: _checkpoint(); <rebalance mints Q to contract>; deposit();
    // deposit(): spareAmount = actualBalance - recordedSupply;  // inflated -> free shares

The detector flags two signals and ranks by their co-occurrence:
  (A) a per-block dedup guard with an early return  (the skip)
  (B) a downstream `(liveBalance - recordedValue)` subtraction in the same file (the sink)

A site with BOTH is the high-risk Tranchess shape. This tool does NOT prove a bug —
every flag needs the manual "can I order ops so the snapshot is stale?" check.

See: bug-bounty-toolkit/methodology/hypothesis_taxonomy.md Cat 9.6.

Usage:
    py -3 -X utf8 checkpoint_staleness.py <path-to-sol-src> [--json out.json] [--all]

    <path>   directory (recursed) or single .sol file
    --json   also write structured findings to a JSON file
    --all    list every guard site (default: only risk >= 1)
"""

import argparse
import json
import os
import re
import sys

# (A) Per-block dedup guard: a state var compared to block.timestamp / block.number,
#     in either operand order. The early-return is checked separately on the line(s).
GUARD_RE = re.compile(
    r"\b(\w+)\s*(>=|==|>|<=|<)\s*block\.(timestamp|number)\b"
    r"|block\.(timestamp|number)\s*(>=|==|>|<=|<)\s*(\w+)\b"
)
RETURN_RE = re.compile(r"\breturn\b")

# Guard variable names that strongly imply a checkpoint/sync snapshot.
GUARD_NAME_HINTS = (
    "lastcheckpoint", "lastupdate", "lastsync", "lastaccrue", "lastrebalance",
    "lasttime", "lastblock", "checkpointtimestamp", "lastsettle", "lastharvest",
)

# Function-name hints that this is the accounting-sync path.
SYNC_FUNC_HINTS = (
    "checkpoint", "_update", "_sync", "sync", "_accrue", "accrue", "refresh",
    "rebalance", "settle", "_settle", "poke",
)

# (B) Downstream delta sink: a live balance MINUS a recorded/stored supply (or vice
#     versa via balanceOf). Either explicit names or balanceOf(this) - X.
DELTA_RE = re.compile(
    r"(actualbalance|realbalance|balanceof\s*\(\s*address\s*\(\s*this\s*\)\s*\)|"
    r"balanceof\s*\(\s*this\s*\))\s*-\s*\w+"
    r"|\w+\s*-\s*(recordedsupply|storedsupply|totalsupply|_totalsupply|"
    r"recordedbalance|trackedbalance|lastrecorded)",
    re.IGNORECASE,
)

WINDOW = 3  # lines after a guard comparison to look for the early `return`


def iter_sol_files(path):
    if os.path.isfile(path):
        if path.endswith(".sol"):
            yield path
        return
    for root, _dirs, files in os.walk(path):
        if any(seg in root for seg in (os.sep + "node_modules", os.sep + ".git",
                                       os.sep + "lib" + os.sep, os.sep + "out")):
            continue
        for f in files:
            if f.endswith(".sol"):
                yield os.path.join(root, f)


def guard_var(line):
    """Return the state-var name compared against block.timestamp/number, if any."""
    m = GUARD_RE.search(line)
    if not m:
        return None
    return m.group(1) or m.group(6)


def file_has_delta_sink(lines):
    for i, ln in enumerate(lines):
        if DELTA_RE.search(ln):
            return i + 1
    return None


def enclosing_func_name(lines, idx):
    """Walk upward to the nearest `function NAME(` declaration."""
    for j in range(idx, max(0, idx - 60), -1):
        m = re.search(r"\bfunction\s+(\w+)", lines[j])
        if m:
            return m.group(1)
    return None


def score_site(var, func_name, has_return, delta_line):
    score = 0
    reasons = []
    if has_return:
        score += 1
        reasons.append("per-block guard with early return")
    else:
        reasons.append("block.timestamp/number compare (no early return nearby — weaker)")
    v = (var or "").lower()
    f = (func_name or "").lower()
    if any(h in v for h in GUARD_NAME_HINTS) or any(h in f for h in SYNC_FUNC_HINTS):
        score += 1
        reasons.append("checkpoint/sync-shaped (var or function name)")
    if delta_line:
        score += 1
        reasons.append("file has (liveBalance - recordedSupply) delta sink @L%d" % delta_line)
    return score, reasons


def scan_file(fp):
    findings = []
    try:
        with open(fp, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return findings

    delta_line = file_has_delta_sink(lines)

    for i, line in enumerate(lines):
        var = guard_var(line)
        if not var:
            continue
        # must look like an `if (... ) return` block, not arbitrary arithmetic
        if "if" not in line.lower():
            continue
        window_blob = "".join(lines[i:min(len(lines), i + WINDOW + 1)])
        has_return = bool(RETURN_RE.search(line) or RETURN_RE.search(window_blob))
        func_name = enclosing_func_name(lines, i)
        score, reasons = score_site(var, func_name, has_return, delta_line)
        findings.append({
            "file": fp,
            "line": i + 1,
            "guard_var": var,
            "function": func_name,
            "code": line.strip(),
            "delta_sink_line": delta_line,
            "risk": score,
            "reasons": reasons,
        })
    return findings


def main():
    ap = argparse.ArgumentParser(description="per-block checkpoint-staleness triage scanner (Cat 9.6)")
    ap.add_argument("path", help="Solidity source dir (recursed) or single .sol file")
    ap.add_argument("--json", dest="json_out", help="write findings to JSON file")
    ap.add_argument("--all", action="store_true", help="list every guard site (default: risk>=1)")
    args = ap.parse_args()

    if not os.path.exists(args.path):
        print("path not found: %s" % args.path, file=sys.stderr)
        return 2

    all_findings = []
    for fp in iter_sol_files(args.path):
        all_findings.extend(scan_file(fp))

    flagged = [f for f in all_findings if f["risk"] >= 1]
    shown = all_findings if args.all else flagged
    shown.sort(key=lambda f: (-f["risk"], f["file"], f["line"]))

    print("checkpoint-staleness scan (Cat 9.6): %d per-block guards, %d flagged (risk>=1)"
          % (len(all_findings), len(flagged)))
    print("Manual question per site: can an attacker run the sync first, change the real")
    print("balance same-block, then read a stale (balance - recorded) delta? -> Tranchess class.")
    print("-" * 72)
    for f in shown:
        fn = (" in %s()" % f["function"]) if f["function"] else ""
        print("[risk %d] %s:%d%s" % (f["risk"], f["file"], f["line"], fn))
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
