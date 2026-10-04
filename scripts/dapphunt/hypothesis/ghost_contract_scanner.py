#!/usr/bin/env python3
"""
ghost_contract_scanner.py — Detect ghost contracts (deprecated but alive)
with live user approvals.

Mission: catch the Transit Finance May 2026 pattern BEFORE re-exploitation.
A protocol's old deprecated contract still on-chain + still callable + still
having user approvals from years ago = $1.88M drained 4 years after the
contract was "deprecated".

What this scanner does:
1. For a given list of "ghost" contract addresses (from docs/historical deploys):
   - Check eth_getCode — is bytecode present? (not selfdestructed)
   - Check paused() / killed() — is it actively running?
   - Check owner() / admin role — is there a path to pause?
2. For a list of major ERC-20 tokens on the chain (USDC/USDT/DAI/WETH/USDe by default):
   - Sample top N holders (via per-chain index — manual config since explorers vary)
   - Query allowance(holder, ghost_contract) for each
   - Sum non-zero allowances → quantified attack surface
3. Optional: check for arbitrary-call function selectors in bytecode

Pure-stdlib (no web3.py). Reuses RPC helpers from role_centralization_scanner.

Usage:
    python3 ghost_contract_scanner.py \\
        --rpc https://eth.llamarpc.com \\
        --ghost 0xOldContract1 \\
        --ghost 0xOldContract2 \\
        --token 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48  # USDC \\
        --token 0xdAC17F958D2ee523a2206206994597C13D831ec7  # USDT \\
        --sample-holder 0xWhale1 \\
        --sample-holder 0xWhale2 \\
        --out sessions/$DOMAIN/onchain/ghost_audit.json

    # Multi-chain ghost surface (run separately per chain):
    python3 ghost_contract_scanner.py --rpc $ETH_RPC --ghost 0xEthGhost ...
    python3 ghost_contract_scanner.py --rpc $TRON_RPC --ghost 0xTronGhost ...
        (TRON-style addresses require tron-aware RPC; this scanner is EVM-only)
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from role_centralization_scanner import (  # noqa: E402
    RPCError, eth_call, eth_get_code,
    encode_call, decode_uint, decode_address, decode_string,
)

# Arbitrary-call function selectors (4byte) — pattern from Transit/SwapNet/Aperture
ARBITRARY_CALL_SELECTORS = {
    "0x87395540": "callBytes(address,bytes)",
    "0x12aa3caf": "swap(address,(address,address,uint256,uint256,uint256,uint256,uint256,address,bytes))",
    "0xac9650d8": "multicall(bytes[])",
    "0x5ae401dc": "multicall(uint256,bytes[])",
    "0x1cff79cd": "execute(address,bytes)",
    "0x9870d7fe": "callBytes(bytes)",
    "0xb858183f": "exactInputSingle((address,address,uint24,address,uint256,uint256,uint256,uint160))",
}

# Default major tokens per chain (can override via --token)
DEFAULT_TOKENS_BY_CHAIN_ID = {
    1: [  # Ethereum
        ("USDC", "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"),
        ("USDT", "0xdAC17F958D2ee523a2206206994597C13D831ec7"),
        ("DAI",  "0x6B175474E89094C44Da98b954EedeAC495271d0F"),
        ("WETH", "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"),
    ],
    56: [  # BSC
        ("USDC", "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d"),
        ("USDT", "0x55d398326f99059fF775485246999027B3197955"),
        ("WBNB", "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"),
    ],
}


@dataclass
class GhostContractAudit:
    address: str
    rpc_url: str
    is_alive: bool = False
    code_size: int = 0
    paused: Optional[bool] = None
    killed: Optional[bool] = None
    owner: Optional[str] = None
    owner_is_dead: bool = False  # owner = 0x0 or known dead addresses
    has_arbitrary_call_selector: bool = False
    detected_selectors: List[str] = field(default_factory=list)
    allowances: List[Dict[str, Any]] = field(default_factory=list)
    total_approved_surface_wei: int = 0
    risk_findings: List[Dict[str, str]] = field(default_factory=list)
    risk_score: int = 0


DEAD_ADDRESSES = {
    "0x0000000000000000000000000000000000000000",
    "0x000000000000000000000000000000000000dead",
    "0x000000000000000000000000000000000000dEaD",
}


def audit_ghost_contract(
    rpc_url: str,
    ghost: str,
    tokens: List[tuple],
    sample_holders: List[str],
) -> GhostContractAudit:
    audit = GhostContractAudit(address=ghost, rpc_url=rpc_url)

    code = eth_get_code(rpc_url, ghost)
    if not code or code == "0x":
        audit.risk_findings.append({
            "severity": "info",
            "id": "selfdestructed_or_no_contract",
            "message": "No bytecode at this address — either selfdestructed or never deployed. "
                       "Ghost is fully dead.",
        })
        return audit

    audit.code_size = (len(code) - 2) // 2
    audit.is_alive = True

    # Detect arbitrary-call selectors in bytecode
    code_lower = code.lower()
    for selector, sig in ARBITRARY_CALL_SELECTORS.items():
        if selector.replace("0x", "") in code_lower:
            audit.detected_selectors.append(sig)
            audit.has_arbitrary_call_selector = True

    # Try paused()
    try:
        paused_raw = eth_call(rpc_url, ghost, encode_call("paused()"))
        audit.paused = bool(decode_uint(paused_raw))
    except RPCError:
        audit.paused = None

    # Try killed() (Compound v2 pattern)
    try:
        killed_raw = eth_call(rpc_url, ghost, encode_call("killed()"))
        audit.killed = bool(decode_uint(killed_raw))
    except RPCError:
        audit.killed = None

    # Try owner()
    try:
        owner_raw = eth_call(rpc_url, ghost, encode_call("owner()"))
        owner = decode_address(owner_raw)
        audit.owner = owner
        if owner.lower() in [d.lower() for d in DEAD_ADDRESSES]:
            audit.owner_is_dead = True
    except RPCError:
        audit.owner = None

    # Allowance audit
    for token_name, token_addr in tokens:
        for holder in sample_holders:
            try:
                allowance_raw = eth_call(
                    rpc_url, token_addr,
                    encode_call("allowance(address,address)", holder, ghost),
                )
                allowance = decode_uint(allowance_raw)
                if allowance > 0:
                    # Get balance too — drainable is min(allowance, balance)
                    try:
                        balance_raw = eth_call(
                            rpc_url, token_addr,
                            encode_call("balanceOf(address)", holder),
                        )
                        balance = decode_uint(balance_raw)
                    except RPCError:
                        balance = 0
                    drainable = min(allowance, balance)
                    audit.allowances.append({
                        "token": token_name,
                        "token_addr": token_addr,
                        "holder": holder,
                        "allowance": allowance,
                        "balance": balance,
                        "drainable_wei": drainable,
                    })
                    audit.total_approved_surface_wei += drainable
            except RPCError:
                continue

    assess_ghost_risk(audit)
    return audit


def assess_ghost_risk(audit: GhostContractAudit) -> None:
    findings = audit.risk_findings
    score = 0

    if not audit.is_alive:
        return

    # The fundamental risk: ghost is alive
    findings.append({
        "severity": "info",
        "id": "contract_alive",
        "message": f"Bytecode present ({audit.code_size} bytes). Contract is callable.",
    })

    # Is there a pause mechanism that's active?
    if audit.paused is True or audit.killed is True:
        findings.append({
            "severity": "info",
            "id": "contract_paused_or_killed",
            "message": "Contract is paused/killed at protocol level. Lower risk.",
        })
        # Don't add score; this is the GOOD state
    else:
        if audit.paused is False or audit.killed is False:
            findings.append({
                "severity": "high",
                "id": "alive_and_not_paused",
                "message": "Contract is alive AND paused()/killed() returns false. Active attack surface.",
            })
            score += 20

    # Owner state
    if audit.owner_is_dead:
        findings.append({
            "severity": "critical",
            "id": "owner_renounced_no_pause_path",
            "message": f"Owner is {audit.owner} (dead address). NO ONE can pause this contract "
                       "post-incident — permanent vulnerability if any bug exists.",
        })
        score += 30
    elif audit.owner and audit.owner != "0x" + "00" * 20:
        # Owner exists — at least someone can act
        pass

    # Arbitrary-call signature presence
    if audit.has_arbitrary_call_selector:
        findings.append({
            "severity": "high",
            "id": "arbitrary_call_pattern",
            "message": f"Detected selectors matching arbitrary-call pattern: "
                       f"{', '.join(audit.detected_selectors)}. "
                       "Combine with live approvals → drain primitive (Transit/SwapNet pattern).",
        })
        score += 25

    # Live approvals
    if audit.allowances:
        critical = audit.total_approved_surface_wei > 10 ** 24  # >1M units rough
        sev = "critical" if critical else "high"
        findings.append({
            "severity": sev,
            "id": "live_approvals_found",
            "message": f"Found {len(audit.allowances)} live approvals across sampled holders. "
                       f"Total drainable surface: {audit.total_approved_surface_wei} wei. "
                       "Approve→drain primitive immediately exploitable if any bug present.",
        })
        score += 30 if critical else 15

    audit.risk_score = min(score, 100)


def format_summary(audit: GhostContractAudit) -> str:
    lines = []
    lines.append("=" * 72)
    lines.append(f"Ghost contract: {audit.address}")
    if not audit.is_alive:
        lines.append("  Status: DEAD (no bytecode)")
        lines.append("=" * 72)
        return "\n".join(lines)
    lines.append(f"  Code size: {audit.code_size} bytes")
    lines.append(f"  paused(): {audit.paused}")
    lines.append(f"  killed(): {audit.killed}")
    lines.append(f"  owner(): {audit.owner} (dead: {audit.owner_is_dead})")
    if audit.detected_selectors:
        lines.append(f"  Arbitrary-call selectors: {', '.join(audit.detected_selectors)}")
    if audit.allowances:
        lines.append(f"  Live approvals: {len(audit.allowances)} (total drainable: "
                     f"{audit.total_approved_surface_wei} wei)")
        for a in audit.allowances[:5]:
            lines.append(f"    {a['token']}: holder {a['holder']} → drainable {a['drainable_wei']}")
        if len(audit.allowances) > 5:
            lines.append(f"    ... and {len(audit.allowances) - 5} more")
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
    parser.add_argument("--ghost", required=True, action="append",
                        help="Ghost contract address (can be repeated)")
    parser.add_argument("--token", action="append", default=[],
                        help="Token contract address to check allowances against "
                             "(can be repeated). Default: USDC/USDT/DAI/WETH on Ethereum.")
    parser.add_argument("--token-name", action="append", default=[],
                        help="Optional name for each --token (parallel array)")
    parser.add_argument("--sample-holder", action="append", default=[],
                        help="Sample holder address to check approvals from (whale/old user). "
                             "If empty, scanner will only report contract state.")
    parser.add_argument("--chain-id", type=int, default=1,
                        help="Chain ID — used to pick default tokens if --token not given")
    parser.add_argument("--out")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    # Resolve tokens list
    if args.token:
        if args.token_name and len(args.token_name) == len(args.token):
            tokens = list(zip(args.token_name, args.token))
        else:
            tokens = [(f"TOKEN_{i}", t) for i, t in enumerate(args.token)]
    else:
        tokens = DEFAULT_TOKENS_BY_CHAIN_ID.get(args.chain_id, [])
        if not tokens:
            print(f"[ERROR] No default tokens for chain_id {args.chain_id}; pass --token", file=sys.stderr)
            return 2

    if not args.sample_holder:
        print("[WARN] No --sample-holder provided; allowance audit skipped. "
              "Pass top holders of major tokens to find live approvals.", file=sys.stderr)

    audits = []
    for ghost_addr in args.ghost:
        try:
            audit = audit_ghost_contract(args.rpc, ghost_addr, tokens, args.sample_holder)
        except RPCError as e:
            print(f"[ERROR] {ghost_addr}: {e}", file=sys.stderr)
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
        print(f"\nWrote {len(audits)} ghost contract audit(s) → {out_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
