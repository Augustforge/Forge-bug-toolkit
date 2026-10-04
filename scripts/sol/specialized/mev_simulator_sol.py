#!/usr/bin/env python3
"""mev_simulator_sol.py — model Solana MEV attack scenarios.

Solana MEV differs from EVM:
- **No classical mempool** — sandwich requires validator collusion OR Jito bundle access
- **Validator-level sandwiches (cross-slot)** — 93% of all sandwiches; frontrun in slot N, backrun in slot N+1
- **Jito bundles**: atomic block execution, no in-block ordering manipulation between non-bundle txs
- **Priority fees** in microlamports/CU — auction-like (highest fee first within bundle/slot)
- **Cross-slot timing**: leader schedule public 432 slots ahead

Scenarios this script models:
1. **Cross-slot sandwich**: profit from frontrun(slot_N) + victim_tx(slot_N) + backrun(slot_N+1)
2. **Jito bundle exclusion**: malicious bundle includes victim tx + sandwich, sent to specific validator
3. **Priority fee griefing**: attacker bid max priority fee to delay protocol txs
4. **Liquidation race**: who captures liquidation incentive given priority fees

Used in J4/S4 economic_analysis to determine MEV-accessibility component of feasibility score.

Usage:
    python3 mev_simulator_sol.py --scenario cross_slot_sandwich --victim-slippage-bps 100 --victim-trade-usd 10000
    python3 mev_simulator_sol.py --scenario liquidation_race --liquidation-bonus-usd 500
"""
import argparse, json, sys
from pathlib import Path


SOL_PRICE_USD_DEFAULT = 150.0
MICROLAMPORTS_PER_LAMPORT = 1_000_000
LAMPORTS_PER_SOL = 1_000_000_000
BASE_TX_FEE_LAMPORTS = 5000


def cu_cost_usd(cu_units: int, priority_fee_per_cu: int, sol_price: float) -> float:
    """Convert CU + priority fee to USD."""
    priority_lamports = (cu_units * priority_fee_per_cu) / MICROLAMPORTS_PER_LAMPORT
    total_lamports = priority_lamports + BASE_TX_FEE_LAMPORTS
    return (total_lamports / LAMPORTS_PER_SOL) * sol_price


def jito_tip_usd(tip_lamports: int, sol_price: float) -> float:
    return (tip_lamports / LAMPORTS_PER_SOL) * sol_price


def cross_slot_sandwich(victim_trade_usd: float, victim_slippage_bps: int,
                        sol_price: float, validator_collusion: bool = False) -> dict:
    """Model cross-slot sandwich. Without validator collusion - pure Jito bundle path."""
    max_extractable = victim_trade_usd * (victim_slippage_bps / 10000)
    realized_capture_pct = 0.6 if validator_collusion else 0.4
    profit_usd = max_extractable * realized_capture_pct

    if validator_collusion:
        attacker_cost = (
            cu_cost_usd(400_000, 50_000, sol_price)
            + cu_cost_usd(400_000, 50_000, sol_price)
            + 100.0
        )
    else:
        jito_tip = max(jito_tip_usd(100_000, sol_price), profit_usd * 0.3)
        attacker_cost = (
            cu_cost_usd(400_000, 100_000, sol_price)
            + cu_cost_usd(400_000, 100_000, sol_price)
            + jito_tip
        )

    roi = (profit_usd - attacker_cost) / max(attacker_cost, 0.01)
    feasibility_score = 70 if validator_collusion else 50

    findings = []
    if roi > 5:
        findings.append({
            "type": "high_mev_extractable",
            "severity": "high",
            "classification": "known_class",
            "description": f"Cross-slot sandwich extractable ${profit_usd:,.0f} net, ROI {roi:.1f}×. Protocol's slippage protection insufficient under {'validator collusion' if validator_collusion else 'Jito bundle'} conditions.",
        })
    if victim_slippage_bps > 100 and profit_usd > 100:
        findings.append({
            "type": "loose_slippage_protection",
            "severity": "medium",
            "classification": "known_class",
            "description": f"Default slippage {victim_slippage_bps}bps too loose. Recommend max 50bps + per-trade cap.",
        })

    return {
        "scenario": "cross_slot_sandwich",
        "victim_trade_usd": victim_trade_usd,
        "victim_slippage_bps": victim_slippage_bps,
        "max_extractable_usd": max_extractable,
        "realized_capture_pct": realized_capture_pct,
        "attacker_cost_usd": attacker_cost,
        "profit_usd": profit_usd,
        "net_profit_usd": profit_usd - attacker_cost,
        "roi": roi,
        "feasibility_score": feasibility_score,
        "findings": findings,
    }


def liquidation_race(liquidation_bonus_usd: float, sol_price: float, expected_competitors: int = 3) -> dict:
    """Model liquidation race economics."""
    win_probability = 1.0 / max(expected_competitors, 1)

    bid_priority_fee_per_cu = min(
        int((liquidation_bonus_usd * 0.5) / (300_000 / 1e6) / sol_price * 1e9),
        500_000,
    )
    attacker_cost = cu_cost_usd(300_000, bid_priority_fee_per_cu, sol_price)
    expected_profit = (liquidation_bonus_usd * win_probability) - attacker_cost

    findings = []
    if liquidation_bonus_usd > 1000 and expected_profit > 0:
        findings.append({
            "type": "profitable_liquidation_race",
            "severity": "info",
            "classification": "known_class",
            "description": f"Liquidation bonus ${liquidation_bonus_usd:,.0f} attracts {expected_competitors} competitors. Win prob {win_probability:.1%}, expected profit ${expected_profit:,.0f}.",
        })
    if win_probability < 0.1 and bid_priority_fee_per_cu >= 500_000:
        findings.append({
            "type": "priority_fee_griefing",
            "severity": "medium",
            "classification": "novel_instance",
            "description": "High competition pushes liquidator priority fees to max. Side effect: protocol txs (oracle updates, settlement) may be delayed.",
        })

    return {
        "scenario": "liquidation_race",
        "liquidation_bonus_usd": liquidation_bonus_usd,
        "competitors": expected_competitors,
        "win_probability": win_probability,
        "priority_fee_per_cu": bid_priority_fee_per_cu,
        "attacker_cost_usd": attacker_cost,
        "expected_profit_usd": expected_profit,
        "findings": findings,
    }


def jito_bundle_exclusion(victim_tx_value_usd: float, sol_price: float) -> dict:
    """Model attack where attacker submits Jito bundle excluding victim's defensive tx."""
    bundle_tip_usd = max(victim_tx_value_usd * 0.05, 10.0)
    attacker_cost = cu_cost_usd(800_000, 100_000, sol_price) + bundle_tip_usd
    profit_usd = victim_tx_value_usd * 0.3

    findings = []
    if profit_usd > attacker_cost * 2:
        findings.append({
            "type": "bundle_exclusion_extractable",
            "severity": "high",
            "classification": "novel_instance",
            "description": f"Atomic bundle execution allows excluding victim defensive tx. Net ${profit_usd - attacker_cost:,.0f}. Mitigation: multi-path submission (Jito + Paladin + bloXroute).",
        })

    return {
        "scenario": "jito_bundle_exclusion",
        "victim_tx_value_usd": victim_tx_value_usd,
        "bundle_tip_usd": bundle_tip_usd,
        "attacker_cost_usd": attacker_cost,
        "profit_usd": profit_usd,
        "net_profit_usd": profit_usd - attacker_cost,
        "findings": findings,
    }


def main():
    ap = argparse.ArgumentParser(description="Solana MEV scenario simulator")
    ap.add_argument("--scenario", choices=["cross_slot_sandwich", "liquidation_race", "jito_bundle_exclusion"], required=True)
    ap.add_argument("--sol-price", type=float, default=SOL_PRICE_USD_DEFAULT)
    ap.add_argument("--victim-trade-usd", type=float, default=10_000)
    ap.add_argument("--victim-slippage-bps", type=int, default=100)
    ap.add_argument("--validator-collusion", action="store_true")
    ap.add_argument("--liquidation-bonus-usd", type=float, default=500)
    ap.add_argument("--expected-competitors", type=int, default=3)
    ap.add_argument("--victim-tx-value-usd", type=float, default=50_000)
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    if args.scenario == "cross_slot_sandwich":
        result = cross_slot_sandwich(
            args.victim_trade_usd,
            args.victim_slippage_bps,
            args.sol_price,
            args.validator_collusion,
        )
    elif args.scenario == "liquidation_race":
        result = liquidation_race(
            args.liquidation_bonus_usd,
            args.sol_price,
            args.expected_competitors,
        )
    else:
        result = jito_bundle_exclusion(args.victim_tx_value_usd, args.sol_price)

    print(json.dumps(result, indent=2))

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
