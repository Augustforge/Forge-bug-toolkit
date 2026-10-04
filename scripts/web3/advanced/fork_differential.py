#!/usr/bin/env python3
"""
fork_differential.py — diff a protocol against its upstream fork.

Use case: target forks Compound/Aave/Uniswap. The custom edits are bug-rich.
Heuristic: for each .sol file with matching name in both trees, hash + line-diff.
Output: modified files ranked by # of edits / risk-keyword density.
"""
import argparse
import difflib
import hashlib
import json
import re
import sys
from pathlib import Path


RISK_KEYWORDS = ["transfer", "balance", "owner", "admin", "approve", "permit", "delegatecall",
                 "selfdestruct", "assembly", "tx.origin", "block.timestamp", "ecrecover"]


def file_hash(p: Path) -> str:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    except Exception:
        return ""


def risk_score(diff_lines: list) -> int:
    score = 0
    for line in diff_lines:
        if not line.startswith(("+", "-")):
            continue
        for kw in RISK_KEYWORDS:
            if kw in line:
                score += 2
        if re.search(r"\bonly\w+\b", line):
            score += 3
        if re.search(r"\.call\s*\{", line):
            score += 4
    return score


def diff_pair(left: Path, right: Path) -> dict:
    try:
        lleft = left.read_text(encoding="utf-8", errors="ignore").splitlines()
        lright = right.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return {}
    diff = list(difflib.unified_diff(lleft, lright, lineterm="", n=0))
    if not diff:
        return {}
    added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
    return {
        "added_lines": added,
        "removed_lines": removed,
        "risk_score": risk_score(diff),
        "diff_sample": diff[:30],
    }


def main():
    ap = argparse.ArgumentParser(description="Differential analysis vs upstream fork")
    ap.add_argument("--target", required=True, help="Target protocol dir")
    ap.add_argument("--upstream", required=True, help="Upstream fork dir")
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    tgt = Path(args.target)
    ups = Path(args.upstream)
    if not (tgt.is_dir() and ups.is_dir()):
        print("[!] Both --target and --upstream must be dirs", file=sys.stderr)
        sys.exit(1)

    target_files = {p.name: p for p in tgt.rglob("*.sol")}
    upstream_files = {p.name: p for p in ups.rglob("*.sol")}

    common = sorted(set(target_files) & set(upstream_files))
    diffs = []
    for name in common:
        d = diff_pair(upstream_files[name], target_files[name])
        if d:
            d["file"] = name
            diffs.append(d)

    diffs.sort(key=lambda x: x["risk_score"], reverse=True)
    target_only = sorted(set(target_files) - set(upstream_files))

    if not args.quiet:
        print(f"[+] Common files: {len(common)}")
        print(f"[+] Modified: {len(diffs)}")
        print(f"[+] Target-only (custom): {len(target_only)}")
        print("\nTop modified by risk-keyword density:")
        for d in diffs[:15]:
            print(f"  risk={d['risk_score']:3}  +{d['added_lines']}/-{d['removed_lines']}  {d['file']}")
        if target_only:
            print(f"\nCustom additions (top 10):")
            for n in target_only[:10]:
                print(f"  {n}")

    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "fork_diff.json").write_text(json.dumps({
            "modified": diffs,
            "target_only": target_only,
        }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
