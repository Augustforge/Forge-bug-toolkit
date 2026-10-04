#!/usr/bin/env python3
"""
wallet_integration_grep.py — Multi-chain wallet handler grep over dApp bundle(s).

For each chain class, find handlers, classify usage, and flag risky patterns:

EVM:
- window.ethereum + EIP-1193 .request({ method })
- EIP-712 typed data (chainId, verifyingContract)
- personal_sign (vs signTypedData)
- eth_sign (legacy — almost always a finding if present)
- Permit / Permit2 / EIP-4361 SIWE
- EIP-1271 isValidSignature
- EIP-3009 transferWithAuthorization
- EIP-7702 (Pectra) — eth_signAuthorization / set-code tx type 0x04 / authorization_list

Solana:
- window.solana / Phantom
- signMessage, signTransaction, signAllTransactions
- signIn (SIWS proposal)

Cosmos:
- window.keplr / window.leap
- signAmino vs signDirect (Direct is preferred for safety; Amino legacy)
- ADR-36 sign messages

Sui / Aptos:
- signTransactionBlock / signPersonalMessage (Sui)
- signTransaction / signMessage (Aptos)

Usage:
    python3 wallet_integration_grep.py --target https://oyster.synfutures.com/ \
        --output sessions/$DOMAIN/wallet_integration_audit.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple


_CHAIN_HANDLERS: Dict[str, List[Tuple[str, str, str, str]]] = {
    "evm": [
        ("window_ethereum", r"window\.ethereum\b", "low", "window.ethereum reference"),
        ("eip1193_request", r"\.request\s*\(\s*\{\s*method\s*[:=]\s*['\"](eth_[\w]+|personal_sign|wallet_[\w]+)", "low", "EIP-1193 request"),
        ("eth_sign", r"eth_sign(?![A-Za-z_])", "high", "Legacy eth_sign — almost always a finding"),
        ("personal_sign", r"personal_sign", "low", "personal_sign use"),
        ("sign_typed_data_v3", r"eth_signTypedData_v3", "medium", "Legacy v3 signTypedData"),
        ("sign_typed_data_v4", r"eth_signTypedData_v4|signTypedData\(", "low", "Modern v4 signTypedData"),
        ("eip712_chain_id_hardcoded", r"chainId\s*[:=]\s*1\b(?!\d)", "medium", "EIP-712 chainId hardcoded to mainnet"),
        ("permit2", r"permit2|Permit2", "low", "Permit2 flow"),
        ("permit_call", r"permit\s*\(\s*[\w$]+\s*,", "low", "EIP-2612 permit"),
        ("eip4361_siwe", r"Sign-In With Ethereum|SIWE|siwe-iso", "low", "EIP-4361 SIWE"),
        ("eip1271", r"isValidSignature|0x1626ba7e", "medium", "EIP-1271 smart-wallet signature path"),
        ("eip3009", r"transferWithAuthorization", "medium", "EIP-3009"),
        ("eth_send_transaction", r"eth_sendTransaction", "low", "Direct value transfer call"),
        ("approve_unlimited", r"approve\s*\([^,)]+,\s*(?:MaxUint256|ethers\.constants\.MaxUint256|2\s*\*\*\s*256\s*-\s*1)", "high", "Unlimited approval primitive"),
        # EIP-7702 (Pectra) — EOA temporarily sets code to a smart wallet impl.
        # Authorization tuple (chain_id, address, nonce, y_parity, r, s) → if dApp asks
        # for an authorization but UI shows it as a regular "Connect" / "Sign in",
        # user can grant code delegation unknowingly. Same threat-model as EIP-1271 lying
        # but at the EOA level — entire wallet becomes attacker-controlled smart contract.
        ("eip7702_authorization", r"\beth_signAuthorization\b|\bsignAuthorization\s*\(|EIP-?7702|setCode\s*\(\s*authorization", "high", "EIP-7702 authorization (Pectra) — delegates EOA code to a contract; verify the UI shows what address the EOA delegates to"),
        ("eip7702_tx_type_0x04", r"type\s*[:=]\s*['\"]?0x0?4['\"]?|TransactionType\.SetCode|setCodeAuthorization", "high", "EIP-7702 transaction type 0x04 (SET_CODE_TX_TYPE) reference"),
        ("eip7702_auth_list", r"authorizationList\s*[:=]|\bauthorization_list\b|delegationDesignator", "medium", "EIP-7702 authorization list / delegation designator construction"),
    ],
    "solana": [
        ("window_solana", r"window\.solana\b|window\.phantom\b", "low", "Solana wallet reference"),
        ("sign_message", r"\.signMessage\s*\(", "medium", "Solana signMessage"),
        ("sign_transaction", r"\.signTransaction\s*\(", "low", "Solana signTransaction"),
        ("sign_all_transactions", r"\.signAllTransactions\s*\(", "medium", "signAllTransactions — bulk signing risk"),
        ("siws", r"signIn\s*\(\s*\{|@solana/wallet-standard", "low", "Sign-In With Solana (proposal)"),
    ],
    "cosmos": [
        ("window_keplr", r"window\.keplr\b", "low", "Keplr"),
        ("window_leap", r"window\.leap\b", "low", "Leap"),
        ("sign_amino", r"\.signAmino\s*\(", "medium", "Cosmos signAmino — legacy signing"),
        ("sign_direct", r"\.signDirect\s*\(", "low", "Cosmos signDirect"),
        ("adr36_sign", r"signArbitrary|signADR036", "low", "ADR-36 arbitrary message signing"),
    ],
    "move_sui": [
        ("sign_tx_block", r"\.signTransactionBlock\s*\(|@mysten/sui", "low", "Sui signTransactionBlock"),
        ("sign_personal_message", r"\.signPersonalMessage\s*\(", "low", "Sui signPersonalMessage"),
    ],
    "move_aptos": [
        ("aptos_sign_tx", r"@aptos-labs.*signTransaction|aptos\.signTransaction", "low", "Aptos signTransaction"),
        ("aptos_sign_message", r"aptos\.signMessage", "low", "Aptos signMessage"),
    ],
}


@dataclass
class WalletPattern:
    pattern_id: str
    chain_class: str
    severity_hint: str
    description: str
    matches: int
    sample_excerpt: str


@dataclass
class WalletAuditReport:
    target: str
    patterns_found: List[WalletPattern] = field(default_factory=list)
    chains_active: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def _fetch(url: str, max_bytes: int = 5_000_000, timeout: float = 8.0) -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dapphunt-wallet-grep/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(max_bytes).decode("utf-8", errors="replace")
    except Exception:
        return None


def _gather_bundle_text(target: str) -> str:
    html = _fetch(target)
    if not html:
        return ""
    parts = [html]
    parsed = urllib.parse.urlparse(target)
    base = f"{parsed.scheme}://{parsed.netloc}"
    srcs = re.findall(r"<script[^>]+src=['\"]([^'\"]+)['\"]", html, re.IGNORECASE)

    def rank(u: str) -> tuple:
        lower = u.lower()
        return (0 if "/index-" in lower or "/main-" in lower else 1, 1 if "vendor" in lower or "polyfill" in lower else 0, -len(u))

    resolved: List[str] = []
    for s in srcs:
        if s.startswith("//"):
            resolved.append(f"{parsed.scheme}:{s}")
        elif s.startswith("/"):
            resolved.append(f"{base}{s}")
        elif s.startswith("http"):
            resolved.append(s)
        else:
            resolved.append(urllib.parse.urljoin(target, s))
    for url in sorted(set(resolved), key=rank)[:5]:
        text = _fetch(url)
        if text:
            parts.append(text)
    return "\n".join(parts)


def scan(target: str) -> WalletAuditReport:
    report = WalletAuditReport(target=target)
    text = _gather_bundle_text(target)
    if not text:
        report.notes.append(f"Could not fetch any content from {target}.")
        return report

    chains_active = set()
    for chain_class, patterns in _CHAIN_HANDLERS.items():
        for pid, rx, sev, desc in patterns:
            m_iter = list(re.finditer(rx, text, re.IGNORECASE))
            if not m_iter:
                continue
            chains_active.add(chain_class)
            sample = m_iter[0].group(0)
            if len(sample) > 80:
                sample = sample[:77] + "..."
            report.patterns_found.append(WalletPattern(
                pattern_id=pid,
                chain_class=chain_class,
                severity_hint=sev,
                description=desc,
                matches=len(m_iter),
                sample_excerpt=sample,
            ))
    report.chains_active = sorted(chains_active)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    report = scan(args.target)
    payload = json.dumps(asdict(report), ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")

    if not args.quiet:
        print(f"Target: {report.target}")
        print(f"Chain classes active: {', '.join(report.chains_active) or '(none)'}")
        print(f"\nPatterns found: {len(report.patterns_found)}")
        by_chain: Dict[str, List[WalletPattern]] = {}
        for p in report.patterns_found:
            by_chain.setdefault(p.chain_class, []).append(p)
        for chain, patterns in sorted(by_chain.items()):
            print(f"\n  [{chain}]")
            for p in patterns:
                print(f"    [{p.severity_hint:6}] {p.pattern_id:30s}  matches={p.matches}  ({p.description})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
