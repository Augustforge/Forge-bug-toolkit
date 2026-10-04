#!/usr/bin/env python3
"""
Twitter/X monitor via Nitter RSS instances.
Tracks security researcher accounts for fresh exploit announcements.

Output: list of new high-severity tweets (last 24h)
"""

import argparse
import json
import sys
import time
from pathlib import Path

from _common import (SOURCES, classify, fetch, parse_rss,
                     load_seen, save_seen, hash_id)


def fetch_account(account: str) -> list[dict]:
    """Try Nitter instances until one works."""
    for instance in SOURCES["twitter_nitter_instances"]:
        url = f"{instance}/{account}/rss"
        r = fetch(url, timeout=10, retries=1)
        if r and r.status_code == 200:
            entries = parse_rss(r.content)
            for e in entries:
                e["account"] = account
                e["source"] = "twitter"
            return entries
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    ap.add_argument("--severity-floor", default="medium",
                    choices=["high", "medium", "low"],
                    help="Skip entries below this severity")
    args = ap.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    seen = load_seen("twitter")
    fresh: list[dict] = []
    sev_order = {"high": 3, "medium": 2, "low": 1, "noise": 0}
    floor = sev_order[args.severity_floor]

    for account in SOURCES["twitter_accounts"]:
        print(f"[*] {account}")
        entries = fetch_account(account)
        time.sleep(1)
        for e in entries:
            text = f"{e['title']} {e['description']}"
            severity, matched = classify(text)
            if sev_order.get(severity, 0) < floor:
                continue
            tid = hash_id(e["link"])
            if tid in seen:
                continue
            seen.add(tid)
            fresh.append({
                "id": tid,
                "source": "twitter",
                "account": account,
                "severity": severity,
                "matched_keywords": matched,
                "title": e["title"],
                "link": e["link"],
                "date": e["date"],
                "description": e["description"][:200],
            })

    save_seen("twitter", seen)
    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_new": len(fresh),
        "by_severity": {
            sev: sum(1 for e in fresh if e["severity"] == sev)
            for sev in ("high", "medium", "low")
        },
        "entries": sorted(fresh, key=lambda x: sev_order.get(x["severity"], 0), reverse=True),
    }
    (out / "twitter.json").write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"[+] {len(fresh)} new entries — {output['by_severity']}")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
