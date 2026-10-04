#!/usr/bin/env python3
"""
_dapphunt_lessons.py — dApp-hunt-specific calibration / lessons aggregator.

This is the dapphunt analog of `_methodology/failure_analysis.py recurring`. It
filters the shared calibration log to dapphunt-class entries, groups them by
hypothesis class, and emits both:

  - `sessions/_methodology/dapphunt_weights.json` — class → win-rate / cost / severity
  - `sessions/_methodology/dapphunt_lessons.md`   — human-readable lessons digest

Hypothesis classes tracked (auto-detected from the entry's `class` array):

  auth_provider_wildcard   — wildcard in Privy/Magic/WC allowed_domains / redirect_uri
  iframe_trust             — X-Frame-Options / frame-ancestors composition
  dapp_clone               — dev/staging/prod asymmetry under shared auth
  postmessage_origin       — missing or weak origin validation in postMessage
  wallet_metadata_xss      — WC peer.metadata.* rendered without sanitize
  tokenlist_cdn            — CDN-hosted tokenlist trust expansion
  dns_takeover_wildcard    — dangling CNAME under wildcard auth allowlist
  siwe_replay              — SIWE/SIWS nonce / domain / expiration issues
  display_vs_reality       — UI assertion vs on-chain reality gap
  eip712_chain_replay      — chainId hardcoded in EIP-712 typed data
  eip7702_authorization    — Pectra set-code authorization handed to user as "connect"

Usage:
    py -3 -X utf8 _dapphunt_lessons.py recurring
    py -3 -X utf8 _dapphunt_lessons.py weights --output sessions/_methodology/dapphunt_weights.json
    py -3 -X utf8 _dapphunt_lessons.py classify-from-calibration   # one-shot bulk re-classify
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple


THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parent.parent
CALIBRATION_LOG = REPO_ROOT / "sessions" / "_methodology" / "calibration_log.jsonl"
WEIGHTS_OUT = REPO_ROOT / "sessions" / "_methodology" / "dapphunt_weights.json"
LESSONS_MD = REPO_ROOT / "sessions" / "_methodology" / "dapphunt_lessons.md"


# Hypothesis class → keywords that, if present in calibration entry's `class` array,
# tag the entry as belonging to that class. Multiple matches → entry counts for each.
_CLASS_KEYWORDS: Dict[str, List[str]] = {
    "auth_provider_wildcard": [
        "auth-provider-wildcard", "privy-wildcard", "magic-wildcard",
        "allowed-domains-wildcard", "auth-wildcard",
    ],
    "iframe_trust": [
        "iframe-trust", "frame-ancestors", "x-frame-options", "clickjacking",
        "iframe-composition",
    ],
    "dapp_clone": [
        "dapp-clone", "dev-clone", "staging-clone", "clone-asymmetry",
    ],
    "postmessage_origin": [
        "postmessage", "origin-validation", "postmessage-origin",
    ],
    "wallet_metadata_xss": [
        "wallet-metadata-xss", "peer-metadata", "eip6963-info",
    ],
    "tokenlist_cdn": [
        "tokenlist-cdn", "tokenlist-takeover", "cdn-poisoning",
    ],
    "dns_takeover_wildcard": [
        "dns-takeover", "dangling-cname", "subdomain-takeover-wildcard",
    ],
    "siwe_replay": [
        "siwe-replay", "siws-replay", "siwe-nonce", "siwe-domain-spoof",
    ],
    "display_vs_reality": [
        "display-vs-reality", "ui-lies", "ui-vs-onchain", "gas-display",
        "slippage-display", "blocklist-ui",
    ],
    "eip712_chain_replay": [
        "eip712-chain-replay", "chainid-hardcoded", "cross-chain-replay",
    ],
    "eip7702_authorization": [
        "eip7702", "set-code", "pectra-auth", "authorization-list",
    ],
    "compromised_admin_mint": [
        "compromised-admin", "unconstrained-mint", "minter-eoa",
        "admin-key-compromise", "no-supply-cap", "echo-pattern",
    ],
    "cross_protocol_collateral_trust": [
        "cross-protocol-collateral", "wrapped-collateral-trust",
        "no-backing-oracle", "unverified-collateral", "lending-amplifier",
    ],
    "bridge_admin_compromise": [
        "bridge-admin-compromise", "validator-set-compromise",
        "bridge-mint-authority", "trusted-relayer-compromise",
        "message-replay-bridge",
    ],
    "erc4626_inflation": [
        "erc4626-inflation", "vault-donation", "first-depositor-attack",
        "share-price-manipulation", "compound-empty-market", "hundred-pattern",
    ],
    "permit2_phishing": [
        "permit2-phish", "permit-spender", "blind-permit", "permit2-clone",
        "permit-batch-phish", "eip2612-phish",
    ],
    "proxy_reinit_collision": [
        "proxy-reinit", "implementation-hijack", "storage-collision",
        "wormhole-pattern", "audius-pattern", "uups-takeover",
        "uninitialized-implementation",
    ],
    "erc4337_paymaster": [
        "paymaster-grief", "paymaster-replay", "userop-replay",
        "bundler-censorship", "aa-validation-violation",
        "paymaster-deposit-drain",
    ],
    "composite_chain": [
        "composite-hypothesis", "chain-of-threats", "h1-unconstrained-minter",
        "h2-clone-permit2", "h3-wormhole-pattern", "h4-hundred-pattern",
        "h5-7702-takeover", "h6-bridge-validator", "h7-oracle-manip",
        "h8-audit-drift", "h9-paymaster-replay", "h10-fresh-chain",
    ],
    "behavioral_opsec": [
        "behavioral", "opsec", "key-rotation", "doxxed-mismatch",
        "audit-drift", "scope-omission",
    ],
    "fresh_chain_velocity": [
        "fresh-chain", "monad", "berachain", "hyperliquid", "new-l1",
        "new-l2", "young-protocol", "early-deploy",
    ],
    "ghost_contract_drain": [
        "ghost-contract", "deprecated-alive", "legacy-approval-drain",
        "transit-pattern", "abandoned-router", "renounced-no-pause",
        "h11-multi-chain-ghost",
    ],
    "arbitrary_call_aggregator": [
        "arbitrary-call", "callbytes", "router-arbitrary-call",
        "dex-aggregator-drain", "swapnet-pattern", "aperture-pattern",
        "transit-2022", "h12-dex-aggregator-arbitrary-call",
    ],
    "multi_chain_deploy_enumeration": [
        "multi-version-enum", "multi-chain-enum", "v1-v2-v3-drift",
        "chain-pause-inconsistency", "deploy-history-mining",
    ],
}


def _load_calibration() -> List[dict]:
    if not CALIBRATION_LOG.exists():
        return []
    entries: List[dict] = []
    for line in CALIBRATION_LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def _entry_classes(entry: dict) -> List[str]:
    """Return hypothesis-class buckets this entry belongs to."""
    raw_classes = entry.get("class") or []
    if isinstance(raw_classes, str):
        raw_classes = [raw_classes]
    raw_lower = [c.lower() for c in raw_classes]
    hits: List[str] = []
    for bucket, keywords in _CLASS_KEYWORDS.items():
        if any(kw in raw_lower or any(kw in c for c in raw_lower) for kw in keywords):
            hits.append(bucket)
    return hits


def _outcome_is_confirmed(outcome: str) -> bool:
    if not outcome:
        return False
    return outcome.upper().startswith("TRUE")


def _outcome_is_refuted(outcome: str) -> bool:
    if not outcome:
        return False
    return outcome.upper().startswith("FALSE")


def aggregate() -> Dict[str, dict]:
    """Compute per-class win-rate / cost / severity weights."""
    entries = _load_calibration()
    per_class: Dict[str, List[dict]] = defaultdict(list)
    for e in entries:
        for cls in _entry_classes(e):
            per_class[cls].append(e)

    weights: Dict[str, dict] = {}
    for cls, items in per_class.items():
        confirmed = [e for e in items if _outcome_is_confirmed(e.get("outcome", ""))]
        refuted = [e for e in items if _outcome_is_refuted(e.get("outcome", ""))]
        paid = [e for e in confirmed if (e.get("payout_usd") or 0) > 0]

        costs = [e.get("actual_cost_hours") for e in items if isinstance(e.get("actual_cost_hours"), (int, float))]
        avg_cost = round(statistics.mean(costs), 2) if costs else None
        severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
        sev_values = [
            severity_rank.get(str(e.get("preflight_severity_ceiling", "")).lower(), 0)
            for e in items
        ]
        avg_sev_rank = round(statistics.mean(sev_values), 2) if sev_values else 0
        avg_sev_label = {4: "critical", 3: "high", 2: "medium", 1: "low", 0: "info"}.get(round(avg_sev_rank), "info")

        win_rate = round(len(confirmed) / max(1, len(items)), 2)
        pay_rate = round(len(paid) / max(1, len(confirmed)), 2) if confirmed else 0.0

        # Recommendation logic
        if len(items) < 3:
            rec = "INSUFFICIENT_DATA"
        elif win_rate >= 0.6 and avg_cost is not None and avg_cost <= 6:
            rec = "STRONG_HUNT"
        elif win_rate >= 0.4:
            rec = "CONTINUE"
        elif len(refuted) >= 3 and win_rate < 0.2:
            rec = "REDUCE_PRIORITY"
        else:
            rec = "OBSERVE"

        weights[cls] = {
            "tries": len(items),
            "confirmed": len(confirmed),
            "refuted": len(refuted),
            "paid": len(paid),
            "win_rate": win_rate,
            "pay_rate": pay_rate,
            "avg_cost_hours": avg_cost,
            "avg_severity_rank": avg_sev_rank,
            "avg_severity_label": avg_sev_label,
            "recommendation": rec,
            "last_targets": sorted({e.get("target", "") for e in items[-5:]}),
        }
    return weights


def render_markdown(weights: Dict[str, dict]) -> str:
    lines: List[str] = []
    lines.append("# dapphunt — class-level lessons")
    lines.append("")
    lines.append("Auto-generated by `scripts/dapphunt/_dapphunt_lessons.py`. Reads")
    lines.append("`sessions/_methodology/calibration_log.jsonl`, buckets entries into")
    lines.append("hypothesis classes, and surfaces per-class win-rate + cost + severity.")
    lines.append("")
    lines.append("Use this when triaging hypotheses in Phase 2.5 — REDUCE_PRIORITY classes")
    lines.append("should be down-weighted; STRONG_HUNT classes should be tried first.")
    lines.append("")
    if not weights:
        lines.append("_No dapphunt-tagged entries in the calibration log yet._")
        lines.append("")
        lines.append("Tag entries with class keywords from `_CLASS_KEYWORDS` to populate.")
        return "\n".join(lines)

    lines.append("| Class | Tries | Confirmed | Refuted | Paid | Win | Pay | Avg cost (h) | Avg sev | Recommendation |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---|---|")
    for cls, w in sorted(weights.items(), key=lambda kv: (-kv[1]["confirmed"], -kv[1]["tries"])):
        lines.append(
            f"| {cls} | {w['tries']} | {w['confirmed']} | {w['refuted']} | "
            f"{w['paid']} | {w['win_rate']} | {w['pay_rate']} | "
            f"{w['avg_cost_hours'] if w['avg_cost_hours'] is not None else '—'} | "
            f"{w['avg_severity_label']} | {w['recommendation']} |"
        )
    lines.append("")
    lines.append("## Per-class detail")
    for cls, w in sorted(weights.items()):
        lines.append(f"### {cls}")
        lines.append(f"- Tries: {w['tries']}, confirmed: {w['confirmed']}, refuted: {w['refuted']}, paid: {w['paid']}")
        lines.append(f"- Win rate: {w['win_rate']} | Pay-after-confirm rate: {w['pay_rate']}")
        lines.append(f"- Avg cost: {w['avg_cost_hours']}h | Avg severity ceiling: {w['avg_severity_label']}")
        lines.append(f"- Recommendation: **{w['recommendation']}**")
        lines.append(f"- Recent targets: {', '.join(t for t in w['last_targets'] if t)}")
        lines.append("")
    return "\n".join(lines)


def cmd_weights(args) -> int:
    weights = aggregate()
    out = args.output or WEIGHTS_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(weights, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(weights)} class weights → {out}")
    md_path = LESSONS_MD if not args.markdown_output else args.markdown_output
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(weights), encoding="utf-8")
    print(f"Wrote markdown digest → {md_path}")
    return 0


def cmd_recurring(args) -> int:
    """Print classes with 3+ refutations / 3+ confirmations to surface stable patterns."""
    weights = aggregate()
    interesting = [
        (cls, w) for cls, w in weights.items()
        if w["refuted"] >= 3 or w["confirmed"] >= 3
    ]
    if not interesting:
        print("No recurring classes yet — need ≥3 confirmed or ≥3 refuted in any class.")
        return 0
    for cls, w in sorted(interesting, key=lambda kv: -kv[1]["confirmed"]):
        flag = "🟢" if w["recommendation"] == "STRONG_HUNT" else ("🔴" if w["recommendation"] == "REDUCE_PRIORITY" else "🟡")
        # Use ASCII only because the user prefers no emojis in code; keep these inline labels minimal
        flag = "[+]" if w["recommendation"] == "STRONG_HUNT" else ("[-]" if w["recommendation"] == "REDUCE_PRIORITY" else "[~]")
        print(f"{flag} {cls}: {w['confirmed']} confirmed / {w['refuted']} refuted / win={w['win_rate']} | rec={w['recommendation']}")
    return 0


def cmd_classify_from_calibration(args) -> int:
    """Show which calibration entries fall into which dapphunt class. Read-only sanity check."""
    entries = _load_calibration()
    matched = 0
    for e in entries:
        classes = _entry_classes(e)
        if not classes:
            continue
        matched += 1
        target = e.get("target", "?")
        ents_outcome = e.get("outcome", "?")
        print(f"  {target:30s}  classes={classes}  outcome={ents_outcome}")
    print()
    print(f"Matched {matched}/{len(entries)} calibration entries into dapphunt classes.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_w = sub.add_parser("weights", help="Compute per-class win-rate / cost / severity weights")
    p_w.add_argument("--output", type=Path)
    p_w.add_argument("--markdown-output", type=Path)
    p_w.set_defaults(func=cmd_weights)

    p_r = sub.add_parser("recurring", help="Show classes with 3+ confirmed or 3+ refuted")
    p_r.set_defaults(func=cmd_recurring)

    p_c = sub.add_parser("classify-from-calibration", help="Sanity check: which entries fall into which class")
    p_c.set_defaults(func=cmd_classify_from_calibration)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
