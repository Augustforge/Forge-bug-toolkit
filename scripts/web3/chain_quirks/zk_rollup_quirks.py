#!/usr/bin/env python3
"""
zk_rollup_quirks.py — ZK-Rollup bug class hunter.

Covers: zkSync Era, Polygon zkEVM, Linea, Scroll, Starknet (EVM-compat aside).

ZK-Rollup quirks:
- Prover liveness assumption — if prover stops, no L2→L1 withdrawals
- Validium DA — if DA committee colludes, state lost
- Force-exit mechanisms (Starknet has, zkSync has)
- Verifier contract upgradeability (huge attack surface)

Bug classes:
- Force-exit missing
- Verifier upgrade backdoor
- DA assumption (validium vs rollup)
- Proof aggregation edge cases
"""

import argparse
import json
import re
from pathlib import Path


CHECKS = [
    ("force_exit_present", r"forceExit|requestL2Transaction|forceWithdrawal", "Force-exit mechanism"),
    ("verifier_upgrade", r"upgradeVerifier|setVerifier", "Verifier contract upgradeable — backdoor risk"),
    ("proof_aggregation", r"aggregateProof|batchProof", "Proof aggregation logic"),
    ("validium_da", r"validium|dataAvailability.*committee|DAC", "Validium DA — committee trust"),
    ("recursive_proof", r"recursiveProof|recursion", "Recursive proof — edge cases"),
    ("eip4844_blob", r"blob_versioned|blobhash|BLOB", "EIP-4844 blob usage"),
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
    (output_dir / "zk_rollup_quirks.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    total = sum(len(f.get("findings", [])) for f in report["files"])
    if not args.quiet:
        print(f"[+] ZK-Rollup findings: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
