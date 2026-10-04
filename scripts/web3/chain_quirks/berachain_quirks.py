#!/usr/bin/env python3
"""
berachain_quirks.py — Berachain Proof-of-Liquidity-specific bug class hunter.

Berachain quirks:
- BGT (Bera Governance Token) — non-transferable until burned for BERA
- Gauge weight voting via BGT
- PoL rewards split between protocol/validator/depositor
- Liquidity-as-security model

Bug classes:
- Gauge weight manipulation
- BGT burn race conditions
- PoL reward calculation drift
- Validator commission gaming
"""

import argparse
import json
import re
from pathlib import Path


CHECKS = [
    ("bgt_burn_race", r"burnBGT|redeemBGT|burnForBERA", "BGT burn — verify atomic with claim"),
    ("gauge_weight_manipulation", r"gaugeWeight|voteForGauge|setGaugeWeight", "Gauge voting — check flash-vote protection"),
    ("pol_reward_calc", r"polReward|pol_reward|proofOfLiquidity", "PoL reward distribution — check splits"),
    ("validator_commission", r"validatorCommission|commissionRate", "Validator commission — settable bounds"),
    ("bgt_transferability", r"BGT.*transfer|approve.*BGT", "BGT is non-transferable; check approve handling"),
]


def scan_file(path: Path) -> dict:
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {"error": "read failed"}
    findings = []
    for check_id, regex, desc in CHECKS:
        if re.search(regex, source, re.IGNORECASE):
            findings.append({"check": check_id, "description": desc})
    return {"file": str(path), "findings": findings}


def scan_dir(target: Path) -> dict:
    if target.is_file():
        return {"files": [scan_file(target)]}
    files = sorted(target.rglob("*.sol"))
    files = [f for f in files if "node_modules" not in f.parts and "/lib/" not in str(f) and ".t.sol" not in f.name]
    return {"files": [r for r in (scan_file(f) for f in files) if r.get("findings")]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--target", required=True)
    p.add_argument("--output", default=".")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    report = scan_dir(Path(args.target))
    (output_dir / "berachain_quirks.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    total = sum(len(f.get("findings", [])) for f in report["files"])
    if not args.quiet:
        print(f"[+] Berachain findings: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
