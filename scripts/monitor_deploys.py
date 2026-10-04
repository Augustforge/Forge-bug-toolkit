#!/usr/bin/env python3
"""
Monitor deploys — tracks GitHub releases and new repositories
of companies on the watchlist. Fresh code = more vulnerabilities.

Usage:
    python3 monitor_deploys.py --watchlist orgs.txt --output ./out
"""

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
HEADERS = {"Accept": "application/vnd.github+json"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"


def recent_releases(org: str, hours: int = 72) -> list[dict]:
    """Releases from the last N hours."""
    try:
        r = requests.get(
            f"https://api.github.com/orgs/{org}/events",
            headers=HEADERS,
            params={"per_page": 100},
            timeout=30,
        )
        if r.status_code != 200:
            return [{"error": f"HTTP {r.status_code}"}]
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        results = []
        for e in r.json():
            if e.get("type") not in ("ReleaseEvent", "PushEvent", "CreateEvent"):
                continue
            created = datetime.fromisoformat(e["created_at"].replace("Z", "+00:00"))
            if created < cutoff:
                continue
            results.append({
                "type": e["type"],
                "repo": e.get("repo", {}).get("name"),
                "created_at": e["created_at"],
                "actor": e.get("actor", {}).get("login"),
                "ref": e.get("payload", {}).get("ref"),
            })
        return results
    except Exception as e:
        return [{"error": str(e)}]


def new_repos(org: str, days: int = 14) -> list[dict]:
    """New public repos from the last N days."""
    try:
        r = requests.get(
            f"https://api.github.com/orgs/{org}/repos",
            headers=HEADERS,
            params={"sort": "created", "direction": "desc", "per_page": 50},
            timeout=30,
        )
        if r.status_code != 200:
            return [{"error": f"HTTP {r.status_code}"}]
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        results = []
        for repo in r.json():
            created = datetime.fromisoformat(repo["created_at"].replace("Z", "+00:00"))
            if created < cutoff:
                break
            results.append({
                "name": repo["full_name"],
                "url": repo["html_url"],
                "created_at": repo["created_at"],
                "language": repo.get("language"),
                "description": repo.get("description"),
            })
        return results
    except Exception as e:
        return [{"error": str(e)}]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--watchlist", required=True,
                    help="File with one GitHub org per line")
    ap.add_argument("--output", required=True)
    ap.add_argument("--hours", type=int, default=72,
                    help="Look back window for releases (hours)")
    ap.add_argument("--days", type=int, default=14,
                    help="Look back window for new repos (days)")
    args = ap.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    watchlist_path = Path(args.watchlist)
    if not watchlist_path.exists():
        print(f"[!] Watchlist not found: {watchlist_path}")
        print("[i] Create it with one org name per line, e.g.:")
        print("    coinbase")
        print("    uniswap-labs")
        print("    aave")
        return

    orgs = [line.strip() for line in watchlist_path.read_text().splitlines()
            if line.strip() and not line.startswith("#")]

    print(f"[*] Monitoring {len(orgs)} orgs (releases: {args.hours}h, new repos: {args.days}d)")
    if not GITHUB_TOKEN:
        print("[!] GITHUB_TOKEN not set — heavy rate limits")

    results = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "watchlist": orgs,
        "by_org": {},
    }

    for org in orgs:
        print(f"[*] Checking: {org}")
        releases = recent_releases(org, args.hours)
        repos = new_repos(org, args.days)
        results["by_org"][org] = {
            "recent_activity": releases,
            "new_repos": repos,
        }
        print(f"    activity: {len(releases)} | new repos: {len(repos)}")

    summary = out / "monitor.json"
    summary.write_text(json.dumps(results, indent=2, default=str))
    print(f"[+] Saved to {summary}")


if __name__ == "__main__":
    main()
