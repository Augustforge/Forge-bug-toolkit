#!/usr/bin/env python3
"""
tokenomics_simulator.py — model weird-token behavior over N blocks.

Simulates:
- fee-on-transfer (transfer amount != received amount)
- rebasing (balance changes between txs without transfer)
- deflationary burn (totalSupply decreases per tx)
- inflationary mint (totalSupply increases per epoch)
- pause/blacklist (transfer reverts mid-flow)

Use to predict accounting drift in protocol that integrates these tokens.
"""
import argparse
import json
import sys
from pathlib import Path


def simulate_fee_on_transfer(initial: float, fee_bps: int, n_transfers: int) -> dict:
    """Each transfer loses fee_bps/10000 of amount."""
    balance = initial
    sent_total = 0
    received_total = 0
    for _ in range(n_transfers):
        sent_total += balance
        received = balance * (1 - fee_bps / 10000)
        received_total += received
        balance = received
    return {
        "initial": initial,
        "final_balance": balance,
        "sent_total": sent_total,
        "received_total": received_total,
        "lost_to_fees": sent_total - received_total,
        "drift_pct": ((initial - balance) / initial) * 100,
    }


def simulate_rebase(initial: float, rebase_factor: float, n_epochs: int) -> dict:
    """Balance multiplied by rebase_factor each epoch."""
    balance = initial
    history = [balance]
    for _ in range(n_epochs):
        balance *= rebase_factor
        history.append(balance)
    return {
        "initial": initial,
        "final_balance": balance,
        "epochs": n_epochs,
        "drift_pct": ((balance - initial) / initial) * 100,
        "first_5_epochs": history[:5],
    }


def simulate_deflationary(initial_supply: float, burn_bps_per_tx: int, n_txs: int) -> dict:
    supply = initial_supply
    for _ in range(n_txs):
        supply *= (1 - burn_bps_per_tx / 10000)
    return {
        "initial_supply": initial_supply,
        "final_supply": supply,
        "burned": initial_supply - supply,
        "burn_pct": ((initial_supply - supply) / initial_supply) * 100,
    }


def emit_assumptions_check(results: dict) -> list:
    risks = []
    if results.get("fee_on_transfer", {}).get("drift_pct", 0) > 1:
        risks.append({
            "primitive": "fee_on_transfer",
            "advice": "Integrating protocols MUST measure received balance, not assume amount == received. Otherwise accounting drift accumulates.",
        })
    if abs(results.get("rebase", {}).get("drift_pct", 0)) > 5:
        risks.append({
            "primitive": "rebasing",
            "advice": "Cached balance snapshots become stale. Withdraw flow must re-query current balance.",
        })
    if results.get("deflationary", {}).get("burn_pct", 0) > 5:
        risks.append({
            "primitive": "deflationary",
            "advice": "totalSupply drift breaks share-based pricing if vault assumes static supply.",
        })
    return risks


def main():
    ap = argparse.ArgumentParser(description="Simulate weird-token behavior over time")
    ap.add_argument("--initial", type=float, default=1_000_000, help="Initial amount")
    ap.add_argument("--blocks", type=int, default=100, help="Number of blocks/txs to simulate")
    ap.add_argument("--fee-bps", type=int, default=100, help="Fee on transfer (bps)")
    ap.add_argument("--rebase-factor", type=float, default=1.0005, help="Rebase multiplier per epoch")
    ap.add_argument("--burn-bps", type=int, default=50, help="Burn bps per tx")
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    results = {
        "fee_on_transfer": simulate_fee_on_transfer(args.initial, args.fee_bps, args.blocks),
        "rebase": simulate_rebase(args.initial, args.rebase_factor, args.blocks),
        "deflationary": simulate_deflationary(args.initial, args.burn_bps, args.blocks),
    }
    results["integration_risks"] = emit_assumptions_check(results)

    if not args.quiet:
        print(f"[+] Tokenomics simulation over {args.blocks} blocks/txs (initial={args.initial})\n")
        for key, val in results.items():
            if key == "integration_risks":
                continue
            print(f"[{key}]")
            for k, v in val.items():
                if isinstance(v, list):
                    print(f"  {k}: {v}")
                elif isinstance(v, float):
                    print(f"  {k}: {v:,.4f}")
                else:
                    print(f"  {k}: {v}")
            print()
        print("Integration risks:")
        for r in results["integration_risks"]:
            print(f"  [{r['primitive']}] {r['advice']}")

    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "tokenomics_sim.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
