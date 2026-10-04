#!/usr/bin/env python3
"""
hyper_evm_quirks.py — HyperEVM-specific bug class hunter.

HyperEVM quirks:
- L1 ↔ HyperEVM bridge mechanics
- HypePerps / HyperCore integration
- Native HYPE token transfers via L1 spot
- Oracle peculiarities (depends on HyperLiquid feed)

Bug classes:
- L1↔EVM cross-chain timing
- Bridge replay (native vs ERC-20 sides)
- HyperLiquid oracle staleness on EVM side
"""

import argparse
import json
import re
from pathlib import Path


CHECKS = [
    ("l1_evm_bridge", r"L1Read|L1Write|hyperBridge|spotBridge", "L1↔EVM bridge mechanic"),
    ("hype_native_transfer", r"HYPE.*native|nativeTransfer.*HYPE", "Native HYPE handling"),
    ("hyperliquid_oracle", r"HyperLiquid.*oracle|hyperOracle|HyperPriceFeed", "HyperLiquid-derived oracle"),
    ("perp_integration", r"HypePerps|HyperCore.*Perp|perpetual.*Hyper", "Perp integration — check unit conversions"),
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
    (output_dir / "hyper_evm_quirks.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    total = sum(len(f.get("findings", [])) for f in report["files"])
    if not args.quiet:
        print(f"[+] HyperEVM findings: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
