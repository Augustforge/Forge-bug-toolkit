#!/usr/bin/env python3
"""
time_warp_simulator.py — find time-dependent code paths.

Flags:
- Interest accrual formulas (block.timestamp-based)
- Reward decay (timestamp delta)
- Lockup expiry checks
- TWAP windows
- Rate-limit timers
- Constants of suspicious sizes (1 year = 31536000, 1 day = 86400)

Output: ranked candidates for Foundry vm.warp() PoC testing.
"""
import argparse
import json
import re
import sys
from pathlib import Path


PATTERNS = [
    ("interest_accrual", re.compile(r"(\w+)\s*\+?=\s*[^;]*\bblock\.timestamp\b[^;]*[\*/]\s*\w+"), "Interest/reward accrual via timestamp delta — test warps"),
    ("lockup_expiry", re.compile(r"require\s*\(\s*block\.timestamp\s*[<>]=?\s*\w+"), "Lockup expiry — test boundary conditions"),
    ("rate_limit_window", re.compile(r"block\.timestamp\s*-\s*\w+\s*[<>]=?\s*\d+"), "Rate-limit window — test off-by-one"),
    ("year_constant", re.compile(r"\b31536000\b|365\s*days|365\s*\*\s*86400"), "Hardcoded 1y constant — drift / leap-year"),
    ("day_constant", re.compile(r"\b86400\b|1\s*days"), "Hardcoded 1d constant"),
    ("twap_window", re.compile(r"observ(?:e|ation)|TWAP|cumulative|\bperiod\b\s*=\s*\d+"), "TWAP observation window — test manipulation"),
    ("decay_exponent", re.compile(r"exp\s*\(|halving|decay|inflation"), "Decay/halving math — test long horizons"),
    ("vesting", re.compile(r"vest(?:ing|ed)|cliff|unlock_at|releaseTime"), "Vesting — test cliff/end boundaries"),
]


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    findings = []
    lines = text.splitlines()
    for pid, regex, advice in PATTERNS:
        for m in regex.finditer(text):
            line_no = text[: m.start()].count("\n") + 1
            snippet = lines[line_no - 1].strip()[:140] if line_no <= len(lines) else ""
            findings.append({
                "pattern": pid,
                "file": str(path),
                "line": line_no,
                "snippet": snippet,
                "advice": advice,
            })
    return findings


def emit_warp_scaffold(findings: list, path: str) -> str:
    body = [
        "// SPDX-License-Identifier: UNLICENSED",
        "pragma solidity ^0.8.0;",
        "import \"forge-std/Test.sol\";",
        "",
        "contract TimeWarpTest is Test {",
        "    function test_warp_one_day() public {",
        "        uint256 t0 = block.timestamp;",
        "        // TODO: snapshot relevant state",
        "        vm.warp(t0 + 1 days);",
        "        // TODO: assert no underflow / unexpected reward / lockup state",
        "    }",
        "",
        "    function test_warp_one_year() public {",
        "        vm.warp(block.timestamp + 365 days);",
        "        // TODO: assert interest accrual sane / no overflow",
        "    }",
        "",
        "    function test_warp_far_future() public {",
        "        vm.warp(2**40); // ~year 36000",
        "        // TODO: assert no math break",
        "    }",
        "}",
    ]
    return "\n".join(body)


def main():
    ap = argparse.ArgumentParser(description="Find time-dependent code for vm.warp() testing")
    ap.add_argument("--target", required=True)
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    target = Path(args.target)
    files = [target] if target.is_file() else list(target.rglob("*.sol")) if target.is_dir() else []
    if not files:
        print(f"[!] Target not found: {target}", file=sys.stderr)
        sys.exit(1)

    all_findings = []
    for f in files:
        if "/test" in str(f).replace("\\", "/").lower():
            continue
        all_findings.extend(scan_file(f))

    if not args.quiet:
        print(f"[+] Time-dependent sites: {len(all_findings)}")
        by = {}
        for f in all_findings:
            by.setdefault(f["pattern"], []).append(f)
        for p, items in sorted(by.items(), key=lambda x: -len(x[1])):
            print(f"  {p:25}  {len(items)}")
            for it in items[:2]:
                print(f"     {Path(it['file']).name}:{it['line']}  {it['snippet'][:80]}")

    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "time_warp.json").write_text(json.dumps(all_findings, indent=2), encoding="utf-8")
        (out / "TimeWarp.t.sol").write_text(emit_warp_scaffold(all_findings, str(target)), encoding="utf-8")


if __name__ == "__main__":
    main()
