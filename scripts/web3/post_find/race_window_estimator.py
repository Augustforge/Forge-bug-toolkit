#!/usr/bin/env python3
"""
race_window_estimator.py — Estimate time until another hunter may find the same bug.

Factors:
- Project freshness (recently deployed → more hunters looking)
- Code complexity (simple bug → race short, complex → race long)
- Public visibility (top-ranking on DefiLlama → many eyes)
- Bug class popularity (well-known class → race short)

Output: estimated race window in days + actions to take.
"""

import argparse
import json
from pathlib import Path


def estimate(factors: dict) -> dict:
    """Compute race window."""
    base_days = 30  # default

    project_age_days = factors.get("project_age_days", 365)
    if project_age_days < 30:
        base_days = max(1, base_days - 25)
    elif project_age_days < 90:
        base_days = max(3, base_days - 15)
    elif project_age_days < 365:
        base_days = max(7, base_days - 5)

    tvl_usd = factors.get("tvl_usd", 0)
    if tvl_usd > 100_000_000:
        base_days = max(1, base_days // 2)  # high attention
    elif tvl_usd > 10_000_000:
        base_days = max(2, int(base_days * 0.7))

    bug_class_obvious = factors.get("bug_class_obvious", False)
    if bug_class_obvious:
        base_days = max(1, base_days // 2)

    has_active_bounty = factors.get("has_active_bounty", True)
    if has_active_bounty:
        base_days = max(1, base_days // 2)  # bounty attracts attention

    audit_recent = factors.get("audit_recent_days", 999)
    if audit_recent < 90:
        base_days = max(2, int(base_days * 0.8))  # post-audit eyes

    actions = []
    if base_days <= 3:
        actions.append("🚨 URGENT — submit within 24h")
        actions.append("Prepare report quality FAST, not perfect")
        actions.append("Use established platform with fast triage")
    elif base_days <= 7:
        actions.append("⏰ Submit within 3 days")
        actions.append("Full PoC + economic analysis, then submit")
    else:
        actions.append("OK to be thorough, submit within 1-2 weeks")
        actions.append("Polish report, run J6 variant scan first")

    return {
        "estimated_race_window_days": base_days,
        "factors_input": factors,
        "actions": actions,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--project-age-days", type=int, default=365)
    p.add_argument("--tvl-usd", type=float, default=0)
    p.add_argument("--bug-class-obvious", action="store_true")
    p.add_argument("--no-active-bounty", action="store_true")
    p.add_argument("--audit-recent-days", type=int, default=999)
    p.add_argument("--output", default=".")
    args = p.parse_args()

    factors = {
        "project_age_days": args.project_age_days,
        "tvl_usd": args.tvl_usd,
        "bug_class_obvious": args.bug_class_obvious,
        "has_active_bounty": not args.no_active_bounty,
        "audit_recent_days": args.audit_recent_days,
    }
    result = estimate(factors)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "race_window.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"Race window: ~{result['estimated_race_window_days']} days")
    for a in result["actions"]:
        print(f"  - {a}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
