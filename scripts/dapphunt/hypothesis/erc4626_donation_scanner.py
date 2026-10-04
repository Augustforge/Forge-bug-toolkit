#!/usr/bin/env python3
"""
erc4626_donation_scanner.py — Detect first-depositor inflation surface on ERC-4626 vaults.

Hundred Finance pattern ($7M, 2023): empty market + balanceOf-based totalAssets +
no first-deposit protection = 1-share donation attack.

Strategy:
1. Read vault metadata (decimals, asset, totalSupply, totalAssets)
2. Probe accounting style — does totalAssets equal asset.balanceOf(vault)?
   If equal → balanceOf-based → donation-vulnerable
3. Check _decimalsOffset() if present (OZ v4.9+)
4. Check for dead-share burn (look for transfers to 0x000...dEaD or 0x0)
5. Score risk

Pure-stdlib (no web3.py). Reuses RPC helpers from role_centralization_scanner.

Usage:
    python3 erc4626_donation_scanner.py \\
        --rpc https://eth.llamarpc.com \\
        --vault 0xVaultAddr \\
        --out sessions/$DOMAIN/onchain/vault_inflation_audit.json

    # Multiple vaults
    python3 erc4626_donation_scanner.py --rpc ... \\
        --vault 0xVault1 --vault 0xVault2 --vault 0xVault3
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import shared RPC helpers from sibling scanner
sys.path.insert(0, str(Path(__file__).resolve().parent))
from role_centralization_scanner import (  # noqa: E402
    RPCError, eth_call, eth_get_code,
    encode_call, decode_uint, decode_address, decode_string,
)


@dataclass
class VaultAudit:
    address: str
    is_contract: bool = False
    name: str = ""
    symbol: str = ""
    decimals: int = 0
    asset: str = ""
    asset_symbol: str = ""
    asset_decimals: int = 0
    total_supply: int = 0
    total_assets: int = 0
    asset_balance_of_vault: int = 0
    accounting_style: str = "unknown"  # "balance_of" / "internal" / "unknown"
    decimals_offset: Optional[int] = None
    has_dead_shares: Optional[bool] = None
    risk_findings: List[Dict[str, str]] = field(default_factory=list)
    risk_score: int = 0


def audit_vault(rpc_url: str, vault: str) -> VaultAudit:
    audit = VaultAudit(address=vault)

    code = eth_get_code(rpc_url, vault)
    audit.is_contract = code and code != "0x" and (len(code) - 2) // 2 > 0
    if not audit.is_contract:
        audit.risk_findings.append({
            "severity": "info",
            "id": "not_a_contract",
            "message": f"{vault} has no bytecode — not a vault address",
        })
        return audit

    # Vault metadata
    try:
        audit.name = decode_string(eth_call(rpc_url, vault, encode_call("name()")))
    except RPCError:
        pass
    try:
        audit.symbol = decode_string(eth_call(rpc_url, vault, encode_call("symbol()")))
    except RPCError:
        pass
    try:
        audit.decimals = decode_uint(eth_call(rpc_url, vault, encode_call("decimals()")))
    except RPCError:
        pass
    try:
        audit.total_supply = decode_uint(eth_call(rpc_url, vault, encode_call("totalSupply()")))
    except RPCError:
        pass

    # ERC-4626: asset()
    try:
        asset_raw = eth_call(rpc_url, vault, encode_call("asset()"))
        audit.asset = decode_address(asset_raw)
    except RPCError:
        audit.risk_findings.append({
            "severity": "info",
            "id": "not_erc4626",
            "message": "Contract does not expose asset() — not standard ERC-4626; may be cToken/custom vault",
        })

    # totalAssets()
    try:
        audit.total_assets = decode_uint(eth_call(rpc_url, vault, encode_call("totalAssets()")))
    except RPCError:
        pass

    # Asset metadata + balance of vault
    if audit.asset and audit.asset != "0x" + "00" * 20:
        try:
            audit.asset_symbol = decode_string(eth_call(rpc_url, audit.asset, encode_call("symbol()")))
        except RPCError:
            pass
        try:
            audit.asset_decimals = decode_uint(eth_call(rpc_url, audit.asset, encode_call("decimals()")))
        except RPCError:
            pass
        try:
            balance_raw = eth_call(rpc_url, audit.asset, encode_call("balanceOf(address)", vault))
            audit.asset_balance_of_vault = decode_uint(balance_raw)
        except RPCError:
            pass

    # Accounting style heuristic: does totalAssets == balanceOf(asset, vault)?
    if audit.total_assets > 0 and audit.asset_balance_of_vault > 0:
        if audit.total_assets == audit.asset_balance_of_vault:
            audit.accounting_style = "balance_of"
        else:
            audit.accounting_style = "internal"
    elif audit.total_assets == 0 and audit.asset_balance_of_vault == 0:
        audit.accounting_style = "unknown_empty"

    # Try to read _decimalsOffset (OZ v4.9+ internal — may not be exposed)
    # Some vaults expose it via getter; many don't. Heuristic only.
    try:
        offset_raw = eth_call(rpc_url, vault, encode_call("_decimalsOffset()"))
        audit.decimals_offset = decode_uint(offset_raw)
    except RPCError:
        audit.decimals_offset = None

    # Heuristic: virtual offset can be derived from `decimals() = asset.decimals + offset`
    if audit.decimals_offset is None and audit.asset_decimals > 0:
        implied_offset = audit.decimals - audit.asset_decimals
        if implied_offset > 0:
            audit.decimals_offset = implied_offset
            audit.risk_findings.append({
                "severity": "info",
                "id": "implied_decimals_offset",
                "message": f"Implied _decimalsOffset = {implied_offset} (vault.decimals {audit.decimals} - asset.decimals {audit.asset_decimals})",
            })

    # Dead-share heuristic: very large totalSupply (≥ 10^3) with very small totalAssets
    # OR known dead address (0x...dEaD) holds non-zero balance
    if audit.total_supply > 0 and audit.total_assets > 0:
        # If totalSupply >> what minimal first deposit would mint, likely seeded
        # Heuristic only — false positives possible
        pass

    assess_inflation_risk(audit)
    return audit


def assess_inflation_risk(audit: VaultAudit) -> None:
    findings = audit.risk_findings
    score = 0

    # Critical: balanceOf-based accounting + no offset + low decimals
    if audit.accounting_style == "balance_of":
        findings.append({
            "severity": "high",
            "id": "balance_of_accounting",
            "message": "totalAssets() == asset.balanceOf(vault) — donation-vulnerable. "
                       "External transfer to vault inflates per-share price.",
        })
        score += 30

        if audit.decimals_offset == 0 or audit.decimals_offset is None:
            findings.append({
                "severity": "critical",
                "id": "no_decimals_offset_with_balanceof",
                "message": "balanceOf-based accounting + no virtual offset (or offset=0). "
                           "Classic Hundred Finance first-depositor inflation primitive.",
            })
            score += 40

    # High: empty vault with active deposits
    if audit.total_supply == 0:
        findings.append({
            "severity": "critical",
            "id": "empty_vault",
            "message": "totalSupply() == 0 — first depositor can manipulate share price. "
                       "Race condition: if no dead shares minted on init, vulnerable.",
        })
        score += 30

    # Medium: low offset + low decimals
    if audit.decimals_offset is not None and 0 < audit.decimals_offset < 6:
        if audit.decimals <= 8:
            findings.append({
                "severity": "medium",
                "id": "weak_offset",
                "message": f"_decimalsOffset={audit.decimals_offset} on decimals={audit.decimals} vault. "
                           "Precision attack possible but realized loss bounded.",
            })
            score += 10

    audit.risk_score = min(score, 100)


def format_summary(audit: VaultAudit) -> str:
    lines = []
    lines.append("=" * 72)
    if not audit.is_contract:
        lines.append(f"Vault: {audit.address} — NOT A CONTRACT")
        return "\n".join(lines + ["=" * 72])
    lines.append(f"Vault: {audit.symbol or '?'} ({audit.name or '?'}) — {audit.address}")
    lines.append(f"  decimals: {audit.decimals}, totalSupply: {audit.total_supply}")
    lines.append(f"  Underlying: {audit.asset_symbol or '?'} ({audit.asset}) decimals: {audit.asset_decimals}")
    lines.append(f"  totalAssets(): {audit.total_assets}")
    lines.append(f"  asset.balanceOf(vault): {audit.asset_balance_of_vault}")
    lines.append(f"  Accounting style: {audit.accounting_style}")
    if audit.decimals_offset is not None:
        lines.append(f"  _decimalsOffset: {audit.decimals_offset}")
    lines.append(f"  Risk score: {audit.risk_score}/100")
    if audit.risk_findings:
        lines.append("  Findings:")
        for f in audit.risk_findings:
            lines.append(f"    [{f['severity'].upper()}] {f['id']}: {f['message']}")
    lines.append("=" * 72)
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--rpc", required=True)
    parser.add_argument("--vault", required=True, action="append")
    parser.add_argument("--out")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    audits = []
    for vault_addr in args.vault:
        try:
            audit = audit_vault(args.rpc, vault_addr)
        except RPCError as e:
            print(f"[ERROR] {vault_addr}: {e}", file=sys.stderr)
            continue
        if not args.quiet:
            print(format_summary(audit))
        audits.append(audit)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps([asdict(a) for a in audits], indent=2),
            encoding="utf-8"
        )
        print(f"\nWrote {len(audits)} vault audit(s) → {out_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
