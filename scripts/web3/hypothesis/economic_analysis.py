#!/usr/bin/env python3
"""
economic_analysis.py — Compute attack cost vs expected profit for a finding.

Used in /deephunt J4 to determine severity.

Severity rule:
- expected_profit > 10× attack_cost AND feasibility ≥ 50% → High/Critical
- expected_profit > attack_cost AND script-kiddie-capable → Critical
- Else → Medium/Low

Inputs (interactive or via --finding json):
- expected_profit_usd
- attack_cost_components (gas, capital, risk-of-revert)
- capital_required (with or without flash loan)
- mev_accessibility (does attacker need ordering control?)
- threat_tier (lowest tier capable of executing)

Output: economic_analysis.json with severity score and rationale.

Usage:
  python3 economic_analysis.py --interactive
  python3 economic_analysis.py --finding sessions/X/finding.json --tvl 10000000
"""

import argparse
import json
import sys
from pathlib import Path

# Flash loan source pools (chain-agnostic for now; mainnet defaults)
FLASH_LOAN_SOURCES = {
    "aave_v3": {"max_usd": 1_000_000_000, "fee_bps": 5},
    "maker_dss_flash": {"max_usd": 500_000_000, "fee_bps": 0, "tokens": ["DAI"]},
    "balancer_v2": {"max_usd": 200_000_000, "fee_bps": 0},
    "uniswap_v3": {"max_usd": 100_000_000, "fee_bps": 0},  # via flash callbacks
}

THREAT_TIERS = {
    "T1_script_kiddie": {"capital_max": 1000, "description": "Script kiddie — replays public exploits"},
    "T2_solo_whitehat": {"capital_max": 0, "description": "Whitehat reporter — finds but doesn't exploit"},
    "T3_solo_blackhat": {"capital_max": 100_000, "description": "Solo blackhat — manual custom exploits"},
    "T4_mev_searcher": {"capital_max": 10_000_000, "description": "MEV searcher — flash loans + bot infra"},
    "T5_sophisticated": {"capital_max": 100_000_000, "description": "Sophisticated — multi-step + zero-day"},
    "T6_nation_state": {"capital_max": float("inf"), "description": "Nation-state — supply chain + 0-days"},
}


def estimate_gas_cost_usd(gas_units: int, gas_price_gwei: float = 30.0, eth_price_usd: float = 3000.0) -> float:
    """Convert gas units to USD (EVM)."""
    return gas_units * gas_price_gwei * 1e-9 * eth_price_usd


def estimate_cu_cost_usd(
    compute_units: int,
    priority_fee_microlamports_per_cu: int = 10000,
    jito_tip_lamports: int = 0,
    sol_price_usd: float = 200.0,
) -> float:
    """Convert Solana Compute Units to USD.

    Components:
    - Priority fee: CU * micro_lamports_per_cu / 1e6 lamports
    - Jito tip (if MEV bundle): explicit lamports
    - Base signature fee: 5000 lamports per signature (negligible but added)

    sol_price_usd default 200 — adjust if needed.
    """
    priority_lamports = compute_units * priority_fee_microlamports_per_cu / 1_000_000
    base_signature_lamports = 5000
    total_lamports = priority_lamports + base_signature_lamports + jito_tip_lamports
    return (total_lamports / 1e9) * sol_price_usd


def estimate_attack_cost_usd(chain: str, **kwargs) -> float:
    """Chain-aware attack cost router.

    chain: "evm" or "solana"
    EVM kwargs: gas_units, gas_price_gwei, eth_price_usd
    Solana kwargs: compute_units, priority_fee_microlamports_per_cu, jito_tip_lamports, sol_price_usd
    """
    if chain == "evm":
        return estimate_gas_cost_usd(
            kwargs.get("gas_units", 200000),
            kwargs.get("gas_price_gwei", 30.0),
            kwargs.get("eth_price_usd", 3000.0),
        )
    elif chain == "solana":
        return estimate_cu_cost_usd(
            kwargs.get("compute_units", 200000),
            kwargs.get("priority_fee_microlamports_per_cu", 10000),
            kwargs.get("jito_tip_lamports", 0),
            kwargs.get("sol_price_usd", 200.0),
        )
    else:
        return estimate_gas_cost_usd(kwargs.get("gas_units", 200000))


SOLANA_FLASH_LOAN_SOURCES = {
    "kamino_flashloan": {"max_usd": 50_000_000, "fee_bps": 0, "tokens": ["SOL", "USDC", "USDT"]},
    "marginfi_flashloan": {"max_usd": 20_000_000, "fee_bps": 0},
    "solend_flashloan": {"max_usd": 10_000_000, "fee_bps": 9},
}


def determine_capital_source(capital_required_usd: float, target_tokens: list[str] = None) -> dict:
    """Find cheapest capital source. Flash loans preferred if available."""
    if capital_required_usd == 0:
        return {"source": "none", "fee_usd": 0, "feasible": True, "type": "no_capital"}

    target_tokens = target_tokens or []

    # Try flash loan sources
    for name, info in FLASH_LOAN_SOURCES.items():
        if capital_required_usd > info["max_usd"]:
            continue
        if "tokens" in info and not any(t in info["tokens"] for t in target_tokens):
            continue
        fee_usd = capital_required_usd * info["fee_bps"] / 10000
        return {
            "source": name,
            "fee_usd": fee_usd,
            "feasible": True,
            "type": "flash_loan",
        }

    # Owned capital required
    return {
        "source": "owned_capital",
        "fee_usd": 0,
        "feasible": capital_required_usd < 100_000_000,  # solo blackhat or sophisticated
        "type": "owned",
        "min_threat_tier": "T3" if capital_required_usd < 100_000 else "T4",
    }


def determine_threat_tier(capital_required_usd: float, mev_required: bool, multi_step: bool, crypto_specific: bool) -> str:
    """Determine lowest threat tier capable of executing."""
    if crypto_specific:
        return "T5_sophisticated"
    if mev_required:
        return "T4_mev_searcher"
    if capital_required_usd > 100_000_000:
        return "T5_sophisticated"
    if capital_required_usd > 100_000 and multi_step:
        return "T4_mev_searcher"
    if capital_required_usd > 1000:
        return "T3_solo_blackhat"
    return "T1_script_kiddie"


def compute_severity(profit_usd: float, cost_usd: float, threat_tier: str, feasibility_score: int) -> dict:
    """Compute severity verdict."""
    if cost_usd <= 0:
        roi = float("inf")
    else:
        roi = profit_usd / cost_usd

    # Default mapping
    severity_floor = {
        "T1_script_kiddie": "Critical" if profit_usd > 1000 else "High",
        "T2_solo_whitehat": "N/A",
        "T3_solo_blackhat": "High" if profit_usd > 100_000 else "Medium",
        "T4_mev_searcher": "Critical" if profit_usd > 100_000 else "High",
        "T5_sophisticated": "High" if profit_usd > 10_000_000 else "Medium",
        "T6_nation_state": "Low",  # supply-chain attacks rarely in bounty scope
    }

    base_severity = severity_floor.get(threat_tier, "Low")

    # Modifiers
    if roi >= 10 and feasibility_score >= 50:
        if base_severity == "Medium":
            base_severity = "High"
        elif base_severity == "Low":
            base_severity = "Medium"

    if profit_usd > 10_000_000 and feasibility_score >= 70:
        base_severity = "Critical"

    # Classification for the economic finding itself:
    # ROI > 100x with known-class exploit pattern → known_class
    # ROI > 100x with unmodeled cost dynamics (novel MEV path, new flash source) → novel_instance
    classification = "known_class" if roi <= 100 or threat_tier in ("T1_script_kiddie", "T3_solo_blackhat") else "novel_instance"
    return {
        "severity": base_severity,
        "roi": round(roi, 2) if roi != float("inf") else "infinity",
        "classification": classification,
        "broader_class": "economic_feasibility",
        "rationale": f"Lowest tier: {threat_tier}, profit ${profit_usd:,.0f}, cost ${cost_usd:,.2f}, ROI {roi:.1f}x, feasibility {feasibility_score}%",
    }


def main():
    p = argparse.ArgumentParser(description="Economic analysis for a finding (EVM + Solana)")
    p.add_argument("--finding", help="JSON file with finding details")
    p.add_argument("--interactive", action="store_true")
    p.add_argument("--profit", type=float, help="Expected profit USD")
    p.add_argument("--chain", choices=["evm", "solana"], default="evm", help="Target chain — selects cost model")
    p.add_argument("--gas-units", type=int, default=500_000, help="Gas for exploit tx (EVM)")
    p.add_argument("--gas-price", type=float, default=30.0, help="Gas price in gwei (EVM)")
    p.add_argument("--eth-price", type=float, default=3000.0, help="ETH price USD")
    p.add_argument("--compute-units", type=int, default=400_000, help="Compute Units (Solana)")
    p.add_argument("--priority-fee-cu", type=int, default=10000, help="Priority fee microlamports/CU (Solana)")
    p.add_argument("--jito-tip", type=int, default=0, help="Jito MEV bundle tip lamports (Solana)")
    p.add_argument("--sol-price", type=float, default=200.0, help="SOL price USD (Solana)")
    p.add_argument("--capital-required", type=float, default=0)
    p.add_argument("--mev-required", action="store_true")
    p.add_argument("--multi-step", action="store_true")
    p.add_argument("--crypto-specific", action="store_true")
    p.add_argument("--feasibility", type=int, default=70, help="Feasibility score 0-100")
    p.add_argument("--output", default=".")
    args = p.parse_args()

    if args.finding:
        data = json.loads(Path(args.finding).read_text())
    else:
        if args.profit is None:
            print("ERROR: provide --profit or --finding")
            return 1
        data = {
            "expected_profit_usd": args.profit,
            "gas_units": args.gas_units,
            "gas_price_gwei": args.gas_price,
            "eth_price_usd": args.eth_price,
            "capital_required_usd": args.capital_required,
            "mev_required": args.mev_required,
            "multi_step": args.multi_step,
            "crypto_specific": args.crypto_specific,
            "feasibility_score": args.feasibility,
        }

    chain = data.get("chain", args.chain if not args.finding else "evm")

    if chain == "solana":
        gas_cost = estimate_cu_cost_usd(
            data.get("compute_units", args.compute_units),
            data.get("priority_fee_microlamports_per_cu", args.priority_fee_cu),
            data.get("jito_tip_lamports", args.jito_tip),
            data.get("sol_price_usd", args.sol_price),
        )
    else:
        gas_cost = estimate_gas_cost_usd(
            data.get("gas_units", 500_000),
            data.get("gas_price_gwei", 30.0),
            data.get("eth_price_usd", 3000.0),
        )

    capital_source = determine_capital_source(
        data.get("capital_required_usd", 0),
        data.get("target_tokens", []),
    )

    total_cost = gas_cost + capital_source["fee_usd"]
    if capital_source["type"] == "owned" and not data.get("multi_step"):
        # Owned capital has opportunity cost — model 5% APR for 1 block (negligible)
        pass

    threat_tier = determine_threat_tier(
        data.get("capital_required_usd", 0),
        data.get("mev_required", False),
        data.get("multi_step", False),
        data.get("crypto_specific", False),
    )

    profit = data.get("expected_profit_usd", 0)
    feasibility = data.get("feasibility_score", 70)

    verdict = compute_severity(profit, total_cost, threat_tier, feasibility)

    output = {
        "input": data,
        "components": {
            "gas_cost_usd": round(gas_cost, 2),
            "capital_source": capital_source,
            "total_cost_usd": round(total_cost, 2),
            "lowest_threat_tier": threat_tier,
            "threat_tier_description": THREAT_TIERS[threat_tier]["description"],
        },
        "verdict": verdict,
    }

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "economic_analysis.json").write_text(json.dumps(output, indent=2), encoding="utf-8")

    print(f"\n=== Economic Analysis ===")
    print(f"Expected profit:  ${profit:,.2f}")
    print(f"Gas cost:         ${gas_cost:,.2f}")
    print(f"Capital fee:      ${capital_source['fee_usd']:,.2f}")
    print(f"Total cost:       ${total_cost:,.2f}")
    print(f"ROI:              {verdict['roi']}x")
    print(f"Capital source:   {capital_source['source']}")
    print(f"Threat tier:      {threat_tier}")
    print(f"Feasibility:      {feasibility}%")
    print(f"")
    print(f"VERDICT: {verdict['severity']}")
    print(f"Rationale: {verdict['rationale']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
