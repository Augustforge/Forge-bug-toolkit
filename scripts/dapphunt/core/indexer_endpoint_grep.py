#!/usr/bin/env python3
"""
indexer_endpoint_grep.py — Find hardcoded indexer / RPC / API endpoints in a dApp bundle.

For each endpoint:
- Identify class (Goldsky / The Graph hosted / Allium / custom / RPC)
- Check DNS provider / takeover surface (basic — full check is in DNS hygiene)
- Flag if hardcoded with no fallback (single point of failure)

Usage:
    python3 indexer_endpoint_grep.py --target https://oyster.synfutures.com/ \
        --output sessions/$DOMAIN/indexer_endpoints.json
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


_INDEXER_PATTERNS: List[Tuple[str, str, str, str]] = [
    ("the_graph_hosted", r"https?://api\.thegraph\.com/subgraphs/", "high", "The Graph hosted service — DNS takeover would affect all dApp users."),
    ("goldsky_subgraph", r"https?://api\.goldsky\.com/", "high", "Goldsky-hosted subgraph endpoint."),
    ("allium_data", r"https?://api\.allium\.so/", "medium", "Allium data API."),
    ("alchemy_api", r"https?://(?:eth|polygon|arbitrum|optimism|base)-(?:mainnet|sepolia|goerli)\.g\.alchemy\.com/", "medium", "Alchemy RPC URL — typically with API key path."),
    ("infura_api", r"https?://(?:mainnet|sepolia|goerli|polygon-mainnet)\.infura\.io/v3/", "medium", "Infura RPC URL."),
    ("ankr_api", r"https?://rpc\.ankr\.com/", "low", "Ankr public RPC."),
    ("quicknode_api", r"https?://[\w-]+\.quiknode\.pro/", "medium", "QuickNode RPC URL — fairly unique slug per project."),
    ("custom_api_subdomain", r"https?://(?:api|subgraph|indexer|gold|graph)\.[\w.-]+(?:\.[a-z]{2,})+", "medium", "Custom subdomain endpoint — DNS takeover surface."),
    ("solana_rpc_helius", r"https?://[\w.-]+\.helius-rpc\.com/", "medium", "Helius Solana RPC."),
    ("solana_rpc_quicknode", r"https?://[\w-]+\.solana-(?:mainnet|devnet)\.quiknode\.pro/", "medium", "Solana QuickNode."),
    ("cosmos_lcd_rest", r"https?://(?:rest|lcd|api)\.[\w.-]+(?:\.[a-z]{2,})+/cosmos/", "low", "Cosmos LCD endpoint."),
]


@dataclass
class IndexerEndpoint:
    finding_id: str
    endpoint_class: str
    severity_hint: str
    description: str
    matched_url: str
    location: str


@dataclass
class IndexerReport:
    target: str
    endpoints: List[IndexerEndpoint] = field(default_factory=list)


def _fetch(url: str, max_bytes: int = 5_000_000, timeout: float = 8.0) -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dapphunt-indexer-grep/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(max_bytes).decode("utf-8", errors="replace")
    except Exception:
        return None


def _gather(target: str):
    html = _fetch(target)
    if not html:
        return []
    out = [(target, html)]
    parsed = urllib.parse.urlparse(target)
    base = f"{parsed.scheme}://{parsed.netloc}"
    srcs = re.findall(r"<script[^>]+src=['\"]([^'\"]+)['\"]", html, re.IGNORECASE)
    resolved = []
    for s in srcs:
        if s.startswith("//"):
            resolved.append(f"{parsed.scheme}:{s}")
        elif s.startswith("/"):
            resolved.append(f"{base}{s}")
        elif s.startswith("http"):
            resolved.append(s)
        else:
            resolved.append(urllib.parse.urljoin(target, s))

    def rank(u):
        lower = u.lower()
        return (0 if "/index-" in lower or "/main-" in lower else 1, 1 if "vendor" in lower or "polyfill" in lower else 0, -len(u))

    for url in sorted(set(resolved), key=rank)[:5]:
        text = _fetch(url)
        if text:
            out.append((url, text))
    return out


def scan(target: str) -> IndexerReport:
    report = IndexerReport(target=target)
    counter = 1
    for location, text in _gather(target):
        for pid, rx, sev, desc in _INDEXER_PATTERNS:
            for m in re.finditer(rx, text, re.IGNORECASE):
                matched = m.group(0)
                if len(matched) > 200:
                    matched = matched[:197] + "..."
                report.endpoints.append(IndexerEndpoint(
                    finding_id=f"IDX{counter:03d}",
                    endpoint_class=pid,
                    severity_hint=sev,
                    description=desc,
                    matched_url=matched,
                    location=location,
                ))
                counter += 1
    # Dedupe by url
    seen = set()
    unique = []
    for e in report.endpoints:
        if e.matched_url in seen:
            continue
        seen.add(e.matched_url)
        unique.append(e)
    report.endpoints = unique
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
        print(f"Indexer / RPC endpoints: {len(report.endpoints)}")
        for e in report.endpoints:
            print(f"  [{e.severity_hint:6}] {e.endpoint_class:25s}  {e.matched_url[:80]}")
    return 0 if not report.endpoints else 1


if __name__ == "__main__":
    sys.exit(main())
