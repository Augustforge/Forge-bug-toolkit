#!/usr/bin/env python3
"""
dapp_detection.py — Identify if a target is a Web3 dApp frontend and which chain(s) it serves.

This is the routing brain for /dapphunt and is also called from /hunt Phase 3
to suggest a methodology switch.

Detection signals (additive scoring 0-100):
- HTML scan: Connect Wallet UI, Privy/Magic/WalletConnect script tags
- JS bundle scan: chain-specific SDK markers, EIP/window object patterns
- HTTP headers: CSP frame-ancestors with wallet providers, security.txt referencing Web3 programs
- TMA markers: Telegram.WebApp / tgWebAppData

Chain class output:
- evm | solana | cosmos | move | multichain | tma | not_dapp

Usage:
    python3 dapp_detection.py --target https://oyster.synfutures.com/
    python3 dapp_detection.py --target https://oyster.synfutures.com/ --output detection.json
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


# ──────────────────────────────────────────────────────────────────────────
# Detection signal definitions
#
# Each signal: (signal_id, regex, chain_class, weight, description)
# chain_class = "evm" | "solana" | "cosmos" | "move" | "tma" | "generic"
# weight: contribution to detection_score (0-25 each, cap at 100)
# ──────────────────────────────────────────────────────────────────────────

_HTML_SIGNALS: List[Tuple[str, str, str, int, str]] = [
    # Generic dApp markers
    ("html_connect_wallet", r"\bconnect\s+wallet\b", "generic", 10, "Connect Wallet UI element"),
    ("html_disconnect_wallet", r"\bdisconnect\s+wallet\b", "generic", 5, "Disconnect Wallet UI"),
    ("html_web3_keyword", r"\bweb3\b", "generic", 3, "web3 mentioned in markup"),

    # Auth provider script tags
    ("html_privy_script", r"<script[^>]+(?:privy\.io|@privy-io)", "generic", 15, "Privy SDK script tag"),
    ("html_magic_script", r"<script[^>]+(?:magic\.link|@magic-sdk)", "generic", 15, "Magic SDK"),
    ("html_web3auth_script", r"<script[^>]+(?:web3auth\.io|@web3auth)", "generic", 15, "Web3Auth SDK"),
    ("html_dynamic_script", r"<script[^>]+(?:dynamic\.xyz|@dynamic-labs)", "generic", 15, "Dynamic Labs SDK"),
    ("html_thirdweb_script", r"<script[^>]+(?:thirdweb)", "generic", 15, "ThirdWeb SDK"),
    ("html_walletconnect_script", r"<script[^>]+(?:walletconnect|web3modal|reown)", "generic", 12, "WalletConnect / Web3Modal / Reown"),

    # TMA
    ("html_tma_script", r"<script[^>]+telegram-web-app\.js", "tma", 25, "Telegram Web App script"),
    ("html_tma_initdata", r"\btgWebAppData\b", "tma", 20, "TMA initData reference"),
]

_BUNDLE_SIGNALS: List[Tuple[str, str, str, int, str]] = [
    # EVM
    ("bundle_wagmi", r"\b(?:wagmi|@wagmi/(?:core|connectors|react))\b", "evm", 20, "wagmi SDK"),
    ("bundle_viem", r"\bviem\b", "evm", 15, "viem"),
    ("bundle_ethers_v6", r"\bethers(?:/lib)?\.js\b|new ethers\.(?:Browser)?Provider", "evm", 15, "ethers.js"),
    ("bundle_web3js", r"\bweb3\.js\b|new Web3\(", "evm", 12, "web3.js"),
    ("bundle_rainbowkit", r"@rainbow-me/rainbowkit", "evm", 18, "RainbowKit"),
    ("bundle_window_ethereum", r"window\.ethereum\b", "evm", 15, "window.ethereum reference"),
    ("bundle_eip1193", r"\beip\s*-\s*1193\b|request\s*\(\s*\{\s*method", "evm", 10, "EIP-1193 pattern"),
    ("bundle_eip712", r"\bEIP-?712\b|signTypedData(?:_v4)?", "evm", 10, "EIP-712 typed data signing"),
    ("bundle_personal_sign", r"\bpersonal_sign\b", "evm", 8, "personal_sign"),

    # Solana
    ("bundle_solana_web3", r"@solana/web3\.js", "solana", 22, "Solana web3.js"),
    ("bundle_solana_wallet_adapter", r"@solana/wallet-adapter", "solana", 22, "Solana wallet adapter"),
    ("bundle_anchor_client", r"@coral-xyz/anchor|@project-serum/anchor", "solana", 18, "Anchor client"),
    ("bundle_window_solana", r"window\.solana\b|window\.phantom\b", "solana", 15, "window.solana / Phantom"),

    # Cosmos
    ("bundle_cosmjs", r"@cosmjs/(?:stargate|encoding|amino|proto-signing|launchpad)", "cosmos", 22, "CosmJS"),
    ("bundle_cosmos_kit", r"@cosmos-kit/", "cosmos", 20, "Cosmos Kit"),
    ("bundle_keplr", r"window\.keplr\b|@keplr-wallet/", "cosmos", 18, "Keplr"),
    ("bundle_leap", r"window\.leap\b|@leapwallet/", "cosmos", 18, "Leap wallet"),

    # Move (Sui / Aptos)
    ("bundle_sui", r"@mysten/sui(?:\.js)?", "move", 22, "Sui SDK"),
    ("bundle_suiet", r"@suiet/wallet-kit", "move", 18, "Suiet wallet kit"),
    ("bundle_aptos", r"@aptos-labs/(?:ts-sdk|wallet-adapter)", "move", 22, "Aptos SDK"),

    # WalletConnect / Reown (chain-agnostic)
    ("bundle_walletconnect", r"@walletconnect/", "generic", 12, "WalletConnect"),
    ("bundle_reown", r"@reown/", "generic", 12, "Reown (WalletConnect rebrand)"),
    ("bundle_web3modal", r"@web3modal/", "generic", 12, "Web3Modal"),

    # Privy embedded
    ("bundle_privy", r"@privy-io/", "generic", 18, "Privy SDK in bundle"),
    ("bundle_privy_app_id", r"clz[a-z0-9]{18,24}", "generic", 8, "Privy app ID pattern"),

    # TMA
    ("bundle_tma_webapp", r"Telegram\.WebApp\b", "tma", 25, "Telegram.WebApp API"),

    # Hardware wallets / signing libs
    ("bundle_ledger", r"@ledgerhq/", "evm", 6, "Ledger SDK"),
    ("bundle_safe", r"@safe-global/|gnosis-safe", "evm", 6, "Safe / Gnosis"),
]

_HEADER_SIGNALS: List[Tuple[str, str, str, int, str]] = [
    ("header_csp_privy", r"frame-ancestors[^;]*privy", "generic", 5, "CSP allows Privy iframe"),
    ("header_csp_walletconnect", r"connect-src[^;]*walletconnect", "generic", 4, "CSP allows WalletConnect"),
    ("header_csp_solana", r"connect-src[^;]*solana", "solana", 4, "CSP allows Solana RPC"),
    ("header_security_txt_immunefi", r"immunefi\.com", "generic", 4, "security.txt references Immunefi"),
    ("header_security_txt_hackenproof", r"hackenproof\.com", "generic", 4, "security.txt references HackenProof"),
]


@dataclass
class DetectionSignal:
    signal_id: str
    chain_class: str
    weight: int
    description: str
    source: str       # "html" / "bundle" / "header"
    location: str     # URL / file / header name


@dataclass
class DappDetectionResult:
    target: str
    detection_score: int           # 0-100, capped
    chain_class: str               # "evm" / "solana" / "cosmos" / "move" / "multichain" / "tma" / "not_dapp"
    auth_providers: List[str] = field(default_factory=list)
    wallet_adapters: List[str] = field(default_factory=list)
    stack_signals: List[str] = field(default_factory=list)
    signals_matched: List[DetectionSignal] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def _fetch(url: str, timeout: float = 8.0) -> Tuple[Optional[str], Dict[str, str]]:
    """Fetch URL → (text, headers_dict). Returns (None, {}) on failure."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "dapphunt-detection/1.0", "Accept": "*/*"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(2_000_000)  # cap at 2MB per fetch
            text = raw.decode("utf-8", errors="replace")
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return text, headers
    except Exception:
        return None, {}


def _extract_script_urls(html: str, base_url: str) -> List[str]:
    """Extract src= URLs from <script> tags, resolving relative URLs."""
    parsed_base = urllib.parse.urlparse(base_url)
    src_pattern = re.compile(r"<script[^>]+src\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
    urls = []
    for m in src_pattern.finditer(html):
        src = m.group(1)
        if src.startswith("//"):
            full = f"{parsed_base.scheme}:{src}"
        elif src.startswith("/"):
            full = f"{parsed_base.scheme}://{parsed_base.netloc}{src}"
        elif src.startswith("http"):
            full = src
        else:
            full = urllib.parse.urljoin(base_url, src)
        urls.append(full)
    return urls


def _scan_signals(
    text: str,
    signal_table: List[Tuple[str, str, str, int, str]],
    source: str,
    location: str,
) -> List[DetectionSignal]:
    """Apply all regex signals from the table against text."""
    found: List[DetectionSignal] = []
    for sig_id, rx, chain_class, weight, desc in signal_table:
        if re.search(rx, text, re.IGNORECASE):
            found.append(
                DetectionSignal(
                    signal_id=sig_id,
                    chain_class=chain_class,
                    weight=weight,
                    description=desc,
                    source=source,
                    location=location,
                )
            )
    return found


def _decide_chain_class(signals: List[DetectionSignal]) -> str:
    """Aggregate per-chain weights and pick the dominant class."""
    chain_totals: Dict[str, int] = {}
    for s in signals:
        if s.chain_class == "generic":
            continue
        chain_totals[s.chain_class] = chain_totals.get(s.chain_class, 0) + s.weight

    if not chain_totals:
        return "not_dapp"

    # Sort chains by weight desc
    sorted_chains = sorted(chain_totals.items(), key=lambda kv: kv[1], reverse=True)
    top_class, top_weight = sorted_chains[0]

    # TMA dominates over everything if detected (TMA is a containment layer, not a chain)
    if "tma" in chain_totals and chain_totals["tma"] >= 20:
        # If TMA + another chain class both strong, return multichain with TMA flag
        non_tma_strong = [c for c, w in chain_totals.items() if c != "tma" and w >= 15]
        if non_tma_strong:
            return "tma"  # report as TMA; chain_class doubles via stack_signals
        return "tma"

    # Multichain if 2+ chain classes each strong (>=15)
    strong_chains = [c for c, w in chain_totals.items() if w >= 15]
    if len(strong_chains) >= 2:
        return "multichain"

    return top_class


def _extract_auth_providers(signals: List[DetectionSignal]) -> List[str]:
    providers = set()
    mapping = {
        "html_privy_script": "privy",
        "bundle_privy": "privy",
        "html_magic_script": "magic",
        "html_web3auth_script": "web3auth",
        "html_dynamic_script": "dynamic",
        "html_thirdweb_script": "thirdweb",
        "html_walletconnect_script": "walletconnect",
        "bundle_walletconnect": "walletconnect",
        "bundle_reown": "reown",
        "bundle_web3modal": "web3modal",
    }
    for s in signals:
        name = mapping.get(s.signal_id)
        if name:
            providers.add(name)
    return sorted(providers)


def _extract_wallet_adapters(signals: List[DetectionSignal]) -> List[str]:
    adapters = set()
    mapping = {
        "bundle_window_ethereum": "metamask_class",
        "bundle_rainbowkit": "rainbowkit",
        "bundle_window_solana": "phantom",
        "bundle_solana_wallet_adapter": "solana_wallet_adapter",
        "bundle_keplr": "keplr",
        "bundle_leap": "leap",
        "bundle_suiet": "suiet",
        "bundle_ledger": "ledger",
        "bundle_safe": "safe",
    }
    for s in signals:
        name = mapping.get(s.signal_id)
        if name:
            adapters.add(name)
    return sorted(adapters)


def detect(target: str, max_bundles: int = 3) -> DappDetectionResult:
    """Run full detection pipeline."""
    result = DappDetectionResult(target=target, detection_score=0, chain_class="not_dapp")

    # 1. Fetch main HTML
    html, headers = _fetch(target)
    if not html:
        result.notes.append(f"Could not fetch {target}; aborting detection.")
        return result

    html_signals = _scan_signals(html, _HTML_SIGNALS, "html", target)
    result.signals_matched.extend(html_signals)

    # 2. Scan headers
    header_blob = "\n".join(f"{k}: {v}" for k, v in headers.items())
    header_signals = _scan_signals(header_blob, _HEADER_SIGNALS, "header", target)
    result.signals_matched.extend(header_signals)

    # 3. Discover script URLs and fetch top N bundles by name length (proxy for "main app bundle")
    script_urls = _extract_script_urls(html, target)
    # Heuristic: longer paths are usually main app chunks (assets/index-<hash>.js); skip vendor.
    ranked = sorted(
        set(script_urls),
        key=lambda u: (
            "vendor" in u.lower(),
            "polyfill" in u.lower(),
            "runtime" in u.lower(),
            -len(u),
        ),
    )
    for script_url in ranked[:max_bundles]:
        bundle_text, _ = _fetch(script_url)
        if bundle_text:
            bundle_signals = _scan_signals(bundle_text, _BUNDLE_SIGNALS, "bundle", script_url)
            result.signals_matched.extend(bundle_signals)

    # 4. Score (capped at 100)
    total = sum(s.weight for s in result.signals_matched)
    result.detection_score = min(100, total)

    # 5. Decide chain class
    if result.detection_score < 30:
        result.chain_class = "not_dapp"
        result.notes.append("Detection score < 30 → likely not a Web3 dApp.")
    else:
        result.chain_class = _decide_chain_class(result.signals_matched)

    # 6. Derive auth providers + wallet adapters
    result.auth_providers = _extract_auth_providers(result.signals_matched)
    result.wallet_adapters = _extract_wallet_adapters(result.signals_matched)

    # 7. Stack signals (unique signal IDs for the report)
    result.stack_signals = sorted({s.signal_id for s in result.signals_matched})

    # 8. Add helpful notes
    if result.detection_score >= 50:
        result.notes.append("Strong dApp signal — recommend /dapphunt methodology.")
    elif result.detection_score >= 30:
        result.notes.append("Weak dApp signal — could be hybrid; consider /hunt with dApp phase 4-5 ad-hoc.")

    if result.chain_class == "multichain":
        result.notes.append("Multi-chain detection — Phase 6 wallet integration audit runs per-chain.")

    if "tma" in result.chain_class or any(s.signal_id.startswith("html_tma") or s.signal_id.startswith("bundle_tma") for s in result.signals_matched):
        result.notes.append("Telegram Mini App markers present — enable Phase 8.5 in skill.")

    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--target", required=True, help="dApp URL (e.g. https://oyster.synfutures.com/)")
    parser.add_argument("--output", type=Path, help="Write JSON output here")
    parser.add_argument("--max-bundles", type=int, default=3, help="Max JS bundles to fetch and scan (default 3)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    result = detect(args.target, max_bundles=args.max_bundles)

    payload = json.dumps(asdict(result), ensure_ascii=False, indent=2, default=str)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")

    if not args.quiet:
        # Compact human summary
        print(f"Target: {result.target}")
        print(f"Detection score: {result.detection_score}/100")
        print(f"Chain class: {result.chain_class}")
        print(f"Auth providers: {', '.join(result.auth_providers) or '(none detected)'}")
        print(f"Wallet adapters: {', '.join(result.wallet_adapters) or '(none detected)'}")
        print(f"Signals matched: {len(result.signals_matched)}")
        for note in result.notes:
            print(f"  note: {note}")

    return 0 if result.detection_score >= 30 else 1


if __name__ == "__main__":
    sys.exit(main())
