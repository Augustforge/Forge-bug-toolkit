#!/usr/bin/env python3
"""
GitHub recon — searches for leaked keys/passwords by domain or org.
Uses GitHub Code Search API + gitleaks/trufflehog for deep scanning.

Usage:
    python3 github_recon.py --domain example.com --output ./out
    python3 github_recon.py --org companyname --output ./out
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"

# Dorks that work via GitHub Code Search
DORKS = [
    '"{target}" password',
    '"{target}" api_key',
    '"{target}" apikey',
    '"{target}" secret',
    '"{target}" token',
    '"{target}" "AWS_SECRET"',
    '"{target}" "DB_PASSWORD"',
    '"{target}" filename:.env',
    '"{target}" filename:config',
    '"{target}" filename:.npmrc _auth',
    '"{target}" "BEGIN RSA PRIVATE KEY"',
    '"{target}" "client_secret"',
    '"{target}" "Bearer "',
]


def search_code(query: str, per_page: int = 30):
    """Search via GitHub Code Search API."""
    if not GITHUB_TOKEN:
        return {"error": "GITHUB_TOKEN not set, code search requires auth"}
    url = "https://api.github.com/search/code"
    try:
        r = requests.get(url, headers=HEADERS,
                         params={"q": query, "per_page": per_page}, timeout=30)
        if r.status_code == 200:
            return r.json()
        if r.status_code == 403:
            time.sleep(60)
            return {"error": "rate limited"}
        return {"error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"error": str(e)}


def list_org_repos(org: str):
    """List of public repos of the organization."""
    repos = []
    page = 1
    while True:
        try:
            r = requests.get(
                f"https://api.github.com/orgs/{org}/repos",
                headers=HEADERS,
                params={"per_page": 100, "page": page, "type": "public"},
                timeout=30,
            )
            if r.status_code != 200:
                break
            batch = r.json()
            if not batch:
                break
            repos.extend(batch)
            page += 1
            if page > 10:
                break
        except Exception:
            break
    return repos


def scan_repo_with_trufflehog(repo_url: str, output_file: Path):
    """Run trufflehog over the repo."""
    try:
        result = subprocess.run(
            ["trufflehog", "git", repo_url, "--json", "--no-update"],
            capture_output=True, text=True, timeout=300,
        )
        if result.stdout:
            output_file.write_text(result.stdout)
            return result.stdout.count("\n")
        return 0
    except Exception as e:
        return f"error: {e}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", help="Domain to search for")
    ap.add_argument("--org", help="GitHub organization name")
    ap.add_argument("--output", required=True, help="Output directory")
    ap.add_argument("--deep-scan", action="store_true",
                    help="Run trufflehog on each org repo (slow)")
    args = ap.parse_args()

    if not args.domain and not args.org:
        ap.error("Need --domain or --org")

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    results = {
        "target": args.domain or args.org,
        "type": "domain" if args.domain else "org",
        "github_token_used": bool(GITHUB_TOKEN),
        "dork_results": {},
        "org_repos": [],
        "trufflehog_findings": {},
    }

    # ─── DORK SEARCH ──────────────────────────────────────────────────────────
    target = args.domain or args.org
    print(f"[*] Running {len(DORKS)} GitHub dorks for: {target}")

    for dork_template in DORKS:
        query = dork_template.format(target=target)
        print(f"[*] Dork: {query}")
        res = search_code(query)
        results["dork_results"][query] = res
        if "items" in res:
            print(f"    → {res.get('total_count', 0)} hits")
        time.sleep(2)  # rate limit friendly

    # ─── ORG REPO ENUMERATION ─────────────────────────────────────────────────
    if args.org:
        print(f"[*] Enumerating public repos for org: {args.org}")
        repos = list_org_repos(args.org)
        results["org_repos"] = [
            {"name": r["full_name"], "url": r["clone_url"],
             "stars": r["stargazers_count"], "updated": r["updated_at"]}
            for r in repos
        ]
        print(f"    → found {len(repos)} repos")

        if args.deep_scan and repos:
            print(f"[*] Deep scan with trufflehog on {len(repos)} repos...")
            tf_dir = out / "trufflehog"
            tf_dir.mkdir(exist_ok=True)
            for r in repos[:20]:
                name = r["full_name"].replace("/", "_")
                f = tf_dir / f"{name}.json"
                count = scan_repo_with_trufflehog(r["clone_url"], f)
                results["trufflehog_findings"][r["full_name"]] = count
                print(f"    {r['full_name']}: {count}")

    # ─── SAVE ─────────────────────────────────────────────────────────────────
    summary_file = out / "github_recon.json"
    summary_file.write_text(json.dumps(results, indent=2, default=str))
    print(f"[+] Saved to {summary_file}")


if __name__ == "__main__":
    main()
