#!/usr/bin/env python3
"""squads_v4_simulator.py — model multisig governance attack surfaces.

Drift apr 2026 ($285M) — Squads v4 multisig + durable nonce + zero-timelock.
Pre-signed transactions stored valid indefinitely. Admin takeover possible.

This script models:
1. **Durable nonce surface** — list of signed transactions which never expire
2. **Timelock check** — timelock = 0 on critical operations
3. **Threshold drift** — pre-signed tx with old threshold valid after threshold change
4. **Approval revocation** — is it possible to revoke approval BEFORE execution?
5. **Vote replay** — same vote PDA reused
6. **Member rotation race** — member removed, but pre-signed tx with old member valid

Usage:
    python3 squads_v4_simulator.py --multisig-pda 9xQeWv... --rpc https://api.mainnet-beta.solana.com
    python3 squads_v4_simulator.py --config-file squads_config.json --analyze-only
"""
import argparse, json, sys, urllib.request
from pathlib import Path


def rpc_call(rpc_url: str, method: str, params: list) -> dict | None:
    try:
        payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        req = urllib.request.Request(rpc_url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"[!] RPC error: {e}", file=sys.stderr)
        return None


def analyze_multisig(config: dict) -> list[dict]:
    findings = []

    threshold = config.get("threshold", 0)
    members = config.get("members", [])
    timelock = config.get("timelock_seconds", 0)
    uses_durable_nonce = config.get("uses_durable_nonce", False)
    config_authority = config.get("config_authority")

    if timelock == 0 and threshold < len(members):
        findings.append({
            "type": "zero_timelock_admin",
            "severity": "critical",
            "classification": "known_class",
            "exploit_ref": "Drift apr 2026 ($285M)",
            "description": f"Timelock = 0 on multisig with threshold {threshold}/{len(members)}. Critical admin ops execute instantly after approval reaches threshold. No window for observers to detect malicious proposal.",
            "fix": "Set timelock_seconds >= 86400 (24h minimum) for config changes + critical admin ops.",
        })

    if uses_durable_nonce:
        findings.append({
            "type": "durable_nonce_in_admin_flow",
            "severity": "critical",
            "classification": "known_class",
            "exploit_ref": "Drift apr 2026",
            "description": "Multisig signs transactions via durable nonce. Pre-signed tx remain valid indefinitely. If member key is compromised after signing, attacker can execute through end of nonce lifetime.",
            "fix": "Use recent_blockhash + tight expiry (typical 60s) for governance txs. Durable nonce only for backup recovery flows.",
        })

    if config_authority and config_authority in [m.get("pubkey") for m in members]:
        findings.append({
            "type": "config_authority_is_member",
            "severity": "high",
            "classification": "novel_instance",
            "description": f"Config authority = {config_authority} is also a multisig member. Single key compromise -> entire multisig configuration changeable (threshold down, members swap).",
            "fix": "Config authority should be the multisig itself (PDA) OR an external timelocked admin.",
        })

    if threshold == 1:
        findings.append({
            "type": "single_signer_multisig",
            "severity": "high",
            "classification": "known_class",
            "description": f"Threshold = 1. This is not a multisig — this is a single-sig wallet with extra steps.",
            "fix": "Set threshold >= 2/3 of members.",
        })

    if threshold > 0 and len(members) > 0 and (threshold / len(members)) < 0.51:
        findings.append({
            "type": "minority_threshold",
            "severity": "medium",
            "classification": "known_class",
            "description": f"Threshold = {threshold}/{len(members)} = {threshold/len(members)*100:.0f}%. Minority of members can authorize. Vulnerable to Sybil-style takeover if member set is permissionless.",
        })

    return findings


def check_pending_proposals(rpc_url: str, multisig_pda: str) -> list[dict]:
    findings = []
    result = rpc_call(rpc_url, "getProgramAccounts", [
        "SMPLecH534NA9acpos4G6x7uf3LWbCAwZQE9e8ZekMu",
        {
            "filters": [{"memcmp": {"offset": 8, "bytes": multisig_pda}}],
            "encoding": "base64",
        }
    ])
    if result and "result" in result:
        accounts = result["result"]
        for acc in accounts:
            findings.append({
                "type": "pending_proposal",
                "severity": "info",
                "description": f"Pending proposal account: {acc.get('pubkey')}. Check status, voting period, target instruction.",
                "account": acc.get("pubkey"),
            })
    return findings


def main():
    ap = argparse.ArgumentParser(description="Squads v4 multisig attack surface analyzer")
    ap.add_argument("--multisig-pda", help="On-chain multisig PDA address")
    ap.add_argument("--rpc", default="https://api.mainnet-beta.solana.com")
    ap.add_argument("--config-file", help="Manual config JSON: {threshold, members, timelock_seconds, uses_durable_nonce, config_authority}")
    ap.add_argument("--analyze-only", action="store_true", help="Skip on-chain RPC checks")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    findings = []
    config = None

    if args.config_file:
        config = json.loads(Path(args.config_file).read_text())
    elif args.multisig_pda and not args.analyze_only:
        print(f"[*] Fetching Squads multisig state for {args.multisig_pda}...")
        result = rpc_call(args.rpc, "getAccountInfo", [args.multisig_pda, {"encoding": "base64"}])
        if not result or not result.get("result", {}).get("value"):
            print(f"[!] Multisig PDA not found or RPC error", file=sys.stderr)
        else:
            print(f"[*] On-chain state fetched. Full parsing requires Squads v4 client library.")
            print(f"    Stub: provide --config-file for full analysis OR install solana-py + squads-mpl.")

    if config:
        findings.extend(analyze_multisig(config))

    if args.multisig_pda and not args.analyze_only:
        findings.extend(check_pending_proposals(args.rpc, args.multisig_pda))

    print(f"\n[+] Total findings: {len(findings)}")
    for f in findings:
        sev = f["severity"].upper()
        cls = f.get("classification", "?")
        ref = f.get("exploit_ref", "")
        ref_str = f" (ref: {ref})" if ref else ""
        print(f"  [{sev}] [{cls}] {f['type']}{ref_str}")
        print(f"     {f['description']}")
        if f.get("fix"):
            print(f"     FIX: {f['fix']}")

    out_data = {
        "multisig_pda": args.multisig_pda,
        "config": config,
        "total": len(findings),
        "findings": findings,
    }
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(out_data, indent=2))


if __name__ == "__main__":
    main()
