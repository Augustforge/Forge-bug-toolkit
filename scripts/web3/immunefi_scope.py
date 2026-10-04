#!/usr/bin/env python3
"""
Immunefi scope checker.

Immunefi has no official public API. Uses community-maintained JSON:
https://github.com/infosec-us-team/Immunefi-Bug-Bounty-Programs-Unofficial

Cached locally (~/.bbt/cache/immunefi/projects.json), TTL 1 hour.

Usage:
    python3 immunefi_scope.py --address 0x...
    python3 immunefi_scope.py --protocol uniswap
    python3 immunefi_scope.py --list-new       # programs from last 7 days
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests


def _parse_ts(value) -> float:
    """Best-effort ISO-8601 / unix-epoch parsing. Returns 0 on failure."""
    if not value:
        return 0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except Exception:
            try:
                return float(value)
            except Exception:
                return 0
    return 0


def _scope_url(p: dict) -> str:
    slug = p.get("slug")
    if slug:
        return f"https://immunefi.com/bug-bounty/{slug}/"
    return p.get("url") or ""

PROJECTS_URL = (
    "https://raw.githubusercontent.com/"
    "infosec-us-team/Immunefi-Bug-Bounty-Programs-Unofficial/main/projects.json"
)
CACHE = Path.home() / ".bbt" / "cache" / "immunefi" / "projects.json"
CACHE_TTL = 3600


def load_projects() -> list[dict]:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    if CACHE.exists() and time.time() - CACHE.stat().st_mtime < CACHE_TTL:
        try:
            return json.loads(CACHE.read_text())
        except Exception:
            pass
    try:
        r = requests.get(PROJECTS_URL, timeout=30)
        if r.status_code != 200:
            return []
        data = r.json()
        CACHE.write_text(json.dumps(data))
        return data
    except Exception:
        return []


def find_by_address(projects: list[dict], address: str) -> list[dict]:
    addr = address.lower()
    matches = []
    for p in projects:
        for asset in p.get("assets", []) or []:
            asset_url = (asset.get("url") or "").lower()
            asset_id = (asset.get("id") or "").lower()
            if addr in asset_url or addr == asset_id:
                matches.append({
                    "project": p.get("project"),
                    "max_bounty": p.get("maxBounty"),
                    "kyc_required": bool(p.get("kyc") or p.get("requireKYC")),
                    "asset_url": asset.get("url"),
                    "asset_type": asset.get("type"),
                    "scope_url": _scope_url(p),
                })
    return matches


def find_by_protocol(projects: list[dict], name: str) -> list[dict]:
    n = name.lower()
    matches = []
    for p in projects:
        if n in (p.get("project") or "").lower():
            matches.append({
                "project": p.get("project"),
                "max_bounty": p.get("maxBounty"),
                "kyc_required": bool(p.get("kyc") or p.get("requireKYC")),
                "assets_count": len(p.get("assets", []) or []),
                "scope_url": _scope_url(p),
            })
    return matches


def list_new(projects: list[dict], days: int = 30) -> list[dict]:
    """Programs launched in last N days.

    Uses `launchDate` (when program went live) — semantically "new programs".
    `updatedDate` is unreliable as freshness signal: community repo bumps it
    on every scrape, so all programs look "updated today".

    Default window 30d (default for `--list-new`); Immunefi typically adds
    only a few programs per week, so 7d often returns 0.
    """
    cutoff = time.time() - days * 86400
    out = []
    for p in projects:
        launch_ts = _parse_ts(p.get("launchDate") or p.get("date"))
        if launch_ts and launch_ts > cutoff:
            out.append({
                "project": p.get("project"),
                "max_bounty": p.get("maxBounty"),
                "kyc_required": bool(p.get("kyc") or p.get("requireKYC")),
                "launch_date": p.get("launchDate"),
                "scope_url": _scope_url(p),
            })
    out.sort(key=lambda x: x.get("launch_date") or "", reverse=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--address", help="Contract address")
    ap.add_argument("--protocol", help="Project name substring")
    ap.add_argument("--list-new", action="store_true",
                    help="List programs from last 7 days")
    ap.add_argument("--output")
    args = ap.parse_args()

    projects = load_projects()
    if not projects:
        print(json.dumps({"error": "could not load Immunefi data"}))
        sys.exit(1)

    if args.address:
        result = {"matches": find_by_address(projects, args.address)}
    elif args.protocol:
        result = {"matches": find_by_protocol(projects, args.protocol)}
    elif args.list_new:
        result = {"new_programs": list_new(projects)}
    else:
        result = {
            "total_programs": len(projects),
            "sample": [p.get("project") for p in projects[:10]],
        }

    out = json.dumps(result, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(out)
    print(out)


if __name__ == "__main__":
    main()
