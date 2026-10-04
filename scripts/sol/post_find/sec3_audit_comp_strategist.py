#!/usr/bin/env python3
"""sec3_audit_comp_strategist.py — decide submission route for a confirmed Solana finding.

Once we have a confirmed Critical/High Solana finding — where do we submit it?
Routes:
1. **Immunefi** (if program listed) — biggest payouts ($1M-10M Critical)
2. **Sec3 audit competition** (if the contest is active) — share pool, no triage delay
3. **Direct to team** (if no public bounty) — little chance of payout, but fastest disclosure
4. **Sherlock-style retroactive** — if there is a post-fix bounty program

This is a decision tree based on:
- severity confirmed
- program listed in Immunefi (Y/N + max bounty)
- active Sec3/audit comp (Y/N + pool size)
- our handle reputation (HackerOne points equivalent)
- race window (how long until someone else finds it)
"""
import argparse, json, sys
from pathlib import Path


def decide_route(finding: dict) -> dict:
    severity = finding.get("severity", "low").lower()
    program = finding.get("program", "")
    immunefi_listed = finding.get("immunefi_listed", False)
    immunefi_max_bounty = finding.get("immunefi_max_bounty_usd", 0)
    sec3_active = finding.get("sec3_audit_comp_active", False)
    sec3_pool_usd = finding.get("sec3_pool_usd", 0)
    race_window_hours = finding.get("race_window_hours", 168)

    recommendations = []

    if severity in ("critical", "high") and immunefi_listed and immunefi_max_bounty >= 50_000:
        recommendations.append({
            "route": "immunefi",
            "rationale": f"Critical-tier finding + Immunefi listed (max ${immunefi_max_bounty:,}). Highest expected payout.",
            "priority": 1,
            "expected_payout_usd": immunefi_max_bounty,
            "expected_response_days": 7,
            "submission_url": f"https://immunefi.com/bug-bounty/{program}/",
            "notes": [
                "Use Immunefi Solana-specific submission template",
                "Attach Foundry/solana-program-test PoC, NOT just description",
                "Include exact severity argument with TVL-at-risk numbers",
            ],
        })

    if sec3_active and severity in ("critical", "high"):
        share_estimate = sec3_pool_usd * 0.3 if severity == "critical" else sec3_pool_usd * 0.1
        recommendations.append({
            "route": "sec3_audit_comp",
            "rationale": f"Active Sec3 audit competition (${sec3_pool_usd:,} pool). Expected share ~${share_estimate:,.0f}.",
            "priority": 2 if immunefi_listed else 1,
            "expected_payout_usd": share_estimate,
            "expected_response_days": 21,
            "notes": [
                "No triage delay - judging panel reviews directly",
                "Be aware: other auditors might find same bug = share dilution",
                "Quality of writeup matters more than on Immunefi",
            ],
        })

    if not immunefi_listed and not sec3_active:
        recommendations.append({
            "route": "direct_disclosure",
            "rationale": "No public bounty program. Direct to team email/Discord.",
            "priority": 1,
            "expected_payout_usd": 0,
            "expected_response_days": 30,
            "notes": [
                "Find team contact via official docs/website (NOT Twitter DM)",
                "Use PGP if available",
                "Set 90-day disclosure deadline upfront",
                "Document everything for retroactive bounty if team adds one later",
            ],
        })

    if race_window_hours < 48 and severity == "critical":
        for r in recommendations:
            r["urgent"] = True
            r["notes"].insert(0, f"URGENT: race window only {race_window_hours}h. Submit ASAP, others might find it.")

    return {
        "finding": program,
        "severity": severity,
        "recommendations": sorted(recommendations, key=lambda x: x["priority"]),
    }


def main():
    ap = argparse.ArgumentParser(description="Decide submission route for Solana finding")
    ap.add_argument("--finding-json", required=True,
                    help="JSON file with: program, severity, immunefi_listed, immunefi_max_bounty_usd, sec3_audit_comp_active, sec3_pool_usd, race_window_hours")
    ap.add_argument("--output")
    args = ap.parse_args()

    finding = json.loads(Path(args.finding_json).read_text())
    decision = decide_route(finding)

    print(f"=== Submission Strategy for {decision['finding']} ===")
    print(f"Severity: {decision['severity'].upper()}\n")
    for i, rec in enumerate(decision["recommendations"], 1):
        marker = "[URGENT] " if rec.get("urgent") else ""
        print(f"{i}. {marker}{rec['route'].upper()} (priority {rec['priority']})")
        print(f"   Why: {rec['rationale']}")
        print(f"   Expected payout: ${rec['expected_payout_usd']:,.0f}")
        print(f"   Response time: {rec['expected_response_days']}d")
        for note in rec["notes"]:
            print(f"   - {note}")
        print()

    if args.output:
        Path(args.output).write_text(json.dumps(decision, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
