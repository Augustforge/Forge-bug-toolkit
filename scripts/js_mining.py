#!/usr/bin/env python3
"""
JS mining — extracts API endpoints and secrets from a site's JS files.
Downloads all JS, runs linkfinder + secretfinder + custom regexes.

Usage:
    python3 js_mining.py --domain example.com --output ./out
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# Regexes for secrets (if secretfinder is unavailable)
SECRET_PATTERNS = {
    "aws_access_key": r"AKIA[0-9A-Z]{16}",
    "aws_secret": r"(?i)aws_secret[_a-z]*\s*[:=]\s*['\"][a-zA-Z0-9/+=]{40}['\"]",
    "google_api": r"AIza[0-9A-Za-z\-_]{35}",
    "stripe_live": r"sk_live_[0-9a-zA-Z]{24,}",
    "stripe_pub": r"pk_live_[0-9a-zA-Z]{24,}",
    "github_token": r"gh[pousr]_[A-Za-z0-9_]{36,}",
    "slack_token": r"xox[baprs]-[0-9a-zA-Z\-]{10,48}",
    "jwt": r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
    "private_key": r"-----BEGIN [A-Z ]+PRIVATE KEY-----",
    "generic_api_key": r"(?i)(api[_-]?key|apikey|secret|token)\s*[:=]\s*['\"][a-zA-Z0-9_\-]{20,}['\"]",
    "firebase_url": r"https://[a-z0-9-]+\.firebaseio\.com",
}

# Regexes for endpoints
ENDPOINT_PATTERNS = [
    r"['\"](\/api\/[a-zA-Z0-9_\-/.]+)['\"]",
    r"['\"](\/v[0-9]+\/[a-zA-Z0-9_\-/.]+)['\"]",
    r"['\"](\/admin\/[a-zA-Z0-9_\-/.]+)['\"]",
    r"['\"](\/internal\/[a-zA-Z0-9_\-/.]+)['\"]",
    r"['\"](\/graphql[a-zA-Z0-9_\-/.]*)['\"]",
]


def fetch_page(url: str) -> str:
    try:
        r = requests.get(url, timeout=15, verify=False,
                         headers={"User-Agent": "Mozilla/5.0 (BBT)"})
        return r.text
    except Exception as e:
        print(f"  fetch failed for {url}: {e}", file=sys.stderr)
        return ""


def extract_js_urls(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls = set()
    for s in soup.find_all("script", src=True):
        urls.add(urljoin(base_url, s["src"]))
    return list(urls)


def find_secrets(content: str) -> dict:
    found = {}
    for name, pattern in SECRET_PATTERNS.items():
        matches = re.findall(pattern, content)
        if matches:
            found[name] = list(set(matches[:10]))
    return found


def find_endpoints(content: str) -> list[str]:
    eps = set()
    for pattern in ENDPOINT_PATTERNS:
        for m in re.findall(pattern, content):
            eps.add(m if isinstance(m, str) else m[0])
    return sorted(eps)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    requests.packages.urllib3.disable_warnings()

    base_url = f"https://{args.domain}"
    print(f"[*] Fetching: {base_url}")
    html = fetch_page(base_url)

    if not html:
        print("[!] Could not fetch base page")
        sys.exit(1)

    js_urls = extract_js_urls(html, base_url)
    print(f"[*] Found {len(js_urls)} JS files")

    results = {
        "domain": args.domain,
        "js_files": [],
        "secrets": {},
        "endpoints": [],
    }

    all_endpoints = set()

    for js_url in js_urls[:50]:  # limit so it doesn't hang
        print(f"[*] Mining: {js_url}")
        content = fetch_page(js_url)
        if not content:
            continue

        secrets = find_secrets(content)
        endpoints = find_endpoints(content)

        results["js_files"].append({
            "url": js_url,
            "size": len(content),
            "secrets_found": list(secrets.keys()),
            "endpoints_count": len(endpoints),
        })

        if secrets:
            results["secrets"][js_url] = secrets
            print(f"    [!] SECRETS: {list(secrets.keys())}")

        all_endpoints.update(endpoints)

    results["endpoints"] = sorted(all_endpoints)

    summary = out / "js_mining.json"
    summary.write_text(json.dumps(results, indent=2))

    print(f"[+] JS mining complete:")
    print(f"    JS files scanned : {len(results['js_files'])}")
    print(f"    Secrets found    : {sum(len(v) for v in results['secrets'].values())}")
    print(f"    Endpoints found  : {len(all_endpoints)}")
    print(f"[+] Saved to {summary}")


if __name__ == "__main__":
    main()
