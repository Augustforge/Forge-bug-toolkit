#!/usr/bin/env python3
"""
pseudonym_manager.py — Manage handles per program.

Different GitHub/Twitter/HackerOne handle per hunt target program.
Prevents linkage between hunts.

Stored in: ~/.bbt/pseudonyms.json
"""

import argparse
import json
from pathlib import Path

STORE_PATH = Path.home() / ".bbt" / "pseudonyms.json"


def load() -> dict:
    if not STORE_PATH.exists():
        return {}
    return json.loads(STORE_PATH.read_text(encoding="utf-8"))


def save(data: dict):
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--add", action="store_true")
    p.add_argument("--list", action="store_true")
    p.add_argument("--target")
    p.add_argument("--platform", help="immunefi/hackerone/twitter/github/etc")
    p.add_argument("--handle")
    p.add_argument("--email")
    args = p.parse_args()

    store = load()

    if args.add:
        if not (args.target and args.platform and args.handle):
            print("ERROR: --add requires --target --platform --handle")
            return 1
        entry = store.setdefault(args.target, {})
        entry[args.platform] = {"handle": args.handle, "email": args.email}
        save(store)
        print(f"[+] Added {args.platform}={args.handle} for target={args.target}")
    elif args.list:
        if not store:
            print("(empty)")
        for target, platforms in store.items():
            print(f"\n{target}:")
            for platform, info in platforms.items():
                print(f"  {platform}: {info['handle']}  (email: {info.get('email', '-')})")
    else:
        p.print_help()
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
