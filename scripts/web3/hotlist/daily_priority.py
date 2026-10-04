#!/usr/bin/env python3
"""
daily_priority.py — Daily TOP-5 targets to hunt today.

Reads from:
- signal_aggregator output (~/.bbt/hotlist.json or specified)
- our current state (~/.bbt/state.json — whitehat_level, kyc status)

Outputs: ranked TOP-5 with actionable next steps.
"""

import argparse
import json
from pathlib import Path


def load_state() -> dict:
    state_file = Path.home() / ".bbt" / "state.json"
    if state_file.exists():
        return json.loads(state_file.read_text())
    return {
        "our_whitehat_level": 0,
        "kyc_passed": False,
        "hackerone_points": 0,
        "preferred_platforms": ["immunefi", "cantina", "hackerone"],
    }


def _action(t: dict, default_prefix: str) -> str:
    """Build an actionable next step. On-chain address -> /deephunt command;
    otherwise (cantina/immunefi program pages) -> the program URL to open."""
    addr = t.get("address")
    if addr:
        prefix = t.get("chain_prefix") or default_prefix
        return f"`/deephunt {prefix}{addr}`"
    if t.get("url"):
        return t["url"]
    return f"`/hunt {t['name']}`"


def filter_actionable(scored: list, our_state: dict) -> list:
    """Filter out targets we can't realistically pursue."""
    filtered = []
    for t in scored:
        # If accessibility blocked, skip
        if any("Whitehat level insufficient" in r for r in t["reasons"]):
            continue
        if any("KYC required but not completed" in r for r in t["reasons"]):
            if not our_state.get("kyc_passed"):
                continue
        filtered.append(t)
    return filtered


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--hotlist", default=str(Path.home() / ".bbt" / "hotlist.json"))
    p.add_argument("--state", help="Override state file path")
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--chain", choices=["evm", "solana", "all"], default="all", help="Filter by chain")
    args = p.parse_args()

    state = load_state()
    if args.state:
        state = json.loads(Path(args.state).read_text())

    if not Path(args.hotlist).exists():
        print(f"ERROR: hotlist not found at {args.hotlist}")
        print("Run signal_aggregator.py first")
        return 1

    scored = json.loads(Path(args.hotlist).read_text())
    actionable = filter_actionable(scored, state)

    if args.chain != "all":
        actionable = [t for t in actionable if t.get("chain", "evm") == args.chain]

    evm_targets = [t for t in actionable if t.get("chain", "evm") == "evm"]
    sol_targets = [t for t in actionable if t.get("chain") == "solana"]

    print(f"=== Daily Priority — TOP {args.top} ===\n")

    if args.chain in ("evm", "all") and evm_targets:
        print(f"## EVM Tier ({len(evm_targets)} candidates)\n")
        for i, t in enumerate(evm_targets[:args.top], 1):
            print(f"{i}. **{t['name']}** — score {t['score']}")
            for r in t["reasons"]:
                print(f"  - {r}")
            print(f"  Action: {_action(t, 'eth:')}\n")

    if args.chain in ("solana", "all") and sol_targets:
        print(f"\n## Solana Tier ({len(sol_targets)} candidates)\n")
        for i, t in enumerate(sol_targets[:args.top], 1):
            print(f"{i}. **{t['name']}** — score {t['score']}")
            for r in t["reasons"]:
                print(f"  - {r}")
            print(f"  Action: {_action(t, 'sol:')}\n")

    print(f"\nState: Whitehat L{state['our_whitehat_level']}, KYC {state.get('kyc_passed', False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
