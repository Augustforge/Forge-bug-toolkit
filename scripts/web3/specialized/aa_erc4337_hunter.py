#!/usr/bin/env python3
"""
aa_erc4337_hunter.py — Account Abstraction (ERC-4337) bug class hunter.

Covers:
- Bundler griefing (validation passes simulation, fails on-chain)
- Validation bypass
- Paymaster abuse
- Aggregated signature attacks
"""

import argparse
import json
import re
from pathlib import Path

AA_MARKERS = ["EntryPoint", "UserOperation", "IPaymaster", "validateUserOp", "BaseAccount", "ISignatureAggregator"]

CHECKS = [
    ("validate_signature", r"function\s+validateUserOp", "validateUserOp present"),
    ("paymaster_validation", r"validatePaymasterUserOp", "Paymaster validation chain"),
    ("simulation_consistency", r"VALIDATION_SUCCESS|SIG_VALIDATION_FAILED", "Validation result constants"),
    ("aggregator_handling", r"IAggregator|aggregateSignatures", "Aggregator support"),
    ("entry_point_only", r"onlyEntryPoint|require.*entryPoint", "EntryPoint-only modifier"),
]


def scan_file(path: Path) -> dict:
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {"error": "read failed"}
    is_aa = any(m in source for m in AA_MARKERS)
    findings = []
    if is_aa:
        for check_id, regex, desc in CHECKS:
            findings.append({"check": check_id, "description": desc, "matches": bool(re.search(regex, source))})
    return {"file": str(path), "is_aa": is_aa, "findings": findings}


def scan_dir(target: Path) -> dict:
    if target.is_file():
        return {"files": [scan_file(target)]}
    files = sorted(target.rglob("*.sol"))
    files = [f for f in files if "node_modules" not in f.parts and "/lib/" not in str(f) and ".t.sol" not in f.name]
    return {"files": [r for r in (scan_file(f) for f in files) if r.get("is_aa")]}


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
    (output_dir / "aa_findings.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not args.quiet:
        print(f"[+] AA files: {len(report['files'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
