#!/usr/bin/env python3
"""
lending_hunter.py — Lending protocol bug class hunter.

Covers:
- Liquidation incentive math (Euler 2023 pattern)
- Interest rate model edge cases (utilization extremes)
- Bad debt absorption
- Collateral oracle manipulation
- Flash-loan repayment race
"""

import argparse
import json
import re
from pathlib import Path

LENDING_MARKERS = ["LendingPool", "IPool", "Comptroller", "CToken", "borrow", "liquidationCall", "_repay"]

LENDING_RISKS = [
    ("liquidation_bonus_unbounded", r"liquidationBonus|liquidation_incentive", "Verify liquidation bonus bounded"),
    ("utilization_explode", r"interestRate.*utilization|util.*\*\*", "Interest model at high utilization"),
    ("bad_debt_absorption", r"badDebt|deficit|sharedLoss", "Bad debt handling mechanism present"),
    ("oracle_for_collateral", r"oracle.*price|getAssetPrice|chainlink", "Collateral oracle source verified"),
    ("flashloan_repay_race", r"flashLoan.*\(.*\).*\{[^}]{0,200}_repay", "Flash-loan repayment within tx"),
    ("ltv_check_at_use", r"healthFactor|ltvCheck|collateralFactor", "LTV check at use vs at borrow"),
    ("sequencer_uptime_check", r"sequencerUptimeFeed|L2SequencerUptimeFeed|0xFdB631F5EE196F0ed6FAa767959853A9F217697D", "L2 sequencer uptime check"),
]


def scan_file(path: Path) -> dict:
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {"error": "read failed"}
    is_lending = any(m in source for m in LENDING_MARKERS)
    findings = []
    if is_lending:
        for check_id, regex, desc in LENDING_RISKS:
            present = bool(re.search(regex, source, re.IGNORECASE))
            findings.append({
                "check": check_id,
                "description": desc,
                "present": present,
                "severity": "High" if check_id in ("bad_debt_absorption", "sequencer_uptime_check") else "Medium",
            })
    return {"file": str(path), "is_lending": is_lending, "findings": findings}


def scan_dir(target: Path) -> dict:
    if target.is_file():
        return {"files": [scan_file(target)]}
    files = sorted(target.rglob("*.sol"))
    files = [f for f in files if "node_modules" not in f.parts and "/lib/" not in str(f) and ".t.sol" not in f.name]
    return {"files": [scan_file(f) for f in files if scan_file(f).get("is_lending")]}


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
    (output_dir / "lending_findings.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not args.quiet:
        print(f"[+] Lending files: {len(report['files'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
