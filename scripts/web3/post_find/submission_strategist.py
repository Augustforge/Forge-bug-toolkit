#!/usr/bin/env python3
"""
submission_strategist.py — Decide where to submit a confirmed finding.

Decision tree:
- Has Immunefi program? → Immunefi (highest payouts)
- Has HackerOne program? → HackerOne (good payouts + reputation)
- Has HackenProof? → HackenProof
- Has Sherlock retro? → Sherlock retro (rare but high)
- None → coordinated disclosure direct (lowest expected, but always option)

Considerations:
- Whitehat Level required for target program
- KYC requirements
- Disclosure timeline expectations
- Payout currency (USDC vs token)
"""

import argparse
import json
from pathlib import Path


PLATFORMS_INFO = {
    "immunefi": {
        "url": "https://immunefi.com/",
        "kyc": "required for payout",
        "whitehat_level": "varies per program",
        "typical_payout_currency": "USDC, native token",
        "triage_time": "5-14 days",
        "max_critical": "$10M (Aave, Compound) typical $50k-$1M",
        "pros": "Highest payouts, established",
        "cons": "Whitehat level gating",
    },
    "hackerone": {
        "url": "https://hackerone.com/",
        "kyc": "tax forms required",
        "whitehat_level": "no explicit gate",
        "typical_payout_currency": "USD via PayPal/wire",
        "triage_time": "1-7 days",
        "max_critical": "Varies, $10k-$200k typical",
        "pros": "Faster triage, reputation building",
        "cons": "Lower payouts for web3",
    },
    "hackenproof": {
        "url": "https://hackenproof.com/",
        "kyc": "required",
        "whitehat_level": "reputation-based access",
        "typical_payout_currency": "USDC",
        "triage_time": "7-21 days",
        "max_critical": "$100k typical",
        "pros": "Russian-friendly",
        "cons": "Smaller programs",
    },
    "cantina": {
        "url": "https://cantina.xyz/",
        "kyc": "optional",
        "whitehat_level": "none",
        "typical_payout_currency": "USDC",
        "triage_time": "varies",
        "max_critical": "Varies; contests + bounty hybrid",
        "pros": "No gating, modern UI",
        "cons": "Smaller program count",
    },
    "sherlock_retro": {
        "url": "https://audits.sherlock.xyz/bug-bounties",
        "kyc": "required for payout",
        "whitehat_level": "none",
        "typical_payout_currency": "USDC",
        "triage_time": "varies",
        "max_critical": "Pre-defined per program",
        "pros": "Post-contest retro coverage",
        "cons": "Limited to Sherlock-audited protocols",
    },
    "direct": {
        "url": "protocol-specific security@",
        "kyc": "n/a",
        "whitehat_level": "n/a",
        "typical_payout_currency": "discretionary",
        "triage_time": "uncertain",
        "max_critical": "Depends on team generosity",
        "pros": "Always available",
        "cons": "No guarantee of payment",
    },
}


def decide(target_info: dict) -> dict:
    """Recommend platform based on what's available."""
    has_immunefi = target_info.get("has_immunefi", False)
    immunefi_whitehat_required = target_info.get("immunefi_whitehat_required", 0)
    our_whitehat_level = target_info.get("our_whitehat_level", 0)
    has_hackerone = target_info.get("has_hackerone", False)
    has_hackenproof = target_info.get("has_hackenproof", False)
    has_cantina = target_info.get("has_cantina", False)
    has_sherlock_retro = target_info.get("has_sherlock_retro", False)
    severity = target_info.get("severity", "Medium")

    recommendations = []
    if has_immunefi and our_whitehat_level >= immunefi_whitehat_required:
        recommendations.append({
            "platform": "immunefi",
            "reason": "Active program, our whitehat level sufficient",
            "priority": 1,
        })
    if has_cantina:
        recommendations.append({
            "platform": "cantina",
            "reason": "No gating, modern platform",
            "priority": 2,
        })
    if has_hackerone:
        recommendations.append({
            "platform": "hackerone",
            "reason": "Active program, fast triage",
            "priority": 3,
        })
    if has_sherlock_retro:
        recommendations.append({
            "platform": "sherlock_retro",
            "reason": "Sherlock-covered, retro bounty available",
            "priority": 3,
        })
    if has_hackenproof:
        recommendations.append({
            "platform": "hackenproof",
            "reason": "Russian-friendly platform",
            "priority": 4,
        })

    # Always include direct as last-resort
    recommendations.append({
        "platform": "direct",
        "reason": "Always available; use if no platform covers target",
        "priority": 99,
    })

    recommendations.sort(key=lambda r: r["priority"])

    return {
        "target": target_info,
        "recommendations": recommendations,
        "primary": recommendations[0]["platform"] if recommendations else "direct",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--target-info", help="JSON file with target info")
    p.add_argument("--severity", default="Medium")
    p.add_argument("--our-whitehat-level", type=int, default=0)
    p.add_argument("--output", default=".")
    args = p.parse_args()

    if args.target_info:
        info = json.loads(Path(args.target_info).read_text())
    else:
        info = {"severity": args.severity, "our_whitehat_level": args.our_whitehat_level}

    result = decide(info)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "submission_strategy.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"=== Submission Strategy ===")
    print(f"Primary: {result['primary']}")
    print()
    print("All recommendations:")
    for r in result["recommendations"]:
        info_p = PLATFORMS_INFO.get(r["platform"], {})
        print(f"  [{r['priority']}] {r['platform']}: {r['reason']}")
        print(f"      KYC: {info_p.get('kyc', '?')}, max critical: {info_p.get('max_critical', '?')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
