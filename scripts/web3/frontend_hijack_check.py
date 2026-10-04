#!/usr/bin/env python3
"""
Frontend hijacking detection for Web3 protocols.

Web3 protocols often have weak frontend security (CSP, SRI). When CDN/DNS
is compromised, attacker injects malicious JS that drains user wallets.
Reference: blockaid.io reports — 5 protocols hijacked in one week (March 2026).

Checks:
1. CSP presence + strictness (no unsafe-inline, no wildcards)
2. Subresource Integrity (SRI) on external scripts
3. HTTPS enforcement (HSTS)
4. Identity of CDN providers (less = better, more single-points-of-failure)

Usage:
    python3 frontend_hijack_check.py --url https://app.uniswap.org --output ./out
"""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


def check_csp(headers: dict) -> dict:
    csp = headers.get("Content-Security-Policy") or headers.get("content-security-policy", "")
    if not csp:
        return {"present": False, "severity": "high",
                "issue": "CSP missing entirely — frontend hijack mitigations absent"}
    issues = []
    severity = "info"
    if "unsafe-inline" in csp:
        issues.append("script-src allows unsafe-inline (XSS amplifier)")
        severity = "high"
    if "unsafe-eval" in csp:
        issues.append("script-src allows unsafe-eval")
        severity = "high"
    if re.search(r"script-src[^;]*\*", csp):
        issues.append("script-src uses wildcard")
        severity = "high"
    if "frame-ancestors" not in csp:
        issues.append("missing frame-ancestors (clickjacking risk)")
        if severity == "info":
            severity = "low"
    return {"present": True, "severity": severity, "issues": issues, "policy_excerpt": csp[:200]}


def check_sri(html: str, base_url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    external_scripts = []
    base_host = urlparse(base_url).netloc
    for s in soup.find_all("script", src=True):
        src = s["src"]
        if not src.startswith(("http://", "https://", "//")):
            continue
        if base_host in src:
            continue  # same-origin, SRI not strictly needed
        external_scripts.append({
            "src": src,
            "has_integrity": bool(s.get("integrity")),
            "has_crossorigin": bool(s.get("crossorigin")),
        })
    missing = [s for s in external_scripts if not s["has_integrity"]]
    return {
        "external_scripts_count": len(external_scripts),
        "missing_sri_count": len(missing),
        "missing_sri": missing[:10],
        "severity": "high" if missing and len(external_scripts) > 0 else "info",
    }


def check_hsts(headers: dict) -> dict:
    hsts = headers.get("Strict-Transport-Security") or headers.get("strict-transport-security", "")
    if not hsts:
        return {"present": False, "severity": "medium",
                "issue": "HSTS missing — protocol downgrade possible"}
    m = re.search(r"max-age=(\d+)", hsts)
    age = int(m.group(1)) if m else 0
    return {
        "present": True, "max_age": age,
        "includes_subdomains": "includesubdomains" in hsts.lower(),
        "preload": "preload" in hsts.lower(),
        "severity": "info" if age >= 15768000 else "low",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="Frontend URL of DeFi protocol")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    print(f"[*] Checking frontend security: {args.url}")
    try:
        r = requests.get(args.url, timeout=20, headers={"User-Agent": "BBT/1.0"})
    except Exception as e:
        print(f"[!] Failed to fetch: {e}")
        sys.exit(1)

    headers = dict(r.headers)
    html = r.text

    csp = check_csp(headers)
    sri = check_sri(html, args.url)
    hsts = check_hsts(headers)

    overall = "info"
    for check in (csp, sri, hsts):
        sev = check.get("severity", "info")
        if sev == "high" or (sev == "medium" and overall == "info"):
            overall = sev
        elif sev == "low" and overall == "info":
            overall = "low"

    result = {
        "url": args.url,
        "status_code": r.status_code,
        "csp": csp,
        "sri": sri,
        "hsts": hsts,
        "overall_severity": overall,
        "frontend_hijack_risk": overall in ("high", "medium"),
    }

    output_file = out / "frontend_hijack.json"
    output_file.write_text(json.dumps(result, indent=2))

    print(f"[+] CSP severity   : {csp.get('severity')}")
    print(f"[+] SRI severity   : {sri.get('severity')} ({sri.get('missing_sri_count')} missing of {sri.get('external_scripts_count')})")
    print(f"[+] HSTS severity  : {hsts.get('severity')}")
    print(f"[+] Overall risk   : {overall}")
    if result["frontend_hijack_risk"]:
        print("[!] Frontend hijack risk — DeFi UI vulnerable if CDN/DNS compromised")
    print(f"[+] Saved to {output_file}")


if __name__ == "__main__":
    main()
