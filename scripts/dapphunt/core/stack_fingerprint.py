#!/usr/bin/env python3
"""
stack_fingerprint.py — Identify frontend stack versions for a dApp.

Detects:
- React / Vue / Svelte version
- Build tool: Vite / Webpack / Next.js / Parcel
- Web3 SDK versions (wagmi, viem, ethers, web3.js)
- Chain-specific: @solana/web3.js, @cosmjs/*, @mysten/sui.js, @aptos-labs/*
- Auth provider versions (Privy, Magic, Dynamic, etc.)
- 3rd-party libs: TradingView, AntD, MUI, Chakra, Sentry, PostHog, GTM
- **Source map check**: GET /assets/*.js.map — if 200 → full TS source restored
- **Env leak check**: VITE_* / process.env.REACT_APP_* baked into bundle

Outputs JSON with versions per library + flagged env leaks + source map presence.

Usage:
    python3 stack_fingerprint.py --target https://oyster.synfutures.com/ \
        --output sessions/$DOMAIN/stack_fingerprint.json
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


# ── Stack signatures: (lib_name, version_regex, severity_class) ──
_STACK_PATTERNS: List[Tuple[str, str, str]] = [
    # Core frameworks
    ("react", r"React.*?(\d+\.\d+\.\d+)|react@(\d+\.\d+\.\d+)|version[\"']\s*:\s*[\"'](\d+\.\d+\.\d+)[\"'].*?react", "framework"),
    ("vue", r"vue@(\d+\.\d+\.\d+)|Vue\.version\s*=\s*[\"'](\d+\.\d+\.\d+)", "framework"),
    ("svelte", r"svelte@(\d+\.\d+\.\d+)", "framework"),
    # Build tools
    ("vite", r"vite@(\d+\.\d+\.\d+)|__vite__|import\.meta\.env", "build_tool"),
    ("webpack", r"webpackJsonp|__webpack_require__|webpack@(\d+\.\d+\.\d+)", "build_tool"),
    ("next", r"__NEXT_DATA__|_next/static/", "build_tool"),
    # EVM Web3 SDKs
    ("wagmi", r"wagmi@(\d+\.\d+\.\d+)|\"name\":\"wagmi\".*?\"version\":\"(\d+\.\d+\.\d+)\"", "web3_evm"),
    ("viem", r"viem@(\d+\.\d+\.\d+)|\"name\":\"viem\".*?\"version\":\"(\d+\.\d+\.\d+)\"", "web3_evm"),
    ("ethers", r"ethers@(\d+\.\d+\.\d+)|ethers/(\d+\.\d+\.\d+)|ethers/lib(?:\.commonjs)?/_version.*?(\d+\.\d+\.\d+)", "web3_evm"),
    ("web3js", r"\"name\":\"web3\".*?\"version\":\"(\d+\.\d+\.\d+)\"", "web3_evm"),
    ("rainbowkit", r"@rainbow-me/rainbowkit@(\d+\.\d+\.\d+)", "web3_evm"),
    # Solana
    ("solana_web3js", r"@solana/web3\.js@(\d+\.\d+\.\d+)", "web3_solana"),
    ("solana_wallet_adapter", r"@solana/wallet-adapter-[\w-]+@(\d+\.\d+\.\d+)", "web3_solana"),
    ("anchor", r"@coral-xyz/anchor@(\d+\.\d+\.\d+)|@project-serum/anchor@(\d+\.\d+\.\d+)", "web3_solana"),
    # Cosmos
    ("cosmjs", r"@cosmjs/[\w-]+@(\d+\.\d+\.\d+)", "web3_cosmos"),
    ("cosmos_kit", r"@cosmos-kit/[\w-]+@(\d+\.\d+\.\d+)", "web3_cosmos"),
    # Move
    ("sui_sdk", r"@mysten/sui(?:\.js)?@(\d+\.\d+\.\d+)", "web3_move"),
    ("aptos_sdk", r"@aptos-labs/ts-sdk@(\d+\.\d+\.\d+)", "web3_move"),
    # Auth providers
    ("privy", r"@privy-io/[\w-]+@(\d+\.\d+\.\d+)", "auth"),
    ("magic", r"@magic-sdk/[\w-]+@(\d+\.\d+\.\d+)", "auth"),
    ("web3auth", r"@web3auth/[\w-]+@(\d+\.\d+\.\d+)", "auth"),
    ("dynamic", r"@dynamic-labs/[\w-]+@(\d+\.\d+\.\d+)", "auth"),
    ("walletconnect", r"@walletconnect/[\w-]+@(\d+\.\d+\.\d+)", "auth"),
    ("web3modal", r"@web3modal/[\w-]+@(\d+\.\d+\.\d+)", "auth"),
    ("reown", r"@reown/[\w-]+@(\d+\.\d+\.\d+)", "auth"),
    # 3rd party
    ("antd", r"antd@(\d+\.\d+\.\d+)|\"antd\".*?\"version\":\"(\d+\.\d+\.\d+)\"", "ui"),
    ("mui", r"@mui/material@(\d+\.\d+\.\d+)", "ui"),
    ("chakra", r"@chakra-ui/[\w-]+@(\d+\.\d+\.\d+)", "ui"),
    ("tradingview", r"tradingview", "ui"),
    ("sentry", r"@sentry/[\w-]+@(\d+\.\d+\.\d+)|Sentry.*?VERSION.*?(\d+\.\d+\.\d+)", "telemetry"),
    ("posthog", r"posthog(?:-js)?@(\d+\.\d+\.\d+)", "telemetry"),
    ("gtm", r"www\.googletagmanager\.com/gtag", "telemetry"),
]


# ── Env leak patterns (Vite + Webpack + Next conventions) ──
_ENV_LEAK_PATTERNS: List[Tuple[str, str, str]] = [
    ("sentry_dsn", r"https?://[a-f0-9]+@[\w.-]+\.ingest\.(?:us\.|de\.)?sentry\.io/\d+", "high"),
    ("privy_app_secret", r"privy[_-]?(?:app[_-]?)?secret\s*[:=]\s*['\"]([A-Za-z0-9_-]{20,})['\"]", "critical"),
    ("magic_secret_key", r"sk_(?:live|test)_[A-Za-z0-9]{16,40}", "critical"),
    ("mapbox_token", r"pk\.eyJ[A-Za-z0-9._-]{40,}", "medium"),
    ("algolia_admin_key", r"algolia[_-]?admin[_-]?(?:key|api[_-]?key)\s*[:=]\s*['\"]([A-Za-z0-9]{32,})['\"]", "high"),
    ("pinata_jwt", r"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "medium"),
    ("aws_access_key", r"AKIA[0-9A-Z]{16}", "critical"),
    ("infura_project_id", r"infura\.io/v3/([a-f0-9]{32})", "medium"),
    ("alchemy_key", r"alchemy(?:\.com)?(?:/v\d)?/([A-Za-z0-9_-]{30,})", "medium"),
    ("generic_jwt", r"eyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}", "low"),
    ("vite_env_marker", r"import\.meta\.env\.VITE_[A-Z_]+", "low"),
    ("react_env_marker", r"process\.env\.REACT_APP_[A-Z_]+", "low"),
]


@dataclass
class StackEntry:
    library: str
    version: Optional[str]
    category: str
    location: str    # bundle url or "html"


@dataclass
class EnvLeak:
    leak_id: str
    severity: str
    matched: str
    bundle_url: str


@dataclass
class StackReport:
    target: str
    libraries: List[StackEntry] = field(default_factory=list)
    env_leaks: List[EnvLeak] = field(default_factory=list)
    source_maps_found: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def _fetch(url: str, max_bytes: int = 5_000_000, timeout: float = 8.0) -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dapphunt-stack-fp/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(max_bytes)
            return raw.decode("utf-8", errors="replace")
    except Exception:
        return None


def _check_source_map(bundle_url: str) -> Optional[str]:
    """If bundle_url ends in .js, try .js.map."""
    if not bundle_url.endswith(".js"):
        return None
    map_url = bundle_url + ".map"
    try:
        req = urllib.request.Request(map_url, headers={"User-Agent": "dapphunt-stack-fp/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200 and resp.headers.get("Content-Type", "").lower().startswith(("application/json", "text/plain", "application/octet")):
                return map_url
    except Exception:
        pass
    return None


def _scan_for_stack(text: str, location: str) -> List[StackEntry]:
    entries: List[StackEntry] = []
    for lib, rx, category in _STACK_PATTERNS:
        for m in re.finditer(rx, text, re.IGNORECASE):
            groups = [g for g in m.groups() if g]
            version = groups[0] if groups else None
            entries.append(StackEntry(library=lib, version=version, category=category, location=location))
    return entries


def _scan_for_env_leaks(text: str, bundle_url: str) -> List[EnvLeak]:
    leaks: List[EnvLeak] = []
    counter = 1
    for leak_id, rx, sev in _ENV_LEAK_PATTERNS:
        for m in re.finditer(rx, text, re.IGNORECASE):
            matched = m.group(0)
            if len(matched) > 200:
                matched = matched[:197] + "..."
            leaks.append(EnvLeak(
                leak_id=f"{leak_id}_{counter:03d}",
                severity=sev,
                matched=matched,
                bundle_url=bundle_url,
            ))
            counter += 1
    return leaks


def scan(target: str) -> StackReport:
    report = StackReport(target=target)
    html = _fetch(target)
    if not html:
        report.notes.append(f"Could not fetch {target}.")
        return report

    report.libraries.extend(_scan_for_stack(html, "html"))

    parsed = urllib.parse.urlparse(target)
    base = f"{parsed.scheme}://{parsed.netloc}"
    src_rx = re.compile(r"<script[^>]+src=['\"]([^'\"]+)['\"]", re.IGNORECASE)
    srcs = src_rx.findall(html)

    # Resolve relative URLs
    bundles: List[str] = []
    for s in srcs:
        if s.startswith("//"):
            bundles.append(f"{parsed.scheme}:{s}")
        elif s.startswith("/"):
            bundles.append(f"{base}{s}")
        elif s.startswith("http"):
            bundles.append(s)
        else:
            bundles.append(urllib.parse.urljoin(target, s))

    # Rank: index/main first, vendor/polyfill last
    def rank(u: str) -> tuple:
        lower = u.lower()
        return (
            0 if "/index-" in lower or "/main-" in lower else 1,
            1 if "vendor" in lower or "polyfill" in lower or "runtime" in lower else 0,
            -len(u),
        )

    bundles = sorted(set(bundles), key=rank)

    for url in bundles[:5]:
        text = _fetch(url)
        if not text:
            continue
        report.libraries.extend(_scan_for_stack(text, url))
        report.env_leaks.extend(_scan_for_env_leaks(text, url))
        smap = _check_source_map(url)
        if smap:
            report.source_maps_found.append(smap)

    # Dedupe libraries by (lib, version)
    seen = set()
    unique: List[StackEntry] = []
    for e in report.libraries:
        key = (e.library, e.version)
        if key in seen:
            continue
        seen.add(key)
        unique.append(e)
    report.libraries = unique

    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    report = scan(args.target)
    payload = json.dumps(asdict(report), ensure_ascii=False, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")

    if not args.quiet:
        print(f"Target: {report.target}")
        print(f"Libraries detected: {len(report.libraries)}")
        by_cat: Dict[str, List[StackEntry]] = {}
        for e in report.libraries:
            by_cat.setdefault(e.category, []).append(e)
        for cat in sorted(by_cat.keys()):
            print(f"\n  [{cat}]")
            for e in by_cat[cat]:
                v = f" v{e.version}" if e.version else ""
                print(f"    {e.library}{v}")
        if report.source_maps_found:
            print(f"\n⚠ Source maps exposed ({len(report.source_maps_found)}):")
            for m in report.source_maps_found:
                print(f"    {m}")
        if report.env_leaks:
            print(f"\n⚠ Env leaks ({len(report.env_leaks)}):")
            for leak in report.env_leaks:
                print(f"    [{leak.severity:8}] {leak.leak_id}: {leak.matched[:80]}")
    return 0 if not (report.env_leaks or report.source_maps_found) else 1


if __name__ == "__main__":
    sys.exit(main())
