#!/usr/bin/env python3
"""
siwe_audit.py — Check SIWE (EIP-4361) / SIWS (Solana sign-in) implementation.

Common SIWE issues:
- No nonce → replay attack
- Nonce reused across sessions
- Static `expiration_time` or missing `issued_at` → indefinite token validity
- `domain` field hardcoded → spoof when dApp is on multiple subdomains
- Statement field permits arbitrary user-controlled text → phishing wrapper

Heuristic — grep SIWE/SIWS message construction patterns in bundle, flag missing
fields.

Usage:
    python3 siwe_audit.py --target https://oyster.synfutures.com/ \
        --output sessions/$DOMAIN/siwe_audit.json
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


_SIWE_INDICATOR_RX = re.compile(r"Sign-In With Ethereum|SIWE|siwe-iso|@siwe/|\bnonce:|EIP-4361", re.IGNORECASE)
_SIWS_INDICATOR_RX = re.compile(r"Sign in With Solana|SIWS|@solana/wallet-standard", re.IGNORECASE)
_NONCE_RX = re.compile(r"nonce\s*[:=]\s*['\"]?([A-Za-z0-9]{6,32})['\"]?", re.IGNORECASE)
_DOMAIN_HARDCODED_RX = re.compile(r"domain\s*[:=]\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
_EXPIRATION_RX = re.compile(r"expiration[_-]?time|expirationTime", re.IGNORECASE)
_ISSUED_AT_RX = re.compile(r"issued[_-]?at|issuedAt", re.IGNORECASE)


@dataclass
class SiweFinding:
    finding_id: str
    issue: str
    severity_hint: str
    evidence: str
    location: str


@dataclass
class SiweReport:
    target: str
    siwe_detected: bool
    siws_detected: bool
    findings: List[SiweFinding] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def _fetch(url: str, max_bytes: int = 5_000_000, timeout: float = 8.0) -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dapphunt-siwe/1.0"})
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


def scan(target: str) -> SiweReport:
    report = SiweReport(target=target, siwe_detected=False, siws_detected=False)
    counter = 1
    for location, text in _gather(target):
        if _SIWE_INDICATOR_RX.search(text):
            report.siwe_detected = True
        if _SIWS_INDICATOR_RX.search(text):
            report.siws_detected = True

    if not (report.siwe_detected or report.siws_detected):
        report.notes.append("No SIWE/SIWS markers found — skipping deeper checks.")
        return report

    for location, text in _gather(target):
        # Nonce checks
        nonces = _NONCE_RX.findall(text)
        if nonces:
            unique_nonces = set(nonces)
            if len(nonces) > 0 and len(unique_nonces) <= 1:
                report.findings.append(SiweFinding(
                    finding_id=f"SIWE{counter:03d}",
                    issue="Hardcoded / single nonce literal found — verify nonce is generated per-session, not constant.",
                    severity_hint="medium",
                    evidence=f"nonce(s) in bundle: {sorted(unique_nonces)[:3]}",
                    location=location,
                ))
                counter += 1
        # Hardcoded domain
        domains = _DOMAIN_HARDCODED_RX.findall(text)
        for d in domains:
            if "${" in d or "{{" in d:
                continue
            report.findings.append(SiweFinding(
                finding_id=f"SIWE{counter:03d}",
                issue=f"Hardcoded `domain` literal `{d}` — if dApp serves multi-subdomain, signature may not bind correctly.",
                severity_hint="low",
                evidence=d,
                location=location,
            ))
            counter += 1
        # Missing expiration
        if not _EXPIRATION_RX.search(text):
            report.findings.append(SiweFinding(
                finding_id=f"SIWE{counter:03d}",
                issue="No `expirationTime` field reference found — signed session may not expire, enabling indefinite reuse.",
                severity_hint="medium",
                evidence="(absent)",
                location=location,
            ))
            counter += 1
            break  # Only report missing once per bundle set
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
        print(f"SIWE detected: {report.siwe_detected}  SIWS detected: {report.siws_detected}")
        print(f"Findings: {len(report.findings)}")
        for f in report.findings:
            print(f"  [{f.severity_hint:6}] {f.finding_id}  {f.issue}")
    return 0 if not report.findings else 1


if __name__ == "__main__":
    sys.exit(main())
