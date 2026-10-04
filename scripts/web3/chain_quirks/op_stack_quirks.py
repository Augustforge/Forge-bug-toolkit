#!/usr/bin/env python3
"""
op_stack_quirks.py — OP-Stack rollup bug class hunter.

Covers: Optimism, Base, Mode, Zora, World Chain, Soneium, others on OP-Stack.

Quirks:
- Sequencer pause = no liquidations, force-exit only via L1
- L1→L2 message timing (~10 min)
- L2→L1 withdrawal (~7 days)
- Fault proofs (Cannon, in rollout)
- Sequencer revenue model

Bug classes:
- Liquidation impossible during sequencer pause
- Force-exit not handled by protocol
- L1↔L2 message ordering assumptions
- Trusted timestamp ↔ block timestamp drift
"""

import argparse
import json
import re
from pathlib import Path


CHECKS = [
    ("sequencer_uptime_check", r"sequencerUptimeFeed|L2SequencerUptimeFeed|0xFdB631F5EE196F0ed6FAa767959853A9F217697D", "Sequencer uptime feed check"),
    ("force_exit_handling", r"forceExit|forceWithdrawal|emergencyWithdraw", "Force-exit path during sequencer down"),
    ("l1_l2_message", r"sendMessage|CrossDomainMessenger|relayMessage", "Cross-domain message handling"),
    ("withdrawal_finality", r"finalizeWithdrawal|proveWithdrawal", "Withdrawal proof/finalize logic"),
    ("liquidation_no_seq_check", r"liquidat.*\(.*\).*\{[^{}]{0,300}(?!sequencerUptime)", "Liquidation w/o sequencer check"),
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
    # Missing sequencer check is critical
    has_check = any(f["check"] == "sequencer_uptime_check" for f in findings)
    has_liquidation = "liquidat" in source.lower()
    if has_liquidation and not has_check:
        findings.append({
            "check": "missing_sequencer_uptime",
            "description": "🚨 Liquidation logic present but NO sequencer uptime check — Critical for L2",
            "severity": "High",
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
    (output_dir / "op_stack_quirks.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    total = sum(len(f.get("findings", [])) for f in report["files"])
    if not args.quiet:
        print(f"[+] OP-Stack findings: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
