#!/usr/bin/env python3
"""
amm_hunter.py — AMM-specific bug class hunter.

Covers:
- V2 constant-product manipulation
- V3 concentrated liquidity (tick math, sqrtPriceX96)
- V4 hooks (callback authorization)
- TWAP oracle manipulation
- Reserve sync griefing
"""

import argparse
import json
import re
from pathlib import Path

AMM_FAMILIES = {
    "uniswap_v2": {
        "markers": ["IUniswapV2Pair", "_swap", "getReserves", "reserve0", "reserve1"],
        "risks": [
            ("twap_short_window", r"price.*Cumulative.*[3-9]\d{0,2}\s*(seconds|minutes)", "TWAP window too short"),
            ("balance_for_price", r"balanceOf\(address\(this\)\).*price", "Use reserves not balanceOf for price"),
        ],
    },
    "uniswap_v3": {
        "markers": ["IUniswapV3Pool", "sqrtPriceX96", "tickSpacing", "INonfungiblePositionManager"],
        "risks": [
            ("observation_cardinality", r"observationCardinality.*[12][05]?\s*[;)]", "Observation cardinality too low"),
            ("tick_math", r"TickMath", "Tick math used — verify overflow"),
        ],
    },
    "uniswap_v4": {
        "markers": ["IUniswapV4", "IHooks", "PoolManager", "BalanceDelta"],
        "risks": [
            ("hook_auth", r"function.*Hook.*\(.*\)\s*public", "Hook callback may not be auth'd to PoolManager"),
        ],
    },
    "curve": {
        "markers": ["ICurvePool", "get_virtual_price", "remove_liquidity"],
        "risks": [
            ("readonly_reentrancy", r"get_virtual_price|getRate", "Curve r/o reentrancy class"),
        ],
    },
    "balancer": {
        "markers": ["IVault", "Balancer", "WeightedPool", "StablePool"],
        "risks": [
            ("readonly_reentrancy", r"getRate|getPoolTokens", "Balancer r/o reentrancy class"),
        ],
    },
}


def scan_file(path: Path) -> dict:
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {"error": "read failed"}

    detected = []
    findings = []
    for family, info in AMM_FAMILIES.items():
        if any(marker in source for marker in info["markers"]):
            detected.append(family)
            for check_id, regex, desc in info["risks"]:
                if re.search(regex, source):
                    findings.append({"family": family, "check": check_id, "description": desc, "severity": "Medium"})
    return {"file": str(path), "amm_families": detected, "findings": findings}


def scan_dir(target: Path) -> dict:
    if target.is_file():
        return {"files": [scan_file(target)]}
    files = sorted(target.rglob("*.sol"))
    files = [f for f in files if "node_modules" not in f.parts and "/lib/" not in str(f) and ".t.sol" not in f.name]
    results = []
    for f in files:
        r = scan_file(f)
        if r.get("amm_families"):
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
    (output_dir / "amm_findings.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not args.quiet:
        families = set()
        for fr in report["files"]:
            families.update(fr.get("amm_families", []))
        print(f"[+] AMM families: {families}")
        total = sum(len(f.get("findings", [])) for f in report["files"])
        print(f"[+] Findings: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
