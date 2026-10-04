#!/usr/bin/env python3
"""
attack_ev_estimate.py — quantitative expected-value gate for an attack hypothesis.

Operationalizes ugwst-sec `methodology/economic-attack-modeling.md` as a pre-flight check
(hypothesis_quality.md #6): before spending hours building a PoC, compute whether the attack
is even economically rational. A NEGATIVE EV doesn't kill a finding (permanent-freeze / data
bugs have non-$ impact, and severity is magnitude not just profit — see
[[feedback_push_severity_ceiling]]) but it tells you the *direct-extraction* angle is weak and
you should pivot to impact-not-profit framings (freeze, insolvency, griefing) or a cheaper vector.

    EV = P_success * profit
         - P_failure * loss_on_fail
         - gas
         - flashloan_fee (= principal * fee_bps/1e4)
         - opportunity_cost (= capital_locked * rate * hold_time_days/365)

AOE §3 net-profit checklist + anti-Goodhart (added 2026-08-05). The raw EV above SILENTLY ignored
three real attacker costs — slippage-in, exit-liquidity realizability, and MEV-backrun. The checklist
makes all six components explicit: `flash-fee / gas / slippage-in / exit-liquidity / MEV-backrun /
opp-cost`. **Anti-Goodhart rule:** a required component left unspecified (and not `--waive`d) ⇒ the
result is a BUILDING-BLOCK, not a clean "PROFITABLE" verdict — you cannot bank an EV while a cost is
unaccounted (that is exactly how naive EV over-states profit). The pre-existing raw `verdict`
(PROFITABLE/UNPROFITABLE) is left UNCHANGED; the checklist adds separate fields.

🔴 magnitude = protocol_loss, NOT this EV (AOE §1/§4, mythos Mandate 0.10). This script estimates the
ATTACKER's extraction. That number is a down-guard / realism input (Templar) — it is NEVER the source
of severity magnitude (magnitude = victim-side protocol_loss) and NEVER kills a non-economic finding.
**Carve (§4):** this economic lens applies ONLY to on-chain-extraction findings (`magnitude_eval.
applies=true`). A LATENT bug → prove via differential-patched-build, not fork-profit. A binary/off-chain
impact (freeze / DoS / web2) → this EV does not apply; severity comes from the program rubric.

Severity-components (AOE §3, prose in mythos near T4): amplification is modeled here as
`effective = per_shot_profit × iterations` (--iterations); pre-positioning / marination-cost is the
opportunity_cost term (capital locked while you wait for the setup). capability-budget (--capability-
budget, from attacker_profile.md §1) nets "unaffordable capital" against what a flash-loan actually
lends, symmetrically (AOE §2.1).

Usage:
    py -3 -X utf8 attack_ev_estimate.py --profit 1000000 --p-success 0.9 \
        --loss 50000 --gas 500 --capital 100000000 --flashloan-bps 9 --rate 0.05 --hold-days 0.001 \
        --slippage-in 2000 --exit-liquidity 15000 --mev-backrun 3000 --capability-budget 500000000
    py -3 -X utf8 attack_ev_estimate.py --self-test

All money args in USD. --json prints a machine-readable verdict.
"""
from __future__ import annotations

import argparse
import json
import sys


def expected_value(profit, p_success, loss, gas, capital, flashloan_bps, rate, hold_days):
    p_fail = max(0.0, 1.0 - p_success)
    flashloan_fee = capital * (flashloan_bps / 1e4)
    opportunity = capital * rate * (hold_days / 365.0)
    ev = (p_success * profit) - (p_fail * loss) - gas - flashloan_fee - opportunity
    return {
        "expected_value_usd": ev,
        "gross_if_success": p_success * profit,
        "expected_loss_on_fail": p_fail * loss,
        "gas_usd": gas,
        "flashloan_fee_usd": flashloan_fee,
        "opportunity_cost_usd": opportunity,
        "p_failure": p_fail,
        "verdict": "PROFITABLE" if ev > 0 else "UNPROFITABLE",
    }


# ──────────────────────────────────────────────────────────────────────────
# AOE §3 — net-profit component checklist + anti-Goodhart (extends, never replaces, the raw EV)
# ──────────────────────────────────────────────────────────────────────────

# The six components a HONEST net-profit accounting must cover. The raw EV above already models
# flash-fee / gas / opp-cost; slippage-in / exit-liquidity / MEV-backrun were silently ignored
# (that omission is what over-states naive EV) → they are the ones the anti-Goodhart rule guards.
REQUIRED_COMPONENTS = ["flash-fee", "gas", "slippage-in", "exit-liquidity", "MEV-backrun", "opp-cost"]


def profit_component_checklist(*, capital, flashloan_bps, gas, hold_days,
                               slippage_in, exit_liquidity, mev_backrun, waived):
    """Return which of the six net-profit components are accounted vs missing.

    Anti-Goodhart (AOE §3): a NEW component (slippage-in / exit-liquidity / MEV-backrun) that is
    neither given a value nor `--waive`d counts as MISSING → status BUILDING-BLOCK-INCOMPLETE. The
    three EV-modeled components are always accounted (0 is a valid value). `waived` = set of names
    the hunter explicitly asserted N/A.
    """
    accounted = {}
    missing = []
    # Components the raw EV already models (0 is a legitimate value → always accounted):
    accounted["flash-fee"] = "N/A (no capital)" if capital == 0 else f"modeled ({flashloan_bps:g} bps)"
    accounted["gas"] = f"modeled (${gas:,.0f})"
    accounted["opp-cost"] = ("N/A (no capital lock)" if (capital == 0 or hold_days == 0)
                             else "modeled (= pre-positioning / marination-cost)")
    # Components the naive EV IGNORED → must be explicit or waived (anti-Goodhart):
    for name, val in (("slippage-in", slippage_in),
                      ("exit-liquidity", exit_liquidity),
                      ("MEV-backrun", mev_backrun)):
        if name in waived:
            accounted[name] = "waived (asserted N/A)"
        elif val is None:
            missing.append(name)
        else:
            accounted[name] = f"${val:,.0f}"
    return {
        "required": REQUIRED_COMPONENTS,
        "accounted": accounted,
        "missing": missing,
        "status": "COMPLETE" if not missing else "BUILDING-BLOCK-INCOMPLETE",
    }


def capability_budget_check(capital, capability_budget):
    """Net 'unaffordable capital' against what the attacker profile says is cheaply available.

    AOE §2.1 symmetry: capital above a flash-loan budget is NOT automatically a practicality-kill —
    it is borrowed & repaid in one tx. Returns a note; `exceeded=True` only when a budget is supplied
    AND capital exceeds it (then it is a genuine capability question, not raw '$ too big').
    """
    if capability_budget is None:
        return {"supplied": False, "exceeded": None,
                "note": "capability-budget not supplied — pull attacker's cheap capital ceiling from "
                        "attacker_profile.md §1 (flash-liquidity) to net this EV symmetrically (AOE §2.1)."}
    exceeded = capital > capability_budget
    return {
        "supplied": True,
        "budget_usd": capability_budget,
        "exceeded": exceeded,
        "note": (f"required capital ${capital:,.0f} EXCEEDS profile budget ${capability_budget:,.0f} "
                 f"→ capability question (is more flash-liquidity reachable?), not raw '$ too big'."
                 if exceeded else
                 f"required capital ${capital:,.0f} within profile budget ${capability_budget:,.0f} "
                 f"→ affordable via flash-liquidity, NOT a practicality-kill."),
    }


def _run_self_test() -> bool:
    """Unit-test the checklist + anti-Goodhart + capability-budget + amplification (no I/O)."""
    results = []

    def check(name, cond):
        ok = bool(cond)
        print("  [%s] %s" % ("PASS" if ok else "FAIL", name))
        results.append(ok)

    # (1) raw EV unchanged (backward-compat guard on the pre-existing function/keys).
    r = expected_value(profit=1_000_000, p_success=0.9, loss=50_000, gas=500,
                       capital=100_000_000, flashloan_bps=9, rate=0.05, hold_days=0.001)
    check("raw EV keys intact + PROFITABLE", r["verdict"] == "PROFITABLE"
          and abs(r["flashloan_fee_usd"] - 90_000) < 1e-6)

    # (2) anti-Goodhart: missing new components → BUILDING-BLOCK-INCOMPLETE.
    c = profit_component_checklist(capital=100_000_000, flashloan_bps=9, gas=500, hold_days=0.001,
                                   slippage_in=None, exit_liquidity=None, mev_backrun=None, waived=set())
    check("missing slippage/exit/mev → INCOMPLETE", c["status"] == "BUILDING-BLOCK-INCOMPLETE")
    check("missing lists all 3 ignored components",
          set(c["missing"]) == {"slippage-in", "exit-liquidity", "MEV-backrun"})

    # (3) provide all three → COMPLETE.
    c2 = profit_component_checklist(capital=100_000_000, flashloan_bps=9, gas=500, hold_days=0.001,
                                    slippage_in=2000, exit_liquidity=15000, mev_backrun=3000, waived=set())
    check("all three provided → COMPLETE", c2["status"] == "COMPLETE" and not c2["missing"])

    # (4) waiving counts as accounted (explicit decision ≠ silent omission).
    c3 = profit_component_checklist(capital=0, flashloan_bps=0, gas=500, hold_days=0,
                                    slippage_in=None, exit_liquidity=None, mev_backrun=None,
                                    waived={"slippage-in", "exit-liquidity", "MEV-backrun"})
    check("waiving all three → COMPLETE", c3["status"] == "COMPLETE")
    check("no-capital → flash-fee & opp-cost N/A", "N/A" in c3["accounted"]["flash-fee"]
          and "N/A" in c3["accounted"]["opp-cost"])

    # (5) capability-budget: within vs exceeded vs unsupplied.
    b_within = capability_budget_check(100_000_000, 500_000_000)
    b_over = capability_budget_check(2_000_000_000, 500_000_000)
    b_none = capability_budget_check(100_000_000, None)
    check("capital within budget → not exceeded", b_within["exceeded"] is False)
    check("capital over budget → exceeded", b_over["exceeded"] is True)
    check("no budget supplied → note points to attacker_profile.md", b_none["supplied"] is False
          and "attacker_profile.md" in b_none["note"])

    # (6) amplification through the REAL layer (not a tautology): per_shot × iterations flows through aoe_ev_layer.
    amp = aoe_ev_layer(100_000, 5000, 20, capital=0, flashloan_bps=0, gas=500, hold_days=0,
                       slippage_in=None, exit_liquidity=None, mev_backrun=None, waived=set(), capability_budget=None)
    check("amplification: per_shot 5000 × 20 iters → 100000 effective", amp["effective_profit"] == 100_000)

    # (7) ev_gate — all 4 branches through the real layer (anti-Goodhart core, previously uncovered).
    g_unprof = aoe_ev_layer(-1.0, 100, 1, capital=0, flashloan_bps=0, gas=500, hold_days=0,
                            slippage_in=None, exit_liquidity=None, mev_backrun=None, waived=set(), capability_budget=None)
    check("ev_gate: EV<=0 → UNPROFITABLE", g_unprof["ev_gate"] == "UNPROFITABLE")
    g_incompl = aoe_ev_layer(10_000.0, 10_000, 1, capital=100_000_000, flashloan_bps=9, gas=500, hold_days=0,
                             slippage_in=None, exit_liquidity=None, mev_backrun=None, waived=set(), capability_budget=None)
    check("ev_gate: EV>0 but missing components → PROFITABLE-BUT-INCOMPLETE",
          g_incompl["ev_gate"].startswith("PROFITABLE-BUT-INCOMPLETE"))
    g_negfull = aoe_ev_layer(5_000.0, 5_000, 1, capital=0, flashloan_bps=0, gas=500, hold_days=0,
                             slippage_in=3000, exit_liquidity=3000, mev_backrun=2000, waived=set(), capability_budget=None)
    check("ev_gate: EV>0 but net<=0 after full checklist → UNPROFITABLE-AFTER-FULL-CHECKLIST",
          g_negfull["ev_gate"] == "UNPROFITABLE-AFTER-FULL-CHECKLIST")
    g_ok = aoe_ev_layer(50_000.0, 50_000, 1, capital=0, flashloan_bps=0, gas=500, hold_days=0,
                        slippage_in=1000, exit_liquidity=1000, mev_backrun=1000, waived=set(), capability_budget=None)
    check("ev_gate: EV>0 and net>0 full checklist → PROFITABLE-COMPLETE", g_ok["ev_gate"] == "PROFITABLE-COMPLETE")

    n_ok = sum(results)
    print("\n%d/%d attack_ev_estimate self-test cases green" % (n_ok, len(results)))
    return n_ok == len(results)


def aoe_ev_layer(expected_value_usd, per_shot_profit, iterations, *, capital, flashloan_bps, gas,
                 hold_days, slippage_in, exit_liquidity, mev_backrun, waived, capability_budget):
    """AOE §3 layer — pure/testable: net-profit checklist + amplification + ev_gate verdict.
    Split out of main() so the anti-Goodhart ev_gate branches are unit-testable (not a tautology)."""
    iterations = max(1, iterations)
    effective_profit = per_shot_profit * iterations
    checklist = profit_component_checklist(
        capital=capital, flashloan_bps=flashloan_bps, gas=gas, hold_days=hold_days,
        slippage_in=slippage_in, exit_liquidity=exit_liquidity, mev_backrun=mev_backrun, waived=waived)
    budget = capability_budget_check(capital, capability_budget)
    extra_cost = sum(v for v in (slippage_in, exit_liquidity, mev_backrun) if v is not None)
    net_ev = (expected_value_usd - extra_cost) if checklist["status"] == "COMPLETE" else None
    if expected_value_usd <= 0:
        ev_gate = "UNPROFITABLE"
    elif checklist["status"] != "COMPLETE":
        ev_gate = "PROFITABLE-BUT-INCOMPLETE (building-block — account missing components before banking EV)"
    elif net_ev is not None and net_ev <= 0:
        ev_gate = "UNPROFITABLE-AFTER-FULL-CHECKLIST"
    else:
        ev_gate = "PROFITABLE-COMPLETE"
    return {"iterations": iterations, "effective_profit": effective_profit, "checklist": checklist,
            "budget": budget, "net_ev": net_ev, "ev_gate": ev_gate}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--self-test" in argv:
        return 0 if _run_self_test() else 1

    ap = argparse.ArgumentParser(description="Attack expected-value pre-flight gate (economic-attack-modeling)")
    ap.add_argument("--profit", type=float, required=True, help="extractable value if attack succeeds (USD, per-shot if --iterations>1)")
    ap.add_argument("--p-success", type=float, default=0.8, help="probability of success 0..1 (default 0.8)")
    ap.add_argument("--loss", type=float, default=0.0, help="capital lost if attack fails (USD)")
    ap.add_argument("--gas", type=float, default=500.0, help="gas cost (USD, default 500)")
    ap.add_argument("--capital", type=float, default=0.0, help="capital deployed / flash-loan principal (USD)")
    ap.add_argument("--flashloan-bps", type=float, default=0.0, help="flash-loan fee in bps (Aave=9, Balancer=0)")
    ap.add_argument("--rate", type=float, default=0.05, help="opportunity-cost annual rate (default 0.05)")
    ap.add_argument("--hold-days", type=float, default=0.0, help="days capital is locked (TWAP window etc.)")
    # AOE §3 net-profit checklist components (the ones the naive EV silently ignored):
    ap.add_argument("--slippage-in", type=float, default=None, help="AOE §3: cost of slippage entering the position (USD)")
    ap.add_argument("--exit-liquidity", type=float, default=None,
                    help="AOE §3: exit-liquidity haircut — nominal profit that can't be realized in thin liquidity (USD)")
    ap.add_argument("--mev-backrun", type=float, default=None, help="AOE §3: value lost to being backrun/sandwiched (USD)")
    ap.add_argument("--waive", action="append", default=[], choices=["slippage-in", "exit-liquidity", "MEV-backrun"],
                    help="explicitly assert a component is N/A (counts as accounted, not a silent omission)")
    # AOE §3 severity-component / §2.1 profile inputs:
    ap.add_argument("--iterations", type=int, default=1, help="AOE §3 amplification: effective = per-shot profit × iterations")
    ap.add_argument("--capability-budget", type=float, default=None,
                    help="AOE §2.1: cheap capital ceiling from attacker_profile.md §1 (nets 'unaffordable capital')")
    ap.add_argument("--self-test", action="store_true", help="run the built-in unit tests and exit")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    # AOE §3 amplification: --profit is per-shot; effective gross = per_shot × iterations (default 1 = identity).
    iterations = max(1, args.iterations)
    effective_profit = args.profit * iterations

    r = expected_value(effective_profit, args.p_success, args.loss, args.gas,
                        args.capital, args.flashloan_bps, args.rate, args.hold_days)

    # ── AOE §3 layer (pure, unit-tested via aoe_ev_layer; existing r-keys above untouched) ──
    layer = aoe_ev_layer(r["expected_value_usd"], args.profit, args.iterations,
                         capital=args.capital, flashloan_bps=args.flashloan_bps, gas=args.gas,
                         hold_days=args.hold_days, slippage_in=args.slippage_in,
                         exit_liquidity=args.exit_liquidity, mev_backrun=args.mev_backrun,
                         waived=set(args.waive), capability_budget=args.capability_budget)
    checklist = layer["checklist"]
    budget = layer["budget"]
    net_ev = layer["net_ev"]
    ev_gate = layer["ev_gate"]

    r["amplification"] = {"per_shot_profit": args.profit, "iterations": iterations, "effective_profit": effective_profit}
    r["profit_checklist"] = checklist
    r["net_ev_usd"] = net_ev
    r["ev_gate"] = ev_gate
    r["capability_budget"] = budget
    r["magnitude_note"] = ("This EV = attacker extraction estimate. magnitude = protocol_loss (victim-side), "
                           "NOT this number (Mandate 0.10). attacker-profit here = down-guard / realism input only.")
    r["carve"] = ("on-chain-extraction lens (magnitude_eval.applies=true). LATENT bug → differential-patched-build, "
                  "not fork-profit. binary/off-chain (freeze/DoS/web2) → EV n/a; severity by program rubric.")

    if args.json:
        print(json.dumps(r, indent=2))
    else:
        print("Attack EV estimate")
        print("-" * 48)
        print(f"  gross if success     : ${r['gross_if_success']:,.0f}")
        print(f"  - expected fail loss : ${r['expected_loss_on_fail']:,.0f}")
        print(f"  - gas                : ${r['gas_usd']:,.0f}")
        print(f"  - flash-loan fee     : ${r['flashloan_fee_usd']:,.0f}")
        print(f"  - opportunity cost   : ${r['opportunity_cost_usd']:,.0f}")
        print("-" * 48)
        print(f"  EXPECTED VALUE       : ${r['expected_value_usd']:,.0f}  -> {r['verdict']}")
        if r["verdict"] == "UNPROFITABLE":
            print("  note: negative direct-extraction EV. Pivot to impact-not-profit framings")
            print("        (permanent freeze / insolvency / griefing) or a cheaper vector before discarding.")
        # ── AOE §3 net-profit checklist (anti-Goodhart) ──
        if iterations > 1:
            print(f"\n  amplification        : ${args.profit:,.0f} per-shot × {iterations} = ${effective_profit:,.0f} effective")
        print("\n  net-profit component checklist (AOE §3):")
        for comp in checklist["required"]:
            if comp in checklist["accounted"]:
                print(f"    [x] {comp:<14} {checklist['accounted'][comp]}")
            else:
                print(f"    [ ] {comp:<14} MISSING — unaccounted")
        print(f"  checklist status     : {checklist['status']}")
        if net_ev is not None:
            print(f"  NET EV (full)        : ${net_ev:,.0f}")
        print(f"  EV GATE              : {ev_gate}")
        if checklist["status"] != "COMPLETE":
            print("  anti-Goodhart: a missing component ⇒ BUILDING-BLOCK, not a bankable EV "
                  "(supply it or --waive).")
        print(f"\n  capability-budget    : {budget['note']}")
        print(f"  magnitude            : {r['magnitude_note']}")
        print(f"  carve                : {r['carve']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
