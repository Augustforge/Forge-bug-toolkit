#!/usr/bin/env python3
"""
game_theory_analyzer.py — Nash equilibrium for liquidation / auction / staking.

Models:
- Liquidator profit margin (incentive vs gas cost)
- Auction with N bidders (winner's curse, last-mover advantage)
- Validator slash vs reward (is staking dominant strategy?)
- Bond-burn vs vote-honest (insurance protocol)

Input: scenario params. Output: dominant strategy + profitable threshold.
"""
import argparse
import json
import sys
from pathlib import Path


def analyze_liquidation(collateral_usd: float, debt_usd: float, bonus_pct: float, gas_cost_usd: float) -> dict:
    """When is liquidation profitable?"""
    seizable = collateral_usd
    bonus = debt_usd * (bonus_pct / 100)
    profit = bonus - gas_cost_usd
    profitable = profit > 0
    breakeven_bonus = (gas_cost_usd / debt_usd) * 100 if debt_usd > 0 else float("inf")
    return {
        "collateral_usd": collateral_usd,
        "debt_usd": debt_usd,
        "bonus_pct": bonus_pct,
        "gas_cost_usd": gas_cost_usd,
        "bonus_usd": bonus,
        "expected_profit": profit,
        "profitable": profitable,
        "breakeven_bonus_pct": breakeven_bonus,
        "verdict": (
            "Liquidator-favorable" if profit > gas_cost_usd
            else "Marginal — MEV competition only"
            if profit > 0 else "Unprofitable — bad debt accumulates"
        ),
    }


def analyze_auction(reserve_price: float, n_bidders: int, valuation_spread_pct: float = 20) -> dict:
    """N bidders w/ similar valuations — winner's curse?"""
    mean_valuation = reserve_price * 1.3
    bid_spread = mean_valuation * (valuation_spread_pct / 100)
    expected_winning_bid = mean_valuation + bid_spread * (1 - 1 / n_bidders)
    winners_curse_excess = expected_winning_bid - mean_valuation
    return {
        "reserve_price": reserve_price,
        "n_bidders": n_bidders,
        "estimated_winning_bid": expected_winning_bid,
        "winners_curse_loss": winners_curse_excess,
        "advice": "Implement second-price (Vickrey) to neutralize winner's curse"
                  if winners_curse_excess / mean_valuation > 0.05 else "Spread tolerable",
    }


def analyze_staking(stake: float, reward_apy_pct: float, slash_prob_per_year: float, slash_amount_pct: float) -> dict:
    """Is staking dominant?"""
    expected_reward = stake * (reward_apy_pct / 100)
    expected_slash = stake * (slash_amount_pct / 100) * slash_prob_per_year
    net_ev = expected_reward - expected_slash
    return {
        "stake": stake,
        "expected_reward": expected_reward,
        "expected_slash": expected_slash,
        "net_ev": net_ev,
        "ev_pct": (net_ev / stake) * 100,
        "verdict": (
            "Staking dominant" if net_ev > 0 else
            "Don't-stake dominant" if net_ev < -stake * 0.01 else
            "Mixed equilibrium — risk-aversion matters"
        ),
    }


def analyze_insurance_vote(stake: float, true_correct: bool, dishonest_reward: float, bond_burn: float, vote_passes_prob: float) -> dict:
    honest_ev = stake * 0.01 if true_correct else 0
    dishonest_ev = (dishonest_reward * vote_passes_prob) - (bond_burn * (1 - vote_passes_prob))
    return {
        "honest_ev": honest_ev,
        "dishonest_ev": dishonest_ev,
        "vote_honestly_dominant": honest_ev > dishonest_ev,
        "advice": "Increase bond_burn or lower dishonest_reward to make honesty dominant"
                  if dishonest_ev > honest_ev else "Mechanism is incentive-compatible",
    }


def main():
    ap = argparse.ArgumentParser(description="Game-theory analyzer for DeFi mechanisms")
    sub = ap.add_subparsers(dest="mode", required=True)

    p_liq = sub.add_parser("liquidation")
    p_liq.add_argument("--collateral", type=float, required=True)
    p_liq.add_argument("--debt", type=float, required=True)
    p_liq.add_argument("--bonus-pct", type=float, default=5)
    p_liq.add_argument("--gas-usd", type=float, default=30)

    p_auc = sub.add_parser("auction")
    p_auc.add_argument("--reserve", type=float, required=True)
    p_auc.add_argument("--bidders", type=int, default=5)
    p_auc.add_argument("--spread-pct", type=float, default=20)

    p_stk = sub.add_parser("staking")
    p_stk.add_argument("--stake", type=float, required=True)
    p_stk.add_argument("--apy", type=float, default=5)
    p_stk.add_argument("--slash-prob", type=float, default=0.001)
    p_stk.add_argument("--slash-pct", type=float, default=5)

    p_ins = sub.add_parser("insurance")
    p_ins.add_argument("--stake", type=float, required=True)
    p_ins.add_argument("--correct", action="store_true")
    p_ins.add_argument("--dishonest-reward", type=float, default=10000)
    p_ins.add_argument("--bond-burn", type=float, default=5000)
    p_ins.add_argument("--pass-prob", type=float, default=0.5)

    for p in (p_liq, p_auc, p_stk, p_ins):
        p.add_argument("--output", default=None)

    args = ap.parse_args()

    if args.mode == "liquidation":
        result = analyze_liquidation(args.collateral, args.debt, args.bonus_pct, args.gas_usd)
    elif args.mode == "auction":
        result = analyze_auction(args.reserve, args.bidders, args.spread_pct)
    elif args.mode == "staking":
        result = analyze_staking(args.stake, args.apy, args.slash_prob, args.slash_pct)
    elif args.mode == "insurance":
        result = analyze_insurance_vote(args.stake, args.correct, args.dishonest_reward, args.bond_burn, args.pass_prob)

    print(f"=== {args.mode.upper()} GAME-THEORY ANALYSIS ===")
    for k, v in result.items():
        if isinstance(v, float):
            print(f"  {k}: {v:,.4f}")
        else:
            print(f"  {k}: {v}")

    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{args.mode}_analysis.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
