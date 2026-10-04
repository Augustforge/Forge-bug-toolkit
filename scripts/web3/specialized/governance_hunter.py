#!/usr/bin/env python3
"""
governance_hunter.py — Governance protocol bug class hunter.

Covers:
- Quorum manipulation (snapshot timing, vote inflation)
- Proposal stuffing
- Timelock bypass
- Upgrade path attacks
- Delegate griefing
"""

import argparse
import json
import re
from pathlib import Path

GOV_MARKERS = ["Governor", "TimelockController", "propose", "castVote", "delegate", "Quorum"]

GOV_CHECKS = [
    ("snapshot_timing", r"snapshot.*block\.number\s*[+-]", "Snapshot at proposal time vs vote time"),
    ("quorum_calc", r"quorum.*=\s*\(.*totalSupply", "Quorum derived from current supply (manipulatable)"),
    ("timelock_min_delay", r"MIN_DELAY|minDelay|TIMELOCK_DELAY", "Minimum timelock delay defined"),
    ("delegate_recursion", r"function\s+delegate.*\(.*delegatee.*\).*self", "Self-delegation handled"),
    ("flash_vote", r"getVotes.*timestamp|votingPower", "Vote weight at snapshot, not current block"),
    ("proposal_threshold", r"proposalThreshold", "Proposal threshold > 0"),
    ("upgrade_via_proposal", r"upgradeToAndCall|_authorizeUpgrade", "Upgrade auth path"),
]


def scan_file(path: Path) -> dict:
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {"error": "read failed"}
    is_gov = any(m in source for m in GOV_MARKERS)
    findings = []
    if is_gov:
        for check_id, regex, desc in GOV_CHECKS:
            findings.append({
                "check": check_id,
                "description": desc,
                "matches": bool(re.search(regex, source, re.IGNORECASE)),
            })
    return {"file": str(path), "is_governance": is_gov, "findings": findings}


def scan_dir(target: Path) -> dict:
    if target.is_file():
        return {"files": [scan_file(target)]}
    files = sorted(target.rglob("*.sol"))
    files = [f for f in files if "node_modules" not in f.parts and "/lib/" not in str(f) and ".t.sol" not in f.name]
    results = []
    for f in files:
        r = scan_file(f)
        if r.get("is_governance"):
            results.append(r)
    return {"files": results}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--target", required=True)
    p.add_argument("--output", default=".")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()
    target = Path(args.target)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    report = scan_dir(target)
    (output_dir / "governance_findings.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not args.quiet:
        print(f"[+] Governance files: {len(report['files'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
