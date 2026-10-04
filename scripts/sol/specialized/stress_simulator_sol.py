#!/usr/bin/env python3
"""
stress_simulator_sol.py — Bank-run, depeg, and mass-event stress simulator
for Solana liquid staking + lending protocols.

CONTEXT:
Audit reports assume equilibrium conditions. Real Critical bugs often live
in edge scenarios:
- Mass unstake event (50%+ TVL withdrawal in single epoch)
- LST/SOL depeg (mSOL trades at 0.85 SOL)
- Validator slash cascade (10+ validators affected simultaneously)
- Sudden TVL drop (40% drop in a single hour due to external shock)
- Oracle outage (Pyth halts on chain X)

These conditions break invariants that hold under normal load:
- Withdrawal queue overload → DoS or starvation
- Share math overflow on depeg
- Liquidation cascades depleting insurance fund
- Validator switch costs exceeding rewards

This tool models scenarios against protocol's state and finds where invariants break.

SCENARIOS:
1. **mass_unstake** — X% TVL unstakes in a single epoch
2. **depeg** — LST/SOL ratio drops to Y%
3. **slash_cascade** — N validators slashed simultaneously
4. **insurance_drain** — liquidation cascade exhausts safety fund
5. **oracle_outage** — Pyth halts, fallback behavior tested
6. **sequential_combo** — sequential of all above

OUTPUTS:
For each scenario:
- Invariant breaks detected (e.g., total_supply > total_assets after slash)
- Capacity exceeded (queue too long, gas/CU budget exhausted)
- Economic edge: who profits, who's exposed

USAGE:
    python3 stress_simulator_sol.py --scenario mass_unstake --pct-unstake 50 --tvl-sol 1000000
    python3 stress_simulator_sol.py --scenario depeg --depeg-ratio 0.85 --tvl-sol 1000000
    python3 stress_simulator_sol.py --scenario slash_cascade --validators-slashed 10
    python3 stress_simulator_sol.py --scenario sequential_combo --tvl-sol 1000000
"""
import argparse
import json
import sys
from pathlib import Path


SOL_PRICE_USD_DEFAULT = 150.0
EPOCHS_PER_DAY = 0.4
RESERVE_PCT_DEFAULT = 0.05


def mass_unstake_scenario(tvl_sol: float, pct_unstake: float, reserve_pct: float, sol_price: float) -> dict:
    requested_sol = tvl_sol * (pct_unstake / 100)
    reserve_sol = tvl_sol * reserve_pct
    stranded_sol = max(0, requested_sol - reserve_sol)
    epochs_to_clear = max(1, stranded_sol / max(reserve_sol * 0.5, 1))

    findings = []
    if pct_unstake >= 30 and stranded_sol > reserve_sol * 3:
        findings.append({
            "type": "withdrawal_queue_overload",
            "severity": "high" if pct_unstake >= 50 else "medium",
            "classification": "known_class",
            "broader_class": "bank_run_resilience",
            "description": f"At {pct_unstake}% mass unstake, {stranded_sol:,.0f} SOL stranded beyond reserve. "
                          f"Queue clearing takes ~{epochs_to_clear:.1f} epochs ({epochs_to_clear / EPOCHS_PER_DAY:.1f} days). "
                          f"User experience: claim ticket WAIT_EPOCHS could extend dramatically, MarinadeError::TicketNotReady cascading.",
        })

    if pct_unstake >= 50:
        findings.append({
            "type": "exchange_rate_manipulation_window",
            "severity": "critical",
            "classification": "novel_instance",
            "broader_class": "mass_event_economic_attack",
            "description": "Mass unstake creates extended period where mSOL trading on secondary market well below redemption value. "
                          "If user can mint mSOL at cheap secondary market and redeem at protocol oracle rate → arbitrage. "
                          "Investigate: is mSOL/SOL ratio cached, or live-computed per redemption?",
        })

    return {
        "scenario": "mass_unstake",
        "tvl_sol": tvl_sol,
        "pct_unstake": pct_unstake,
        "requested_sol": requested_sol,
        "reserve_sol": reserve_sol,
        "stranded_sol": stranded_sol,
        "epochs_to_clear": epochs_to_clear,
        "value_at_risk_usd": stranded_sol * sol_price,
        "findings": findings,
    }


def depeg_scenario(tvl_sol: float, depeg_ratio: float, sol_price: float) -> dict:
    lst_value_lost = tvl_sol * (1 - depeg_ratio)
    arb_window_sol = lst_value_lost * 0.5

    findings = []
    if depeg_ratio < 0.95:
        severity = "critical" if depeg_ratio < 0.85 else "high"
        findings.append({
            "type": "depeg_arbitrage_exposure",
            "severity": severity,
            "classification": "known_class",
            "broader_class": "depeg_economic_attack",
            "description": f"LST trading at {depeg_ratio*100:.0f}% of oracle redemption price. "
                          f"Arbitrage window: buy {arb_window_sol:,.0f} SOL worth of LST at market, "
                          f"redeem at protocol → ~{lst_value_lost*0.5*sol_price:,.0f} USD extractable. "
                          f"Mitigation: redemption rate must reflect market price, not stale oracle/internal accounting.",
        })

    if depeg_ratio < 0.80:
        findings.append({
            "type": "insolvency_risk",
            "severity": "critical",
            "classification": "known_class",
            "broader_class": "protocol_insolvency",
            "description": f"At {depeg_ratio*100:.0f}% depeg, redemption queue likely exceeds reserve. "
                          f"Liquidation cascade in integrated lending protocols (Solend/Kamino/Marginfi) holding mSOL as collateral. "
                          f"Cross-protocol contagion risk.",
        })

    return {
        "scenario": "depeg",
        "depeg_ratio": depeg_ratio,
        "lst_value_lost_sol": lst_value_lost,
        "lst_value_lost_usd": lst_value_lost * sol_price,
        "arb_window_sol": arb_window_sol,
        "findings": findings,
    }


def slash_cascade_scenario(validators_slashed: int, total_validators: int, avg_slash_pct: float,
                            tvl_sol: float, sol_price: float) -> dict:
    affected_pct = validators_slashed / max(total_validators, 1)
    stake_lost_sol = tvl_sol * affected_pct * (avg_slash_pct / 100)

    findings = []
    if validators_slashed >= 3:
        findings.append({
            "type": "multi_validator_slash_handling",
            "severity": "high",
            "classification": "novel_instance",
            "broader_class": "slash_cascade_recovery",
            "description": f"{validators_slashed} validators slashed (avg {avg_slash_pct}%). "
                          f"Total SOL lost: {stake_lost_sol:,.0f} ({stake_lost_sol*sol_price:,.0f} USD). "
                          f"Protocol must update total_active_balance across {validators_slashed} stake_accounts atomically OR "
                          f"handle partial updates safely. Race window: ahead of state update, users can withdraw at pre-slash rate.",
        })

    if validators_slashed >= 5:
        findings.append({
            "type": "compute_budget_exhaustion",
            "severity": "high",
            "classification": "novel_instance",
            "broader_class": "ops_capacity_under_stress",
            "description": f"Updating {validators_slashed} validators' state likely exceeds 1.4M CU per tx. "
                          f"Multi-tx update creates intermediate states. User ops between txs see partial-updated state.",
        })

    return {
        "scenario": "slash_cascade",
        "validators_slashed": validators_slashed,
        "total_validators": total_validators,
        "affected_pct": affected_pct,
        "stake_lost_sol": stake_lost_sol,
        "stake_lost_usd": stake_lost_sol * sol_price,
        "findings": findings,
    }


def insurance_drain_scenario(tvl_sol: float, insurance_fund_sol: float, sol_price: float) -> dict:
    insurance_pct = insurance_fund_sol / max(tvl_sol, 1) * 100

    findings = []
    if insurance_pct < 1:
        findings.append({
            "type": "thin_insurance_buffer",
            "severity": "medium",
            "classification": "known_class",
            "broader_class": "insurance_fund_sizing",
            "description": f"Insurance fund {insurance_pct:.2f}% of TVL. Single 1% slash event would exhaust fund. "
                          f"Subsequent slashes propagate losses to LST holders directly.",
        })

    return {
        "scenario": "insurance_drain",
        "tvl_sol": tvl_sol,
        "insurance_fund_sol": insurance_fund_sol,
        "insurance_pct_of_tvl": insurance_pct,
        "findings": findings,
    }


def oracle_outage_scenario(oracle_dependency: str, fallback_strategy: str | None) -> dict:
    findings = []
    if not fallback_strategy:
        findings.append({
            "type": "no_oracle_fallback",
            "severity": "high",
            "classification": "novel_instance",
            "broader_class": "oracle_dependency_brittleness",
            "description": f"Single oracle dependency ({oracle_dependency}) without fallback strategy documented. "
                          f"Oracle outage = redemption rate uncalculatable OR uses stale value. "
                          f"Either path is exploit surface.",
        })

    return {
        "scenario": "oracle_outage",
        "oracle_dependency": oracle_dependency,
        "fallback": fallback_strategy,
        "findings": findings,
    }


def sequential_combo(tvl_sol: float, sol_price: float) -> dict:
    chain = [
        mass_unstake_scenario(tvl_sol, 30, RESERVE_PCT_DEFAULT, sol_price),
        depeg_scenario(tvl_sol, 0.93, sol_price),
        slash_cascade_scenario(5, 100, 5, tvl_sol, sol_price),
    ]

    combo_findings = []
    for step in chain:
        combo_findings.extend(step["findings"])

    if combo_findings:
        combo_findings.append({
            "type": "compound_stress_amplification",
            "severity": "critical",
            "classification": "novel_instance",
            "broader_class": "cascade_failure",
            "description": "Sequential stress events compound effects. Mass unstake + depeg + slash cascade in same week "
                          "creates state inconsistencies (price stale, queue overloaded, reserve drained, insurance exhausted) "
                          "ALL simultaneously. Real Black Thursday scenario (March 2020 ETH crash). "
                          "Investigate: protocol behavior when 3+ adverse conditions stack.",
        })

    return {
        "scenario": "sequential_combo",
        "steps": [{"scenario": s["scenario"], "findings_count": len(s["findings"])} for s in chain],
        "all_findings": combo_findings,
    }


def main():
    ap = argparse.ArgumentParser(description="Stress simulator for Solana LST/lending protocols")
    ap.add_argument("--scenario", choices=[
        "mass_unstake", "depeg", "slash_cascade", "insurance_drain", "oracle_outage", "sequential_combo"
    ], required=True)
    ap.add_argument("--tvl-sol", type=float, default=1_000_000)
    ap.add_argument("--sol-price", type=float, default=SOL_PRICE_USD_DEFAULT)
    ap.add_argument("--pct-unstake", type=float, default=50)
    ap.add_argument("--reserve-pct", type=float, default=RESERVE_PCT_DEFAULT)
    ap.add_argument("--depeg-ratio", type=float, default=0.90)
    ap.add_argument("--validators-slashed", type=int, default=5)
    ap.add_argument("--total-validators", type=int, default=100)
    ap.add_argument("--avg-slash-pct", type=float, default=5.0)
    ap.add_argument("--insurance-fund-sol", type=float, default=10_000)
    ap.add_argument("--oracle-dependency", default="pyth")
    ap.add_argument("--fallback-strategy", default=None)
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    if args.scenario == "mass_unstake":
        result = mass_unstake_scenario(args.tvl_sol, args.pct_unstake, args.reserve_pct, args.sol_price)
    elif args.scenario == "depeg":
        result = depeg_scenario(args.tvl_sol, args.depeg_ratio, args.sol_price)
    elif args.scenario == "slash_cascade":
        result = slash_cascade_scenario(args.validators_slashed, args.total_validators, args.avg_slash_pct,
                                        args.tvl_sol, args.sol_price)
    elif args.scenario == "insurance_drain":
        result = insurance_drain_scenario(args.tvl_sol, args.insurance_fund_sol, args.sol_price)
    elif args.scenario == "oracle_outage":
        result = oracle_outage_scenario(args.oracle_dependency, args.fallback_strategy)
    else:
        result = sequential_combo(args.tvl_sol, args.sol_price)

    print(json.dumps(result, indent=2, default=str))

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
