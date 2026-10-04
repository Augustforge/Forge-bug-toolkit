#!/usr/bin/env python3
"""
GitHub monitor — stars surge, new repos, suspicious commits.

Outputs:
- Trending Solidity repos
- Stars surge in watchlist orgs (>50% week-over-week)
- New public Solidity repos in last 7 days
- Recent commits with suspicious keywords (fix critical, emergency, revert)
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import SOURCES, fetch, hash_id

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
HEADERS = {"Accept": "application/vnd.github+json"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"

SUSPICIOUS_COMMIT_KEYWORDS = [
    "fix critical", "security patch", "emergency", "revert pause",
    "hotfix", "vulnerability", "CVE-", "disclose",
]


def trending_solidity():
    """GitHub trending Solidity repos via search API (proxy for trending)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d")
    try:
        r = requests.get(
            "https://api.github.com/search/repositories",
            headers=HEADERS,
            params={
                "q": f"language:Solidity created:>{cutoff} stars:>10",
                "sort": "stars", "order": "desc", "per_page": 20,
            }, timeout=20,
        )
        if r.status_code != 200:
            return []
        return [
            {"name": i["full_name"], "stars": i["stargazers_count"],
             "url": i["html_url"], "created": i["created_at"],
             "description": i.get("description") or ""}
            for i in r.json().get("items", [])
        ]
    except Exception:
        return []


def stars_surge(org: str) -> list[dict]:
    """Compare current stars vs cached snapshot for org's top repos."""
    try:
        r = requests.get(
            f"https://api.github.com/orgs/{org}/repos",
            headers=HEADERS,
            params={"sort": "updated", "per_page": 30}, timeout=20,
        )
        if r.status_code != 200:
            return []
    except Exception:
        return []

    cache_file = Path.home() / ".bbt" / "cache" / "monitors" / f"github_stars_{org}.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    prev = {}
    if cache_file.exists():
        try:
            prev = json.loads(cache_file.read_text())
        except Exception:
            pass

    surges = []
    current = {}
    for repo in r.json():
        name = repo["full_name"]
        stars = repo["stargazers_count"]
        current[name] = stars
        if name in prev and prev[name] > 0:
            growth = (stars - prev[name]) / prev[name] * 100
            if growth >= 50:
                surges.append({
                    "name": name, "url": repo["html_url"],
                    "stars_before": prev[name], "stars_after": stars,
                    "growth_percent": round(growth, 1),
                })
    cache_file.write_text(json.dumps(current))
    return surges


def suspicious_commits(org: str) -> list[dict]:
    """Recent commits with suspicious keywords."""
    found = []
    try:
        r = requests.get(
            f"https://api.github.com/orgs/{org}/repos",
            headers=HEADERS, params={"per_page": 10, "sort": "pushed"}, timeout=20,
        )
        if r.status_code != 200:
            return []
        for repo in r.json()[:5]:
            cr = requests.get(
                f"{repo['url']}/commits", headers=HEADERS,
                params={"per_page": 20}, timeout=20,
            )
            if cr.status_code != 200:
                continue
            for c in cr.json():
                msg = c.get("commit", {}).get("message", "").lower()
                matched = [kw for kw in SUSPICIOUS_COMMIT_KEYWORDS if kw in msg]
                if matched:
                    found.append({
                        "repo": repo["full_name"],
                        "sha": c["sha"][:10],
                        "url": c["html_url"],
                        "message": msg[:200],
                        "matched": matched,
                    })
            time.sleep(0.5)
    except Exception:
        pass
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    if not GITHUB_TOKEN:
        print("[!] GITHUB_TOKEN not set — heavy rate limits expected")

    print("[*] Trending Solidity repos...")
    trending = trending_solidity()
    print(f"    {len(trending)} repos")

    surges = []
    suspicious = []
    for org in SOURCES["github_orgs_watchlist"]:
        print(f"[*] {org} — stars surge & suspicious commits")
        surges.extend(stars_surge(org))
        suspicious.extend(suspicious_commits(org))
        time.sleep(1)

    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "trending_solidity": trending,
        "stars_surges": surges,
        "suspicious_commits": suspicious,
    }
    (out / "github.json").write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"[+] {len(trending)} trending | {len(surges)} surges | {len(suspicious)} suspicious commits")


if __name__ == "__main__":
    main()
