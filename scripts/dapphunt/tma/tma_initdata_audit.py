#!/usr/bin/env python3
"""
tma_initdata_audit.py — Audit Telegram Mini App initData handling.

Telegram passes `initData` as a query string to the WebApp URL. The dApp/bot
must validate the HMAC over initData using the bot token. Common issues:

- No HMAC validation server-side (only frontend "looks valid")
- Validation present but `auth_date` not checked → replay window unbounded
- `hash` field stripped before validation, allowing replayed payloads
- Cross-bot reuse: same initData accepted across multiple bots (if validation
  doesn't bind to bot ID)

This script:
1. Grep frontend bundle for Telegram.WebApp usage and initData handling
2. Flag any client-only validation (initData passed to server without
   apparent HMAC-bound verification)

Usage:
    python3 tma_initdata_audit.py --target https://your-tma-target/
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
from typing import List, Optional


_TMA_USAGE_RX = re.compile(r"Telegram\.WebApp\.initData(?:Unsafe)?\b", re.IGNORECASE)
_HMAC_VERIFY_RX = re.compile(r"createHmac|crypto\.subtle\.sign|hmac-sha256", re.IGNORECASE)
_AUTH_DATE_RX = re.compile(r"auth_date|authDate", re.IGNORECASE)
_BOT_TOKEN_RX = re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b")  # Telegram bot token format


@dataclass
class TMAFinding:
    finding_id: str
    issue: str
    severity_hint: str
    evidence: str
    location: str


@dataclass
class TMAReport:
    target: str
    tma_detected: bool
    findings: List[TMAFinding] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def _fetch(url: str, max_bytes: int = 5_000_000, timeout: float = 8.0) -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dapphunt-tma/1.0"})
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


def scan(target: str) -> TMAReport:
    report = TMAReport(target=target, tma_detected=False)
    counter = 1
    has_tma = False
    has_hmac = False
    has_auth_date = False
    bot_token_found = False

    for location, text in _gather(target):
        if _TMA_USAGE_RX.search(text):
            has_tma = True
        if _HMAC_VERIFY_RX.search(text):
            has_hmac = True
        if _AUTH_DATE_RX.search(text):
            has_auth_date = True
        if _BOT_TOKEN_RX.search(text):
            bot_token_found = True
            m = _BOT_TOKEN_RX.search(text)
            report.findings.append(TMAFinding(
                finding_id=f"TMA{counter:03d}",
                issue="Telegram bot token (or token-shaped string) found in frontend bundle. Bot tokens grant full bot control — never bundle them.",
                severity_hint="critical",
                evidence=m.group(0)[:30] + "...",
                location=location,
            ))
            counter += 1

    report.tma_detected = has_tma
    if not has_tma:
        report.notes.append("No Telegram.WebApp.initData usage detected.")
        return report

    if not has_hmac:
        report.findings.append(TMAFinding(
            finding_id=f"TMA{counter:03d}",
            issue="Telegram.WebApp.initData is consumed but no HMAC-SHA256 verification primitive (createHmac / crypto.subtle.sign) is visible in the bundle. Verify server-side validation exists; if absent, initData is forgeable.",
            severity_hint="medium",
            evidence="(no HMAC primitive found)",
            location=target,
        ))
        counter += 1
    if not has_auth_date:
        report.findings.append(TMAFinding(
            finding_id=f"TMA{counter:03d}",
            issue="No `auth_date` field handling visible. initData replay window may be unbounded.",
            severity_hint="medium",
            evidence="(no auth_date handling)",
            location=target,
        ))
        counter += 1
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
        print(f"TMA detected: {report.tma_detected}")
        for f in report.findings:
            print(f"  [{f.severity_hint:8}] {f.finding_id}: {f.issue}")
    return 0 if not report.findings else 1


if __name__ == "__main__":
    sys.exit(main())
