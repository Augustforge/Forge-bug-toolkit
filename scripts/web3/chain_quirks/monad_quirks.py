#!/usr/bin/env python3
"""
monad_quirks.py — Monad-specific bug class hunter.

Monad-specific quirks (vs Ethereum):
1. Gas billing on LIMIT (not used). Set high limit = pay high regardless of revert.
2. Cold SLOAD = 8,100 gas (vs 2,100 on Ethereum) — 4x more expensive
3. Cold EXTCODESIZE / CALL / DELEGATECALL = 10,100 gas (vs 2,600) — 4x more
4. ecRecover precompile = 6,000 gas (vs 3,000) — 2x
5. ecMul = 30,000 gas (vs 6,000) — 5x
6. ecPairing = 225,000 gas (vs 45,000) — 5x
7. Optimistic parallel execution — re-execution on state conflict
8. JIT VM compilation — potential intermittent differences vs interpreted EVM

Bug classes:
- Contracts with high gas limit estimation → cost overhead
- Heavy SLOAD usage → OOG in unexpected places
- Cryptographic operations more expensive (ZK protocols hit hard)
- State conflicts can re-execute, exposing race conditions
"""

import argparse
import json
import re
from pathlib import Path


CHECKS = [
    ("high_gas_limit_pattern", r"\.gasleft\(\)|gasleft\(\)", "Contract reads gasleft() — may compute incorrectly on Monad limit-billing"),
    ("heavy_cold_sload", r"function.*\(.*\)\s*(?:view|pure|external|public).*\{[^{}]*for.*\{[^{}]*SLOAD", "Heavy SLOAD pattern — Monad cold cost 4x"),
    ("ecrecover_intensive", r"ecrecover\s*\(", "ecrecover usage — 2x cost on Monad"),
    ("ecpairing_zk", r"ecPairing|pairing|BN254|BLS12", "ZK pairing operations — 5x cost on Monad"),
    ("ecmul_heavy", r"ecMul|ecAdd|scalarMul", "EC arithmetic — 5x cost on Monad"),
    ("storage_intensive_loop", r"for\s*\([^)]+\)\s*\{[^{}]*\b(mapping|storage)\b", "Loop with storage access — re-execution risk"),
    ("parallel_conflict_pattern", r"unchecked\s*\{[^{}]*\+\+|counter\s*\+\+", "Shared counter — parallel execution conflict"),
]


def scan_file(path: Path) -> dict:
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {"error": "read failed"}

    findings = []
    for check_id, regex, desc in CHECKS:
        matches = list(re.finditer(regex, source))
        if matches:
            for m in matches[:5]:
                line = source[: m.start()].count("\n") + 1
                findings.append({
                    "check": check_id,
                    "description": desc,
                    "line": line,
                    "match": m.group(0)[:80],
                })
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
    (output_dir / "monad_quirks.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    total = sum(len(f.get("findings", [])) for f in report["files"])
    if not args.quiet:
        print(f"[+] Monad-specific findings: {total} in {len(report['files'])} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
