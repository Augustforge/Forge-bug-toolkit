#!/usr/bin/env python3
"""
wallet_metadata_xss_check.py — Detect unsanitized use of untrusted external input.

Generalizes past the single wallet-metadata source into the class "every external
input is untrusted — assume it lies to the maximum": a malicious contract-wallet
faking EIP-1271 signature validity, a malicious/compromised RPC or indexer response,
a malicious/compromised tokenlist. Each source family is checked against TWO kinds
of sinks:

  - display sinks (original XSS path) — innerHTML/dangerouslySetInnerHTML/img-src/etc.
  - decision sinks (new) — balance/allowance-gated conditionals, decimals/price scaling
    math — where the dApp makes a MONEY decision on unverified external data.

Source families (`_SOURCE_FAMILIES`):

  - wallet_metadata      — WalletConnect peer.metadata / EIP-6963 detail.info / wallet-standard.
                            {name, url, icons, description, verifyUrl} are attacker-controlled
                            the moment a malicious wallet connects.
  - eip1271_liar         — a contract-wallet whose isValidSignature() always returns the
                            magic value (0x1626ba7e) regardless of the actual signature. If the
                            dApp trusts that return value for an access/authorization decision,
                            the "signature" verified nothing.
  - malicious_rpc_indexer — eth_call / subgraph / indexer response drives displayed or
                            decision-critical balances/prices/allowances. If nothing
                            cross-checks the indexer against a direct RPC read, the indexer
                            is a single point of trust.
  - malicious_tokenlist   — fetched tokenlist name/symbol/logoURI/decimals rendered OR fed
                            into math (e.g. amount scaling) without ever reading decimals()
                            from the token contract itself.

If the dApp renders or decides on any of these fields without verification (typical
React mistake: `<img src={wallet.icons[0]} />` or `dangerouslySetInnerHTML`; typical
decision mistake: `if (indexerBalance >= price)` with no on-chain cross-check), a
malicious wallet / RPC / tokenlist can land XSS or a false-decision primitive on the
dApp origin.

This script grep's the bundle for known source-family markers near sink patterns
(within PROX_LINES) and flags suspicious co-locations.

Usage:
    python3 wallet_metadata_xss_check.py --target https://oyster.synfutures.com/ \
        --output sessions/$DOMAIN/wallet_metadata_xss.json
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
from typing import Dict, List, Optional


# Fields exposed by WalletConnect peer metadata, EIP-6963, wallet-standard.
# Any of these read from a connected wallet is attacker-controllable.
_METADATA_FIELDS = [
    # WalletConnect v2 SessionTypes.Peer.metadata
    r"peer\.metadata\.(name|url|icons|description|verifyUrl)",
    r"session\.peer\.metadata\.(name|url|icons|description)",
    r"proposer\.metadata\.(name|url|icons|description)",
    # EIP-6963 detail.info
    r"detail\.info\.(name|icon|rdns|uuid)",
    r"provider\.info\.(name|icon|rdns)",
    # wallet-standard (Solana)
    r"wallet\.(name|icon|version)\b",
    # Generic walletconnect-like
    r"metadata\.(name|url|icons|description|verifyUrl)\b",
]

# Source families of untrusted external input — "every external input lies to the
# maximum". Each family maps to a list of grep markers that indicate the dApp is
# reading data it did not generate itself and cannot control the content of.
_SOURCE_FAMILIES: Dict[str, Dict[str, object]] = {
    "wallet_metadata": {
        "title": "Wallet-supplied connection metadata (WalletConnect/EIP-6963/wallet-standard)",
        "patterns": _METADATA_FIELDS,
    },
    "eip1271_liar": {
        "title": "EIP-1271 contract-wallet isValidSignature() — magic-value liar",
        "patterns": [
            r"isValidSignature\s*\(",
            r"0x1626ba7e",
            r"EIP-?1271",
        ],
    },
    "malicious_rpc_indexer": {
        "title": "eth_call / subgraph / indexer response driving balances, prices, allowances",
        "patterns": [
            r"\beth_call\b",
            r"subgraph",
            r"indexer",
            r"gql`[^`]*\b(balance|allowance|price|reserve)\b",
            r"\.balanceOf\s*\(",
            r"\.allowance\s*\(",
        ],
    },
    "malicious_tokenlist": {
        "title": "Fetched tokenlist name/symbol/logoURI/decimals",
        "patterns": [
            r"tokenlist",
            r"tokens\.uniswap\.org",
            r"tokenlists\.org",
            r"\.tokenlist\.json",
            r"logoURI",
        ],
    },
}

# DOM sinks that render untrusted strings as HTML.
_DOM_SINKS = [
    (r"dangerouslySetInnerHTML\s*[:=]\s*\{[^}]*?__html\s*:", "high",
     "React dangerouslySetInnerHTML — direct HTML injection sink"),
    (r"\.innerHTML\s*[:=]", "high", "Element.innerHTML — HTML injection sink"),
    (r"\.outerHTML\s*[:=]", "high", "Element.outerHTML — HTML injection sink"),
    (r"document\.write(?:ln)?\s*\(", "high", "document.write — HTML injection sink"),
    (r"\beval\s*\(", "high", "eval — code injection sink"),
    (r"\bnew\s+Function\s*\(", "high", "new Function() — code injection sink"),
    (r"insertAdjacentHTML\s*\(", "high", "insertAdjacentHTML — HTML injection sink"),
]

# Image src and href sinks that take a URL but can be `javascript:` URI.
_URL_SINKS = [
    (r"(<img[^>]+src=|\.src\s*=)\s*[\{`'\"][^`'\"]*?(icon|metadata|peer)", "medium",
     "<img src={attacker URL}> — javascript: URI XSS if URL is not validated"),
    (r"(<a[^>]+href=|\.href\s*=)\s*[\{`'\"][^`'\"]*?(url|verifyUrl|metadata)", "medium",
     "<a href={attacker URL}> — javascript: URI XSS if URL not validated"),
]

# Decision sinks — the dApp makes a money/authorization decision on untrusted data
# instead of merely rendering it. Same co-location engine as the display sinks.
_DECISION_SINKS = [
    (r"if\s*\([^)]*\b(?:bal|\w*balance)\w*[^)]*(?:>=|>|<=|<)", "high",
     "Balance-gated conditional — branch decided by unverified balance value"),
    (r"if\s*\([^)]*\w*allowance\w*[^)]*(?:>=|>|<=|<)", "high",
     "Allowance-gated conditional — branch decided by unverified allowance value"),
    (r"\b(?:amountOut|scaledAmount|normalizedAmount|maxBorrow|borrowLimit|collateralValue)\s*=\s*[^;]*\b(?:decimals|price|balance)\b", "high",
     "Amount/collateral math derived from unverified decimals/price/balance"),
    (r"10\s*\*\*\s*\w*[Dd]ecimals\w*", "medium",
     "Exponent scaling directly by an unverified `decimals` value"),
    (r"isValidSignature\b.{0,60}?(?:===|==)\s*(?:true|0x1626ba7e)", "high",
     "Access decision gated on isValidSignature() result — trusts the contract-wallet's own claim"),
]


@dataclass
class XSSHit:
    field_pattern: str
    sink_pattern: str
    severity: str
    sink_description: str
    bundle_url: str
    line_no: int
    context_excerpt: str
    source_family: str = "wallet_metadata"
    sink_kind: str = "display"


@dataclass
class WalletXSSReport:
    target: str
    bundles_scanned: List[str] = field(default_factory=list)
    metadata_references_found: int = 0
    sinks_found: int = 0
    composed_hits: List[XSSHit] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def _fetch(url: str, max_bytes: int = 5_000_000, timeout: float = 8.0) -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dapphunt-walletmeta/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(max_bytes).decode("utf-8", errors="replace")
    except Exception:
        return None


def _gather_bundles(target: str) -> Dict[str, str]:
    """Fetch the HTML and the top JS bundles, return {url: content}."""
    html = _fetch(target)
    if not html:
        return {}
    parsed = urllib.parse.urlparse(target)
    base = f"{parsed.scheme}://{parsed.netloc}"
    srcs = re.findall(r"<script[^>]+src=['\"]([^'\"]+)['\"]", html, re.IGNORECASE)

    def rank(u: str) -> tuple:
        lower = u.lower()
        return (0 if "/index-" in lower or "/main-" in lower or "/app-" in lower else 1,
                1 if "vendor" in lower or "polyfill" in lower else 0,
                -len(u))

    resolved: List[str] = []
    for s in srcs:
        if s.startswith("//"):
            resolved.append(f"{parsed.scheme}:{s}")
        elif s.startswith("/"):
            resolved.append(f"{base}{s}")
        elif s.startswith("http"):
            resolved.append(s)
        else:
            resolved.append(f"{base}/{s}")
    resolved.sort(key=rank)

    bundles: Dict[str, str] = {target: html}
    for url in resolved[:5]:  # cap to top 5
        text = _fetch(url)
        if text:
            bundles[url] = text
    return bundles


def _find_lines(content: str, pattern: str, flags: int = re.IGNORECASE) -> List[tuple]:
    """Return [(line_no, line_text)] for each match."""
    matches: List[tuple] = []
    rx = re.compile(pattern, flags)
    for idx, line in enumerate(content.split("\n"), 1):
        if rx.search(line):
            matches.append((idx, line.strip()[:300]))
    return matches


def _analyze_bundles(bundles: Dict[str, str]) -> WalletXSSReport:
    """Pure analysis over already-fetched {url: content} bundles — no network I/O.
    Split out from scan() so tests can feed fixture bundles directly."""
    rep = WalletXSSReport(target="")
    rep.bundles_scanned = list(bundles.keys())

    # Pass 1: find all source-family references (wallet metadata / EIP-1271 liar /
    # malicious RPC-indexer / malicious tokenlist).
    source_hits: List[tuple] = []  # (bundle_url, line_no, line, family_id, pattern)
    for url, content in bundles.items():
        for family_id, family in _SOURCE_FAMILIES.items():
            for fp in family["patterns"]:
                for line_no, line in _find_lines(content, fp):
                    source_hits.append((url, line_no, line, family_id, fp))
    rep.metadata_references_found = len(source_hits)

    # Pass 2: find all sinks — display (DOM/URL, original XSS path) and decision
    # (balance/allowance-gated conditionals, unverified scaling math).
    sink_hits: List[tuple] = []  # (bundle_url, line_no, line, sink_pattern, severity, desc, kind)
    all_sinks = (
        [(pat, sev, desc, "display") for pat, sev, desc in _DOM_SINKS + _URL_SINKS]
        + [(pat, sev, desc, "decision") for pat, sev, desc in _DECISION_SINKS]
    )
    for url, content in bundles.items():
        for pat, sev, desc, kind in all_sinks:
            for line_no, line in _find_lines(content, pat):
                sink_hits.append((url, line_no, line, pat, sev, desc, kind))
    rep.sinks_found = len(sink_hits)

    # Pass 3: composed hits — source reference + sink in nearby lines (±10 lines).
    # Minified bundles often have everything on one line, so co-location on the
    # same line is a strong signal. Cross-line proximity is a weaker signal.
    PROX_LINES = 10
    seen: set = set()
    for m_url, m_line, m_text, m_family, m_field in source_hits:
        for s_url, s_line, s_text, s_pat, s_sev, s_desc, s_kind in sink_hits:
            if m_url != s_url:
                continue
            if abs(m_line - s_line) > PROX_LINES:
                continue
            key = (m_url, m_line, s_line, m_family, m_field, s_pat)
            if key in seen:
                continue
            seen.add(key)
            # Boost severity if on the SAME line (high-confidence composition)
            severity = s_sev
            if m_line == s_line:
                severity = "high"
            rep.composed_hits.append(
                XSSHit(
                    field_pattern=m_field,
                    sink_pattern=s_pat,
                    severity=severity,
                    sink_description=s_desc,
                    bundle_url=m_url,
                    line_no=m_line,
                    context_excerpt=(m_text if len(m_text) <= len(s_text) else s_text)[:200],
                    source_family=m_family,
                    sink_kind=s_kind,
                )
            )

    if rep.metadata_references_found and not rep.sinks_found:
        rep.notes.append(
            "External-input source(s) are read in the bundle but no obvious "
            "display/decision sinks found nearby — manually verify any place this "
            "data is rendered or decided on (React's text interpolation is safe by "
            "default; only HTML/decision sinks matter)."
        )
    if not rep.metadata_references_found:
        rep.notes.append(
            "No wallet-metadata / EIP-1271 / RPC-indexer / tokenlist source references "
            "found in the bundle. Either none of these adapters are used, or the "
            "relevant code is processed in a worker / dynamic import not reachable "
            "from the main bundle."
        )
    if rep.composed_hits:
        by_family: Dict[str, int] = {}
        for hit in rep.composed_hits:
            by_family[hit.source_family] = by_family.get(hit.source_family, 0) + 1
        breakdown = ", ".join(f"{k}={v}" for k, v in sorted(by_family.items()))
        rep.notes.append(
            f"COMPOSED RISK: {len(rep.composed_hits)} external-input-source + sink "
            f"co-locations detected ({breakdown}). For each, verify the dApp "
            "sanitizes/cross-checks the field before passing it to the sink. Sample "
            "PoC (wallet_metadata/display): install an EIP-6963 wallet extension that "
            "announces `info.name = '<img src=x onerror=alert(1)>'`. Sample PoC "
            "(eip1271_liar/decision): deploy a contract-wallet whose isValidSignature() "
            "always returns 0x1626ba7e."
        )

    return rep


def scan(target: str) -> WalletXSSReport:
    bundles = _gather_bundles(target)
    rep = _analyze_bundles(bundles)
    rep.target = target
    return rep


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human summary")
    args = parser.parse_args(argv)

    rep = scan(args.target)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(asdict(rep), ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(asdict(rep), ensure_ascii=False, indent=2))
        return 0

    print(f"Target: {args.target}")
    print(f"Bundles scanned: {len(rep.bundles_scanned)}")
    print(f"External-input source refs (wallet-metadata/eip1271/rpc-indexer/tokenlist): {rep.metadata_references_found}")
    print(f"Display+decision sinks found: {rep.sinks_found}")
    print(f"Composed hits (source + sink near): {len(rep.composed_hits)}")
    for hit in rep.composed_hits[:10]:
        print(f"  [{hit.severity}] {hit.bundle_url}:{hit.line_no}")
        print(f"     source: {hit.source_family}  field: {hit.field_pattern}")
        print(f"     sink:   [{hit.sink_kind}] {hit.sink_description}")
        print(f"     ctx:    {hit.context_excerpt[:140]}")
    if len(rep.composed_hits) > 10:
        print(f"  ... and {len(rep.composed_hits) - 10} more")
    for note in rep.notes:
        print(f"  note: {note}")
    return 0 if not rep.composed_hits else 1


if __name__ == "__main__":
    sys.exit(main())
