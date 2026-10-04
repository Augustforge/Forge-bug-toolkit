#!/usr/bin/env python3
"""
Telegram channels monitor via RSSHub bridge.
Tracks security communities for fresh alerts/postmortems.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (SOURCES, classify, fetch, parse_rss,
                     load_seen, save_seen, hash_id)


def fetch_channel(channel: str) -> list[dict]:
    url = f"{SOURCES['telegram_rss_bridge']}/{channel}"
    r = fetch(url, timeout=15, retries=2)
    if not r or r.status_code != 200:
        return []
    entries = parse_rss(r.content)
    for e in entries:
        e["channel"] = channel
        e["source"] = "telegram"
    return entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    ap.add_argument("--severity-floor", default="medium")
    args = ap.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    sev_order = {"high": 3, "medium": 2, "low": 1, "noise": 0}
    floor = sev_order.get(args.severity_floor, 2)
    seen = load_seen("telegram")
    fresh = []

    for channel in SOURCES["telegram_channels"]:
        print(f"[*] @{channel}")
        entries = fetch_channel(channel)
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
                "id": tid, "source": "telegram", "channel": channel,
                "severity": severity, "matched_keywords": matched,
                "title": e["title"][:200], "link": e["link"],
                "date": e["date"], "description": e["description"][:300],
            })

    save_seen("telegram", seen)
    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_new": len(fresh),
        "entries": sorted(fresh, key=lambda x: sev_order.get(x["severity"], 0), reverse=True),
    }
    (out / "telegram.json").write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"[+] {len(fresh)} new entries")


if __name__ == "__main__":
    main()
