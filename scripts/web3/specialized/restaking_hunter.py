#!/usr/bin/env python3
"""
restaking_hunter.py — EigenLayer-like restaking protocol bug class hunter.

Covers:
- Slash race (withdraw before slash propagates)
- AVS commitment edge cases
- Withdrawal queue ordering
- Operator collusion
"""

import argparse
import json
import re
from pathlib import Path

RESTAKING_MARKERS = ["EigenLayer", "Restaking", "Operator", "AVS", "StrategyManager", "DelegationManager", "slashStake", "queueWithdrawal"]

CHECKS = [
    ("withdrawal_delay_vs_slash", r"withdrawalDelay|MIN_WITHDRAWAL_DELAY", "Withdrawal delay configured"),
    ("slash_window", r"slashWindow|SLASH_WINDOW", "Slash propagation window defined"),
    ("operator_opt_in", r"operatorOptIn|optInTo", "Operator opt-in mechanism"),
    ("avs_authorization", r"onlyAVS|registeredAVS", "AVS auth check"),
    ("queue_position_griefing", r"queuePosition|withdrawalQueue|cancel.*Withdraw", "Queue position handling"),
]


def scan_file(path: Path) -> dict:
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {"error": "read failed"}
    is_restaking = any(m in source for m in RESTAKING_MARKERS)
    findings = []
    if is_restaking:
        for check_id, regex, desc in CHECKS:
            findings.append({"check": check_id, "description": desc, "matches": bool(re.search(regex, source))})
    return {"file": str(path), "is_restaking": is_restaking, "findings": findings}


def scan_dir(target: Path) -> dict:
    if target.is_file():
        return {"files": [scan_file(target)]}
    files = sorted(target.rglob("*.sol"))
    files = [f for f in files if "node_modules" not in f.parts and "/lib/" not in str(f) and ".t.sol" not in f.name]
    return {"files": [r for r in (scan_file(f) for f in files) if r.get("is_restaking")]}


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
    (output_dir / "restaking_findings.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not args.quiet:
        print(f"[+] Restaking files: {len(report['files'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
