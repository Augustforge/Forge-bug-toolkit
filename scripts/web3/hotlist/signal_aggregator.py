#!/usr/bin/env python3
"""
signal_aggregator.py — Aggregate signals to score hunt targets.

Inputs (auto-pulled or manual):
- TVL change (DefiLlama)
- Recent commits (GitHub, suspicious patterns)
- New audit just published (Cantina, Code4rena)
- Deploy alerts (new contract on chain)
- Bounty program just launched/updated

Output: ranked list of targets with score.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def _days_since(iso_ts: str) -> int:
    """Days since an ISO-8601 timestamp. Returns 999 if unparseable."""
    if not iso_ts:
        return 999
    try:
        ts = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - ts).days)
    except (ValueError, TypeError):
        return 999


def detect_chain(target_name: str, address: str = "", repo_path: str = "") -> tuple[str, str]:
    """Detect chain + chain_prefix from target identifiers.

    Returns (chain, chain_prefix). chain in {"evm", "solana"}. chain_prefix in {"eth:", "bsc:", "arbitrum:", "sol:", ...}.
    """
    name = target_name.lower()
    addr = address.lower()

    sol_keywords = ["solana", "sol", "anchor", "marinade", "jito", "phoenix", "openbook",
                    "raydium", "orca", "kamino", "marginfi", "drift", "jupiter", "wormhole-sol",
                    "loopscale", "mango", "squads", "sanctum", "pump.fun", "helius"]
    for kw in sol_keywords:
        if kw in name:
            return ("solana", "sol:")

    if addr.startswith("sol:") or addr.startswith("solana:"):
        return ("solana", "sol:")
    if len(addr) == 44 and not addr.startswith("0x"):
        return ("solana", "sol:")

    if addr.startswith("eth:") or addr.startswith("0x"):
        return ("evm", "eth:")
    if addr.startswith("bsc:"):
        return ("evm", "bsc:")
    if addr.startswith("arbitrum:") or addr.startswith("arb:"):
        return ("evm", "arbitrum:")
    if addr.startswith("polygon:"):
        return ("evm", "polygon:")
    if addr.startswith("base:"):
        return ("evm", "base:")
    if addr.startswith("optimism:") or addr.startswith("op:"):
        return ("evm", "optimism:")

    return ("evm", "eth:")


def score_target(signals: dict) -> dict:
    """Score a target based on aggregated signals."""
    score = 0
    reasons = []

    # TVL change
    tvl_change_pct = signals.get("tvl_change_pct_30d", 0)
    if tvl_change_pct > 50:
        score += 30
        reasons.append(f"TVL grew +{tvl_change_pct}% in 30d")
    elif tvl_change_pct > 20:
        score += 15
        reasons.append(f"TVL grew +{tvl_change_pct}% in 30d")

    # Recent commits with suspicious patterns
    suspicious_commits = signals.get("suspicious_commits_count", 0)
    if suspicious_commits > 5:
        score += 25
        reasons.append(f"{suspicious_commits} suspicious fix-commits recently")
    elif suspicious_commits > 0:
        score += 10
        reasons.append(f"{suspicious_commits} suspicious commits")

    # New audit
    audit_age_days = signals.get("audit_age_days", 999)
    if audit_age_days <= 7:
        score += 20
        reasons.append(f"Audit published {audit_age_days}d ago — fresh code post-audit")

    # Bounty program
    if signals.get("bounty_program_new", False):
        score += 20
        reasons.append("Bounty program new (first to find)")

    # Payout — accept toolkit-native key plus immunefi (max_bounty) / cantina (max_payout_usd) aliases
    bounty_payout = (signals.get("bounty_critical_payout_usd")
                     or signals.get("max_payout_usd")
                     or signals.get("max_bounty")
                     or 0)
    if bounty_payout >= 1_000_000:
        score += 25
        reasons.append(f"Critical payout ≥ ${bounty_payout:,.0f}")
    elif bounty_payout >= 100_000:
        score += 15
        reasons.append(f"Critical payout ≥ ${bounty_payout:,.0f}")
    elif bounty_payout >= 25_000:
        score += 5
        reasons.append(f"Payout ${bounty_payout:,.0f}")

    # Program status (cantina sitemap): Live/Active = confirmed open, null = unknown
    status = (signals.get("status") or "").lower()
    if status in ("live", "active"):
        score += 10
        reasons.append(f"Program status: {status}")

    # Deploy / launch freshness. Accept explicit deploy_age_days, else derive from
    # launch_date (immunefi — real). cantina lastmod is a sitemap snapshot (uniform
    # across all entries) so it is NOT used as a freshness signal here.
    deploy_age_days = signals.get("deploy_age_days")
    if deploy_age_days is None and signals.get("launch_date"):
        deploy_age_days = _days_since(signals["launch_date"])
        if deploy_age_days <= 30:
            reasons.append("Bounty just launched (first to find)")
    if deploy_age_days is None:
        deploy_age_days = 999
    if deploy_age_days <= 30:
        score += 25
        reasons.append(f"Launched {deploy_age_days}d ago — fresh code")
    elif deploy_age_days <= 90:
        score += 10

    # Accessibility
    if signals.get("immunefi_whitehat_required", 0) > signals.get("our_whitehat_level", 0):
        score -= 50
        reasons.append("⚠️ Whitehat level insufficient — gated")
    if signals.get("kyc_required", False) and not signals.get("kyc_passed", False):
        score -= 20
        reasons.append("⚠️ KYC required but not completed")

    return {"score": score, "reasons": reasons}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--targets-file", required=True, help="JSON file with list of {name, signals}")
    p.add_argument("--output", default=".")
    p.add_argument("--top", type=int, default=10)
    args = p.parse_args()

    targets = json.loads(Path(args.targets_file).read_text())

    scored = []
    for t in targets:
        result = score_target(t.get("signals", {}))
        chain = t.get("chain")
        chain_prefix = t.get("chain_prefix")
        if not chain or not chain_prefix:
            detected_chain, detected_prefix = detect_chain(
                t.get("name", ""),
                t.get("address", ""),
                t.get("repo_path", ""),
            )
            chain = chain or detected_chain
            chain_prefix = chain_prefix or detected_prefix
        scored.append({
            "name": t["name"],
            "chain": chain,
            "chain_prefix": chain_prefix,
            "address": t.get("address", ""),
            "source": t.get("source", ""),
            "url": t.get("url", ""),
            "score": result["score"],
            "reasons": result["reasons"],
            "signals": t.get("signals", {}),
        })

    scored.sort(key=lambda x: -x["score"])

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "hotlist.json").write_text(json.dumps(scored, indent=2), encoding="utf-8")

    print(f"=== Hot List (top {args.top}) ===")
    for s in scored[:args.top]:
        print(f"\n{s['name']} — score {s['score']}")
        for r in s["reasons"]:
            print(f"  - {r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
