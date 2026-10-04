#!/usr/bin/env python3
"""
trust_wildcard_scanner.py — Find every wildcard in any allowlist a dApp ships.

Wildcard sources (per dapphunt SKILL Phase 2.5 hypothesis sources):
- `allowed_domains` (Privy/Magic/Web3Auth)
- `frame-ancestors` (CSP)
- `Access-Control-Allow-Origin` (CORS)
- `connect-src` (CSP)
- `redirect_uri` (OAuth)
- `metadata.url` (WalletConnect peer metadata)

Each wildcard = expanded trust boundary. If a wildcard like `*.iftl.info`
exists, ANY iftl.info subdomain that lacks framing protection becomes a
clickjacking primitive for the production dApp (SynFutures pattern).

Usage:
    python3 trust_wildcard_scanner.py --target https://oyster.synfutures.com/ \
        --auth-config sessions/$DOMAIN/auth_provider_config.json \
        --headers sessions/$DOMAIN/headers.json \
        --output sessions/$DOMAIN/hypothesis/trust_wildcards.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional


WILDCARD_RX = re.compile(r"\*\.[a-z0-9-]+(?:\.[a-z0-9-]+)+", re.IGNORECASE)


@dataclass
class Wildcard:
    pattern: str            # e.g. "*.iftl.info"
    source: str             # "privy_allowed_domains" | "csp_frame_ancestors" | ...
    location: str           # exact field path / header name
    severity_hint: str      # "high" | "medium" | "low"
    composes_with: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass
class TrustWildcardReport:
    target: str
    wildcards: List[Wildcard] = field(default_factory=list)
    composed_hypotheses: List[str] = field(default_factory=list)


def _fetch_headers(url: str, timeout: float = 6.0) -> Dict[str, str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dapphunt-trust-scan/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {k.lower(): v for k, v in resp.headers.items()}
    except Exception:
        return {}


def _scan_string_for_wildcards(text: str) -> List[str]:
    """Return all *.domain patterns found in a string, deduped."""
    return sorted(set(WILDCARD_RX.findall(text)))


def _scan_auth_config(config: dict) -> List[Wildcard]:
    """Walk JSON tree from auth_provider_probe output, flag wildcards."""
    found: List[Wildcard] = []

    def walk(node, path: str, provider: str):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else k, provider)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]", provider)
        elif isinstance(node, str):
            for w in _scan_string_for_wildcards(node):
                severity = "high" if any(s in path.lower() for s in ("allowed_domains", "frame", "redirect")) else "medium"
                found.append(
                    Wildcard(
                        pattern=w,
                        source=f"{provider}_{path.lower().replace('.', '_')}",
                        location=f"auth_provider_config.{provider}.{path}",
                        severity_hint=severity,
                        notes=[f"Wildcard {w} declared in {provider} config at {path}."],
                    )
                )

    # Top-level keys = provider names (privy, magic, web3auth, dynamic, ...)
    if isinstance(config, dict):
        for provider, sub in config.items():
            walk(sub, "", provider)
    return found


def _scan_headers_for_wildcards(headers: Dict[str, str]) -> List[Wildcard]:
    found: List[Wildcard] = []
    interesting = {
        "content-security-policy": ("csp", "high"),
        "access-control-allow-origin": ("cors_acao", "medium"),
        "permissions-policy": ("permissions_policy", "low"),
    }
    for hdr, value in headers.items():
        if hdr not in interesting:
            continue
        source_label, sev = interesting[hdr]

        if hdr == "content-security-policy":
            # Parse directives, pick frame-ancestors and connect-src specifically
            directives = [d.strip() for d in value.split(";") if d.strip()]
            for d in directives:
                parts = d.split(None, 1)
                if len(parts) < 2:
                    continue
                directive, vals = parts[0].lower(), parts[1]
                if directive == "frame-ancestors":
                    for w in _scan_string_for_wildcards(vals):
                        found.append(Wildcard(
                            pattern=w,
                            source="csp_frame_ancestors",
                            location="response_headers.Content-Security-Policy.frame-ancestors",
                            severity_hint="high",
                            notes=[f"CSP frame-ancestors permits {w} — frameable from any matching subdomain."],
                        ))
                elif directive == "connect-src":
                    for w in _scan_string_for_wildcards(vals):
                        found.append(Wildcard(
                            pattern=w,
                            source="csp_connect_src",
                            location="response_headers.Content-Security-Policy.connect-src",
                            severity_hint="medium",
                            notes=[f"CSP connect-src permits {w} — fetch reach expanded."],
                        ))
        elif hdr == "access-control-allow-origin":
            if value.strip() == "*":
                found.append(Wildcard(
                    pattern="*",
                    source="cors_acao_star",
                    location="response_headers.Access-Control-Allow-Origin",
                    severity_hint="high",
                    notes=["ACAO: * means any origin can read responses. Critical if endpoint returns user data."],
                ))
            else:
                for w in _scan_string_for_wildcards(value):
                    found.append(Wildcard(
                        pattern=w,
                        source=source_label,
                        location=f"response_headers.{hdr.title()}",
                        severity_hint=sev,
                        notes=[f"CORS reflects wildcard {w}."],
                    ))
        else:
            for w in _scan_string_for_wildcards(value):
                found.append(Wildcard(
                    pattern=w,
                    source=source_label,
                    location=f"response_headers.{hdr.title()}",
                    severity_hint=sev,
                ))
    return found


def _scan_bundle_for_wildcards(bundle_text: str) -> List[Wildcard]:
    """Heuristic: walk minified bundle for *.domain.tld string literals."""
    found: List[Wildcard] = []
    for w in _scan_string_for_wildcards(bundle_text):
        found.append(Wildcard(
            pattern=w,
            source="bundle_string_literal",
            location="bundle.js",
            severity_hint="low",
            notes=[
                f"Wildcard string {w} found in JS bundle. "
                "Manually check if it's used in OAuth redirect, WalletConnect metadata, or another trust allowlist."
            ],
        ))
    return found


def _compose_hypotheses(wildcards: List[Wildcard]) -> List[str]:
    """For each wildcard, generate a candidate hypothesis."""
    hypotheses: List[str] = []
    seen_patterns: set = set()
    for w in wildcards:
        source_l = w.source.lower()
        # Dedupe per (pattern, hypothesis class)
        if "allowed_domains" in source_l or "csp_frame_ancestors" in source_l:
            key = (w.pattern, "auth_iframe")
            if key in seen_patterns:
                continue
            seen_patterns.add(key)
            hypotheses.append(
                f"H[{w.pattern}]: If any subdomain matching `{w.pattern}` lacks X-Frame-Options/CSP "
                f"frame-ancestors AND auth provider trusts it ({w.source}), then a clickjacking + "
                f"wallet-phishing chain becomes available against production users."
            )
        elif "redirect" in source_l or source_l.startswith("oauth"):
            key = (w.pattern, "oauth")
            if key in seen_patterns:
                continue
            seen_patterns.add(key)
            hypotheses.append(
                f"H[{w.pattern}]: OAuth redirect_uri allows `{w.pattern}` — open-redirect to attacker-controlled "
                f"subdomain enables token exfiltration via OAuth flow."
            )
        elif source_l == "cors_acao_star":
            key = ("*", "cors")
            if key in seen_patterns:
                continue
            seen_patterns.add(key)
            hypotheses.append(
                "H[ACAO*]: ACAO=* permits any origin to read responses. If accompanied by authenticated "
                "endpoint with credentials in cookie, cross-origin data theft is possible."
            )
        elif "connect_src" in source_l or "connect-src" in source_l:
            key = (w.pattern, "connect_src")
            if key in seen_patterns:
                continue
            seen_patterns.add(key)
            hypotheses.append(
                f"H[{w.pattern}]: CSP connect-src permits fetches to `{w.pattern}`. Pair with subdomain "
                f"takeover under that wildcard → fake API responses to dApp users."
            )
    return hypotheses


def scan(
    target: str,
    auth_config_path: Optional[Path],
    headers_path: Optional[Path],
    bundle_paths: List[Path],
) -> TrustWildcardReport:
    report = TrustWildcardReport(target=target)

    # Auth provider config (already-collected output from auth_provider_probe)
    if auth_config_path and auth_config_path.exists():
        try:
            config = json.loads(auth_config_path.read_text(encoding="utf-8"))
            report.wildcards.extend(_scan_auth_config(config))
        except Exception as exc:
            print(f"warn: could not parse auth config: {exc}", file=sys.stderr)

    # Headers (precomputed by iframe_trust_check or fresh fetch)
    headers: Dict[str, str] = {}
    if headers_path and headers_path.exists():
        try:
            headers = json.loads(headers_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    if not headers:
        headers = _fetch_headers(target)
    report.wildcards.extend(_scan_headers_for_wildcards(headers))

    # Bundles (optional — pass --bundle PATH for each)
    for bp in bundle_paths:
        if bp.exists():
            try:
                text = bp.read_text(encoding="utf-8", errors="replace")
                report.wildcards.extend(_scan_bundle_for_wildcards(text))
            except Exception:
                continue

    # Dedupe (same pattern + source pair)
    seen = set()
    unique: List[Wildcard] = []
    for w in report.wildcards:
        key = (w.pattern, w.source, w.location)
        if key not in seen:
            seen.add(key)
            unique.append(w)
    report.wildcards = unique

    # Generate hypotheses
    report.composed_hypotheses = _compose_hypotheses(report.wildcards)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--target", required=True)
    parser.add_argument("--auth-config", type=Path, help="JSON output from auth_provider_probe.py")
    parser.add_argument("--headers", type=Path, help="JSON dict of response headers")
    parser.add_argument("--bundle", action="append", type=Path, default=[], help="JS bundle file (repeatable)")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    report = scan(args.target, args.auth_config, args.headers, args.bundle)
    payload = json.dumps(asdict(report), ensure_ascii=False, indent=2)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")

    if not args.quiet:
        print(f"Target: {report.target}")
        print(f"Wildcards found: {len(report.wildcards)}")
        for w in report.wildcards:
            print(f"  [{w.severity_hint.upper():6}] {w.pattern}  source={w.source}")
            print(f"           location: {w.location}")
        print()
        print(f"Composed hypotheses: {len(report.composed_hypotheses)}")
        for h in report.composed_hypotheses:
            print(f"  • {h}")

    return 0 if not report.wildcards else 1


if __name__ == "__main__":
    sys.exit(main())
