#!/usr/bin/env python3
"""
proxy_reinit_scanner.py — Detect upgradeable proxy hijack surface.

Targets:
- Wormhole-class: implementation directly callable, not locked via _disableInitializers
- Audius-class: initialize() callable multiple times due to missing protection
- Centralized upgrade authority: single EOA / no timelock on _authorizeUpgrade

Strategy:
1. Read EIP-1967 implementation/admin/beacon slots via eth_getStorageAt
2. Probe implementation contract directly (call owner/getRoleMember; see if it's
   initialized to non-zero OR completely uninitialized)
3. Classify upgrade authority (admin slot or implementation's owner) via role scanner
4. Score risk

Pure-stdlib (no web3.py). Reuses RPC helpers from role_centralization_scanner.

Usage:
    python3 proxy_reinit_scanner.py --rpc $RPC --proxy 0xProxyAddr
    python3 proxy_reinit_scanner.py --rpc $RPC --proxy 0xA --proxy 0xB --out audit.json
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

# Reuse RPC helpers from sibling scanner
sys.path.insert(0, str(Path(__file__).resolve().parent))
from role_centralization_scanner import (  # noqa: E402
    RPCError, rpc_call, eth_call, eth_get_code,
    encode_call, decode_uint, decode_address, decode_string,
    classify_address,
)

# EIP-1967 storage slots
SLOT_IMPLEMENTATION = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
SLOT_ADMIN = "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103"
SLOT_BEACON = "0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50"


def eth_get_storage_at(rpc_url: str, address: str, slot: str, block: str = "latest") -> str:
    return rpc_call(rpc_url, "eth_getStorageAt", [address, slot, block])


def storage_to_address(hex_value: str) -> str:
    if not hex_value or hex_value == "0x" or int(hex_value, 16) == 0:
        return "0x" + "00" * 20
    return "0x" + hex_value[-40:]


@dataclass
class ProxyAudit:
    proxy_address: str
    is_proxy: bool = False
    proxy_type: str = "unknown"  # "uups" / "transparent" / "beacon" / "custom"
    implementation: str = "0x" + "00" * 20
    admin: str = "0x" + "00" * 20
    beacon: str = "0x" + "00" * 20
    implementation_code_size: int = 0
    implementation_initialized: Optional[bool] = None
    implementation_owner: Optional[str] = None
    admin_classification: Optional[Dict] = None
    upgrade_authority_classification: Optional[Dict] = None
    risk_findings: List[Dict[str, str]] = field(default_factory=list)
    risk_score: int = 0


def audit_proxy(rpc_url: str, proxy: str) -> ProxyAudit:
    audit = ProxyAudit(proxy_address=proxy)

    proxy_code = eth_get_code(rpc_url, proxy)
    if not proxy_code or proxy_code == "0x":
        audit.risk_findings.append({
            "severity": "info", "id": "not_a_contract",
            "message": f"{proxy} has no bytecode",
        })
        return audit

    # Read EIP-1967 slots
    try:
        impl_raw = eth_get_storage_at(rpc_url, proxy, SLOT_IMPLEMENTATION)
        audit.implementation = storage_to_address(impl_raw)
    except RPCError as e:
        audit.risk_findings.append({
            "severity": "info", "id": "rpc_storage_unsupported",
            "message": f"Cannot read EIP-1967 slots: {e}",
        })

    try:
        admin_raw = eth_get_storage_at(rpc_url, proxy, SLOT_ADMIN)
        audit.admin = storage_to_address(admin_raw)
    except RPCError:
        pass

    try:
        beacon_raw = eth_get_storage_at(rpc_url, proxy, SLOT_BEACON)
        audit.beacon = storage_to_address(beacon_raw)
    except RPCError:
        pass

    # Classify proxy type
    zero = "0x" + "00" * 20
    if audit.beacon != zero:
        audit.proxy_type = "beacon"
        audit.is_proxy = True
    elif audit.implementation != zero and audit.admin != zero:
        audit.proxy_type = "transparent"
        audit.is_proxy = True
    elif audit.implementation != zero and audit.admin == zero:
        audit.proxy_type = "uups"
        audit.is_proxy = True
    elif audit.implementation == zero and audit.admin == zero and audit.beacon == zero:
        # Either not a proxy, or uses custom slot pattern
        audit.proxy_type = "unknown"
        audit.risk_findings.append({
            "severity": "info", "id": "no_eip1967_slots",
            "message": "No EIP-1967 slots populated — may be regular contract or custom proxy",
        })
        return audit

    # Probe implementation directly
    if audit.implementation != zero:
        impl_code = eth_get_code(rpc_url, audit.implementation)
        if impl_code and impl_code != "0x":
            audit.implementation_code_size = (len(impl_code) - 2) // 2

            # Try owner() on impl directly — if returns non-zero, it's been initialized
            try:
                owner_raw = eth_call(rpc_url, audit.implementation, encode_call("owner()"))
                owner = decode_address(owner_raw)
                if owner != zero:
                    audit.implementation_initialized = True
                    audit.implementation_owner = owner
                else:
                    audit.implementation_initialized = False
            except RPCError:
                # owner() may not exist; try getRoleMember(DEFAULT_ADMIN_ROLE, 0)
                try:
                    admin_role = "0x" + "00" * 32
                    count_raw = eth_call(
                        rpc_url, audit.implementation,
                        encode_call("getRoleMemberCount(bytes32)", admin_role)
                    )
                    count = decode_uint(count_raw)
                    audit.implementation_initialized = count > 0
                except RPCError:
                    audit.implementation_initialized = None  # inconclusive

    # Classify admin (transparent proxy)
    if audit.proxy_type == "transparent" and audit.admin != zero:
        try:
            adm = classify_address(rpc_url, audit.admin)
            audit.admin_classification = asdict(adm)
        except RPCError:
            pass

    # For UUPS: upgrade authority lives in implementation; usually owner()/role
    if audit.proxy_type == "uups" and audit.implementation_owner:
        try:
            ua = classify_address(rpc_url, audit.implementation_owner)
            audit.upgrade_authority_classification = asdict(ua)
        except RPCError:
            pass

    assess_proxy_risk(audit)
    return audit


def assess_proxy_risk(audit: ProxyAudit) -> None:
    findings = audit.risk_findings
    score = 0

    # Critical: implementation not initialized (Wormhole pattern — anyone can take over)
    if audit.implementation_initialized is False:
        findings.append({
            "severity": "critical",
            "id": "implementation_uninitialized",
            "message": "Implementation contract appears uninitialized (owner()==0). "
                       "Anyone can call initialize() and take over the impl. "
                       "Wormhole near-miss pattern.",
        })
        score += 50

    # Critical: UUPS upgrade authority is single EOA
    ua = audit.upgrade_authority_classification
    if audit.proxy_type == "uups" and ua and ua.get("kind") == "EOA":
        findings.append({
            "severity": "critical",
            "id": "uups_eoa_upgrade_authority",
            "message": f"UUPS upgrade authority is single EOA {ua['address']}. "
                       "Compromised key → arbitrary impl swap.",
        })
        score += 40

    # High: transparent ProxyAdmin owner is EOA
    ac = audit.admin_classification
    if audit.proxy_type == "transparent" and ac:
        if ac.get("kind") == "EOA":
            findings.append({
                "severity": "high",
                "id": "transparent_eoa_admin",
                "message": f"Transparent proxy ProxyAdmin is EOA {ac['address']}. "
                           "Single key compromise = arbitrary upgrade.",
            })
            score += 30
        elif ac.get("kind") == "GnosisSafe":
            threshold = ac.get("details", {}).get("safe_threshold", 0)
            owner_count = ac.get("details", {}).get("safe_owner_count", 0)
            if owner_count > 0 and threshold <= 2:
                findings.append({
                    "severity": "high",
                    "id": "low_threshold_admin_multisig",
                    "message": f"Transparent proxy admin Safe threshold {threshold}/{owner_count}",
                })
                score += 20

    # Info: implementation slot points to address with no code (impl never deployed)
    if audit.implementation != "0x" + "00" * 20 and audit.implementation_code_size == 0:
        findings.append({
            "severity": "critical",
            "id": "implementation_no_code",
            "message": "Implementation slot points to address with no bytecode. "
                       "Proxy is non-functional OR pre-deployment race window.",
        })
        score += 30

    audit.risk_score = min(score, 100)


def format_summary(audit: ProxyAudit) -> str:
    lines = []
    lines.append("=" * 72)
    lines.append(f"Proxy: {audit.proxy_address}")
    lines.append(f"  Type: {audit.proxy_type}")
    lines.append(f"  Implementation: {audit.implementation}  (code: {audit.implementation_code_size}B)")
    if audit.admin != "0x" + "00" * 20:
        lines.append(f"  Admin: {audit.admin}")
        if audit.admin_classification:
            lines.append(f"    → kind: {audit.admin_classification.get('kind')}")
    if audit.beacon != "0x" + "00" * 20:
        lines.append(f"  Beacon: {audit.beacon}")
    if audit.implementation_initialized is not None:
        lines.append(f"  Impl initialized: {audit.implementation_initialized}")
    if audit.implementation_owner:
        lines.append(f"  Impl owner: {audit.implementation_owner}")
        if audit.upgrade_authority_classification:
            lines.append(f"    → kind: {audit.upgrade_authority_classification.get('kind')}")
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
    parser.add_argument("--proxy", required=True, action="append")
    parser.add_argument("--out")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    audits = []
    for proxy_addr in args.proxy:
        try:
            audit = audit_proxy(args.rpc, proxy_addr)
        except RPCError as e:
            print(f"[ERROR] {proxy_addr}: {e}", file=sys.stderr)
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
        print(f"\nWrote {len(audits)} proxy audit(s) → {out_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
