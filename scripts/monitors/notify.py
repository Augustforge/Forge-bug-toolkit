#!/usr/bin/env python3
"""
Telegram bot notifier — push alerts to the operator's private channel.

ENV:
  TELEGRAM_BOT_TOKEN   bot token from @BotFather
  TELEGRAM_CHAT_ID     chat ID (get via @userinfobot)

Usage:
  python3 notify.py --message "text"
  python3 notify.py --from-aggregated path/to/aggregated.json --severity high
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def send(text: str, parse_mode: str = "Markdown") -> bool:
    if not TOKEN or not CHAT_ID:
        print("[!] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        return False
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={
            "chat_id": CHAT_ID, "text": text[:4000],
            "parse_mode": parse_mode, "disable_web_page_preview": "true",
        }, timeout=15)
        if r.status_code == 200:
            return True
        # Telegram rejected Markdown (e.g. unescaped _ in usernames) — retry plain text
        r2 = requests.post(url, data={
            "chat_id": CHAT_ID, "text": text[:4000],
            "disable_web_page_preview": "true",
        }, timeout=15)
        return r2.status_code == 200
    except Exception as e:
        print(f"[!] Send failed: {e}")
        return False


def format_entry(e: dict) -> str:
    sev = e.get("severity", "?").upper()
    src = e.get("source", "?")
    icon = {"high": "🚨", "medium": "⚠️", "low": "ℹ️"}.get(e.get("severity"), "•")
    title = e.get("title", "")
    link = e.get("link", "")
    score = e.get("score", "?")
    return f"{icon} *{sev}* `[{src}]` (score: {score})\n{title}\n{link}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--message", help="Send arbitrary text")
    ap.add_argument("--from-aggregated", help="Path to aggregated.json")
    ap.add_argument("--severity", default="high", choices=["high", "medium", "low"])
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

    if args.message:
        ok = send(args.message)
        sys.exit(0 if ok else 1)

    if args.from_aggregated:
        data = json.loads(Path(args.from_aggregated).read_text())
        floor = {"high": 3, "medium": 2, "low": 1}[args.severity]
        sev_w = {"high": 3, "medium": 2, "low": 1}
        eligible = [e for e in data.get("top", [])
                    if sev_w.get(e.get("severity"), 0) >= floor][:args.limit]
        if not eligible:
            print(f"[i] No {args.severity}+ signals to send")
            return
        header = f"*BBT alert* — {len(eligible)} signal(s) ≥ {args.severity}"
        body = "\n\n".join(format_entry(e) for e in eligible)
        send(f"{header}\n\n{body}")
        print(f"[+] Sent {len(eligible)} alerts")
        return

    ap.error("Need --message or --from-aggregated")


if __name__ == "__main__":
    main()
