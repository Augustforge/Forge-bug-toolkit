#!/usr/bin/env python3
"""
tokenlist_audit.py — Find tokenlist / image / metadata fetches the dApp depends on.

Surfaces:
- Hardcoded URL to .tokenlist.json
- tokens.uniswap.org / tokenlists.org / arbitrum.tokenlist / etc.
- IPFS gateways (ipfs.io, cf-ipfs.com, dweb.link) — gateway compromise risk
- Token metadata URIs (data:image, opensea-aware metadata)
- Logo CDNs (raw.githubusercontent.com, trustwallet assets repo)

For each, classify takeover surface (DNS / GitHub PR / CDN / IPFS gateway).

Usage:
    python3 tokenlist_audit.py --target https://oyster.synfutures.com/ \
        --output sessions/$DOMAIN/tokenlist_audit.json
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


_TOKENLIST_PATTERNS: List[Tuple[str, str, str, str]] = [
    ("uniswap_default_list", r"tokens\.uniswap\.org(?:/[^'\"\s]*)?", "high", "Compromise = malicious tokens displayed in N dApps."),
    ("tokenlists_org_generic", r"tokenlists\.org(?:/[^'\"\s]*)?", "medium", "Aggregator — compromise = downstream effect."),
    ("github_raw_tokenlist", r"raw\.githubusercontent\.com/[^/]+/[^/]+/[^/]+/.+\.tokenlist\.json", "medium", "GitHub-hosted tokenlist — PR poisoning if maintainer lax."),
    ("trustwallet_assets", r"raw\.githubusercontent\.com/trustwallet/assets/", "low", "Trust Wallet assets repo PR poisoning class."),
    ("ipfs_gateway_io", r"https?://ipfs\.io/ipfs/", "low", "Gateway-mediated content — gateway compromise can serve fake content."),
    ("ipfs_cloudflare", r"https?://cf-ipfs\.com/ipfs/", "low", "Cloudflare IPFS gateway — same gateway risk."),
    ("ipfs_dweb_link", r"https?://dweb\.link/ipfs/", "low", "Protocol Labs gateway."),
    ("ipfs_pinata", r"https?://gateway\.pinata\.cloud/ipfs/|\.mypinata\.cloud/ipfs/", "low", "Pinata-hosted IPFS gateway."),
    ("arweave_gateway", r"https?://arweave\.net/", "low", "Arweave content — permanent but gateway-mediated."),
    ("logo_cdn_generic", r"https?://[^'\"\s]+/logo(?:s)?/[^'\"\s]+\.(?:png|svg|jpg|webp)", "low", "Token logo CDN — defacing risk."),
    ("subdomain_indexer", r"https?://(?:subgraph|api|indexer|gold)\.[\w.-]+(?:\.[a-z]{2,})+", "medium", "Indexer/subgraph endpoint hardcoded."),
]


@dataclass
class TokenlistFinding:
    finding_id: str
    pattern_id: str
    severity_hint: str
    description: str
    matched_url: str
    location: str
    has_sri: bool


@dataclass
class TokenlistReport:
    target: str
    findings: List[TokenlistFinding] = field(default_factory=list)


def _fetch(url: str, max_bytes: int = 5_000_000, timeout: float = 8.0) -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dapphunt-tokenlist/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(max_bytes).decode("utf-8", errors="replace")
    except Exception:
        return None


def _gather(target: str) -> List[Tuple[str, str]]:
    """Return list of (location, text) tuples for html + first 5 bundles."""
    out: List[Tuple[str, str]] = []
    html = _fetch(target)
    if not html:
        return out
    out.append((target, html))
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

    def rank(u: str) -> tuple:
        lower = u.lower()
        return (0 if "/index-" in lower or "/main-" in lower else 1, 1 if "vendor" in lower or "polyfill" in lower else 0, -len(u))

    for url in sorted(set(resolved), key=rank)[:5]:
        text = _fetch(url)
        if text:
            out.append((url, text))
    return out


def scan(target: str) -> TokenlistReport:
    report = TokenlistReport(target=target)
    counter = 1
    for location, text in _gather(target):
        for pid, rx, sev, desc in _TOKENLIST_PATTERNS:
            for m in re.finditer(rx, text, re.IGNORECASE):
                matched = m.group(0)
                if len(matched) > 200:
                    matched = matched[:197] + "..."
                report.findings.append(TokenlistFinding(
                    finding_id=f"TL{counter:03d}",
                    pattern_id=pid,
                    severity_hint=sev,
                    description=desc,
                    matched_url=matched,
                    location=location,
                    has_sri=False,  # SRI for JSON is not typically attribute-attached
                ))
                counter += 1
    # Dedupe (pattern, url)
    seen = set()
    unique = []
    for f in report.findings:
        key = (f.pattern_id, f.matched_url)
        if key in seen:
            continue
        seen.add(key)
        unique.append(f)
    report.findings = unique
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
        print(f"Tokenlist / CDN deps: {len(report.findings)}")
        for f in report.findings:
            print(f"  [{f.severity_hint:6}] {f.pattern_id:25s}  {f.matched_url[:80]}")
    return 0 if not report.findings else 1


if __name__ == "__main__":
    sys.exit(main())
