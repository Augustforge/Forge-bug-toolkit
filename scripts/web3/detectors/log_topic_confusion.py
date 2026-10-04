#!/usr/bin/env python3
"""
log_topic_confusion.py — standalone Go/Rust scanner for Ethereum event/log type confusion.

NOT a Slither detector (these are Go/Rust off-chain listeners, not Solidity). Standalone,
like halo2_underconstraint.py.

CLASS (asymmetric.re "Ethereum Log Confusion: Polygon Heimdall", consensus takeover):
A bridge/sidechain listener decodes an Ethereum log into a struct via `UnpackLog(out, "Event", log)`
WITHOUT first verifying `log.Topics[0] == keccak256("Event(...)")`. Two events with the same
number of indexed args are structurally identical → `UnpackLog` happily decodes a `SignerChange`
log as a `StakeUpdate`, so a 20-byte address field is read as a uint256 stake amount → trillions of
fake stake → consensus supermajority. Heimdall: ~$2B bridge at risk.

DETECTION SIGNAL: a `UnpackLog(` (go-ethereum bound-contract style) or manual log decode where the
enclosing function does NOT compare `Topics[0]` to the expected event id (`abi.Events[...].ID`,
`crypto.Keccak256Hash`, `event.ID`). abigen Filter*/Watch* helpers DO check the topic internally —
those are safe; the danger is hand-rolled `UnpackLog` on a raw/arbitrary log.

Heuristic triage aid — flag → manual check: "is Topics[0] verified before this decode?"

Usage: py -3 -X utf8 log_topic_confusion.py <src-dir|file> [--json out.json] [--all]
"""
import argparse
import json
import os
import re
import sys

UNPACK_RE = re.compile(r"\b\w*\.?UnpackLog\s*\(|\bUnpackIntoInterface\s*\(")
# Evidence the function verifies the topic (mitigation).
TOPIC_CHECK_RE = re.compile(
    r"Topics\s*\[\s*0\s*\]|\.ID\b|Keccak256Hash|abi\.Events\[|EventByID|SigHash|crypto\.Keccak256"
)
FUNC_RE = re.compile(r"func\s+(?:\([^)]*\)\s*)?(\w+)\s*\(", re.MULTILINE)
WINDOW = 40  # lines around the UnpackLog to look for a topic check


def iter_src(path):
    if os.path.isfile(path):
        if path.endswith((".go", ".rs")):
            yield path
        return
    for root, _d, files in os.walk(path):
        if any(s in root for s in (os.sep + "vendor", os.sep + ".git", os.sep + "node_modules")):
            continue
        for f in files:
            if f.endswith((".go", ".rs")):
                yield os.path.join(root, f)


def scan_file(fp):
    try:
        with open(fp, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return []
    findings = []
    for i, line in enumerate(lines):
        if not UNPACK_RE.search(line):
            continue
        lo, hi = max(0, i - WINDOW), min(len(lines), i + WINDOW + 1)
        ctx = "".join(lines[lo:hi])
        has_topic_check = bool(TOPIC_CHECK_RE.search(ctx))
        risk = 1 if has_topic_check else 2
        findings.append({
            "file": fp, "line": i + 1, "risk": risk,
            "code": line.strip(),
            "topic_check_nearby": has_topic_check,
            "reason": "Topics[0]/event-ID check found in window (likely safe)" if has_topic_check
                      else "no Topics[0]/event-ID verification near UnpackLog → type-confusion candidate",
        })
    return findings


def main():
    ap = argparse.ArgumentParser(description="Ethereum log/event topic-confusion scanner (Go/Rust)")
    ap.add_argument("path")
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--all", action="store_true", help="show even topic-checked sites")
    args = ap.parse_args()
    if not os.path.exists(args.path):
        print("path not found: %s" % args.path, file=sys.stderr)
        return 2

    found = []
    for fp in iter_src(args.path):
        found.extend(scan_file(fp))
    shown = found if args.all else [f for f in found if f["risk"] >= 2]
    shown.sort(key=lambda f: (-f["risk"], f["file"], f["line"]))

    print("log topic-confusion scan: %d UnpackLog sites, %d flagged (no topic check)"
          % (len(found), len([f for f in found if f["risk"] >= 2])))
    print("Manual check per flag: is log.Topics[0] verified == keccak(EventSig) before decode?")
    print("-" * 72)
    for f in shown:
        print("[risk %d] %s:%d" % (f["risk"], f["file"], f["line"]))
        print("    %s" % f["code"])
        print("    why: %s" % f["reason"])

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(found, fh, indent=2)
        print("-" * 72)
        print("wrote %d findings -> %s" % (len(found), args.json_out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
