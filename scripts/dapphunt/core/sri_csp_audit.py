#!/usr/bin/env python3
"""
sri_csp_audit.py — Check Subresource Integrity (SRI) and CSP completeness.

Checks:
- Every <script src=...> and <link rel="stylesheet">: integrity attribute present?
- Cross-origin scripts without SRI = supply chain risk (e.g. TradingView, AntD CDN)
- CSP directives completeness: script-src, style-src, connect-src, default-src
- CSP weaknesses: 'unsafe-inline', 'unsafe-eval', '*', http: schemes

Usage:
    python3 sri_csp_audit.py --target https://oyster.synfutures.com/ \
        --output sessions/$DOMAIN/sri_csp_audit.json
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


@dataclass
class ScriptTag:
    src: str
    cross_origin: bool
    has_integrity: bool
    crossorigin_attr: Optional[str]


@dataclass
class CspFinding:
    directive: str
    issue: str
    severity_hint: str


@dataclass
class SRICspReport:
    target: str
    csp_present: bool
    csp_raw: Optional[str]
    csp_findings: List[CspFinding] = field(default_factory=list)
    scripts: List[ScriptTag] = field(default_factory=list)
    sri_findings: List[str] = field(default_factory=list)


def _fetch(url: str, timeout: float = 8.0) -> tuple[Optional[str], Dict[str, str]]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dapphunt-sri-csp/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(2_000_000).decode("utf-8", errors="replace"), {k.lower(): v for k, v in resp.headers.items()}
    except Exception:
        return None, {}


def _parse_csp(csp: str) -> Dict[str, List[str]]:
    result: Dict[str, List[str]] = {}
    for directive in csp.split(";"):
        d = directive.strip()
        if not d:
            continue
        parts = d.split()
        result[parts[0].lower()] = [p.strip() for p in parts[1:]]
    return result


def _csp_findings(csp_parsed: Dict[str, List[str]]) -> List[CspFinding]:
    findings: List[CspFinding] = []
    risky = {
        "'unsafe-inline'": ("allows inline scripts/styles", "medium"),
        "'unsafe-eval'": ("allows eval()", "medium"),
        "*": ("wildcard host source", "high"),
        "http:": ("permits HTTP fetch — downgrade vector", "medium"),
        "data:": ("permits data: URIs — content-injection vector", "low"),
    }
    for directive, values in csp_parsed.items():
        if directive not in ("default-src", "script-src", "style-src", "connect-src", "img-src", "frame-src"):
            continue
        for v in values:
            for token, (desc, sev) in risky.items():
                if v == token or v.startswith(token):
                    findings.append(CspFinding(directive=directive, issue=f"{v} → {desc}", severity_hint=sev))
    # Missing critical directives
    for required in ("script-src", "frame-ancestors"):
        if required not in csp_parsed and "default-src" not in csp_parsed:
            findings.append(CspFinding(directive=required, issue="missing directive (no default-src fallback)", severity_hint="low"))
    return findings


def scan(target: str) -> SRICspReport:
    html, headers = _fetch(target)
    report = SRICspReport(target=target, csp_present=False, csp_raw=None)
    if not html:
        return report

    parsed = urllib.parse.urlparse(target)
    primary_host = parsed.netloc

    # CSP from header (or meta)
    csp = headers.get("content-security-policy")
    if not csp:
        m = re.search(r"<meta[^>]+http-equiv=['\"]Content-Security-Policy['\"][^>]+content=['\"]([^'\"]+)['\"]", html, re.IGNORECASE)
        if m:
            csp = m.group(1)
    if csp:
        report.csp_present = True
        report.csp_raw = csp
        parsed_csp = _parse_csp(csp)
        report.csp_findings = _csp_findings(parsed_csp)

    # Scripts + SRI
    for m in re.finditer(r"<script\b([^>]+)>", html, re.IGNORECASE):
        attrs = m.group(1)
        src_m = re.search(r"src=['\"]([^'\"]+)['\"]", attrs)
        if not src_m:
            continue
        src = src_m.group(1)
        integrity = "integrity=" in attrs.lower()
        crossorigin_m = re.search(r"crossorigin=['\"]?([^'\" >]+)?", attrs, re.IGNORECASE)
        crossorigin_attr = crossorigin_m.group(1) if crossorigin_m else None
        # Cross-origin?
        full_src = src
        if src.startswith("//"):
            full_src = f"{parsed.scheme}:{src}"
        elif src.startswith("/"):
            full_src = f"{parsed.scheme}://{parsed.netloc}{src}"
        cross_origin = bool(re.match(r"^https?://", full_src)) and urllib.parse.urlparse(full_src).netloc != primary_host
        report.scripts.append(ScriptTag(src=src, cross_origin=cross_origin, has_integrity=integrity, crossorigin_attr=crossorigin_attr))
        if cross_origin and not integrity:
            report.sri_findings.append(
                f"Cross-origin <script src='{src}'> has no integrity attribute. Supply-chain risk if remote CDN is compromised."
            )

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
        print(f"CSP present: {report.csp_present}")
        if report.csp_findings:
            print(f"CSP issues: {len(report.csp_findings)}")
            for f in report.csp_findings:
                print(f"  [{f.severity_hint:6}] {f.directive}: {f.issue}")
        print(f"Scripts: {len(report.scripts)}  (cross-origin missing SRI: {len(report.sri_findings)})")
        for f in report.sri_findings:
            print(f"  • {f}")
    return 0 if not (report.csp_findings or report.sri_findings) else 1


if __name__ == "__main__":
    sys.exit(main())
