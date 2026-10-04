#!/usr/bin/env python3
"""
reputation_builder.py — Track our handle reputation across platforms.

Reputation matters: HackerOne points, Immunefi Whitehat Level, Sherlock contest rank.
This script tracks what we have across handles → strategic platform choice.

Stored: ~/.bbt/reputation.json
"""

import argparse
import json
from datetime import date
from pathlib import Path

STORE_PATH = Path.home() / ".bbt" / "reputation.json"


def load() -> dict:
    if not STORE_PATH.exists():
        return {}
    return json.loads(STORE_PATH.read_text(encoding="utf-8"))


def save(data: dict):
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--update", action="store_true")
    p.add_argument("--show", action="store_true")
    p.add_argument("--platform")
    p.add_argument("--handle")
    p.add_argument("--metric", help="e.g., 'level', 'points', 'rank'")
    p.add_argument("--value", help="Value of the metric")
    args = p.parse_args()

    store = load()

    if args.update:
        if not all([args.platform, args.handle, args.metric, args.value]):
            print("ERROR: --update requires --platform --handle --metric --value")
            return 1
        entry = store.setdefault(args.platform, {}).setdefault(args.handle, {})
        entry.setdefault("history", []).append({
            "date": str(date.today()),
            "metric": args.metric,
            "value": args.value,
        })
        entry[args.metric] = args.value
        save(store)
        print(f"[+] Updated {args.platform}/{args.handle}.{args.metric} = {args.value}")
    elif args.show:
        if not store:
            print("(no reputation data)")
            return 0
        for platform, handles in store.items():
            print(f"\n## {platform}")
            for handle, info in handles.items():
                print(f"  Handle: {handle}")
                for k, v in info.items():
                    if k == "history":
                        continue
                    print(f"    {k}: {v}")
    else:
        p.print_help()
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
