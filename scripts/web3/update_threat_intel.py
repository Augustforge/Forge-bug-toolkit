#!/usr/bin/env python3
"""
Update threat_intel.md with fresh DeFi exploit postmortems and security research.

Pulls from RSS feeds:
- rekt.news, Blockaid blog, Trail of Bits, OpenZeppelin, ConsenSys Diligence
- Immunefi disclosed reports, a16z Crypto, Paradigm, PortSwigger Research

Output: appends a "Recently Added" section at the top of threat_intel.md
with new entries from last 30 days.

Usage:
    python3 update_threat_intel.py
    python3 update_threat_intel.py --days 7
"""

import argparse
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

THREAT_INTEL_FILE = Path(__file__).resolve().parent / "threat_intel.md"

SOURCES = [
    {"name": "rekt.news", "feed": "https://rekt.news/feed/", "tag": "🔥 EXPLOIT"},
    {"name": "Blockaid", "feed": "https://www.blockaid.io/blog/rss.xml", "tag": "🛡 RESEARCH"},
    {"name": "Trail of Bits", "feed": "https://blog.trailofbits.com/feed.xml", "tag": "🛡 RESEARCH"},
    {"name": "OpenZeppelin", "feed": "https://blog.openzeppelin.com/rss.xml", "tag": "🛡 RESEARCH"},
    {"name": "ConsenSys Diligence", "feed": "https://consensys.io/diligence/blog/rss.xml", "tag": "🛡 RESEARCH"},
    {"name": "PortSwigger Research", "feed": "https://portswigger.net/research/rss", "tag": "🌐 WEB"},
    {"name": "Immunefi", "feed": "https://medium.com/feed/immunefi", "tag": "💎 BOUNTY"},
    {"name": "a16z Crypto", "feed": "https://a16zcrypto.com/feed/", "tag": "🛡 RESEARCH"},
]

EXPLOIT_KEYWORDS = re.compile(
    r"\b(exploit|hack|drained|attack|vulnerability|incident|"
    r"compromised|breach|stolen|paused|emergency|postmortem|rekt)\b",
    re.IGNORECASE,
)


def parse_feed(url: str, tag: str, since: datetime) -> list[dict]:
    """Parse RSS/Atom feed, return entries newer than `since`."""
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "BBT/1.0"})
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
    except Exception as e:
        print(f"  [!] {url} failed: {e}", file=sys.stderr)
        return []

    entries = []
    items = (root.findall(".//item")
             or root.findall(".//{http://www.w3.org/2005/Atom}entry"))
    for item in items[:25]:
        title = _text(item, "title")
        link = _text(item, "link") or _attr(item, "{http://www.w3.org/2005/Atom}link", "href")
        pub_date = _text(item, "pubDate") or _text(item, "{http://www.w3.org/2005/Atom}updated")
        if not title or not link:
            continue
        published = _parse_date(pub_date)
        if published and published < since:
            continue
        entries.append({
            "title": title.strip(),
            "link": link.strip(),
            "published": published.isoformat() if published else "?",
            "tag": tag,
        })
    return entries


def _text(item, tag):
    el = item.find(tag)
    return el.text if el is not None and el.text else ""


def _attr(item, tag, attr):
    el = item.find(tag)
    return el.get(attr, "") if el is not None else ""


def _parse_date(s: str):
    if not s:
        return None
    fmts = [
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(s.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            continue
    return None


def render_section(entries: list[dict]) -> str:
    """Generate markdown for the 'Recently Added' section."""
    if not entries:
        return ""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [f"## Recently Added — updated {today}", ""]
    by_tag = {}
    for e in entries:
        by_tag.setdefault(e["tag"], []).append(e)

    for tag in sorted(by_tag.keys()):
        lines.append(f"### {tag}")
        lines.append("")
        for e in by_tag[tag][:10]:
            is_exploit = bool(EXPLOIT_KEYWORDS.search(e["title"]))
            marker = " 🚨" if is_exploit else ""
            lines.append(f"- [{e['title']}]({e['link']}){marker} — {e['published'][:10]}")
        lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def update_file(new_section: str):
    if not THREAT_INTEL_FILE.exists():
        print(f"[!] {THREAT_INTEL_FILE} not found")
        return
    content = THREAT_INTEL_FILE.read_text(encoding="utf-8")
    # Remove previous "Recently Added" section if exists
    content = re.sub(
        r"^## Recently Added.*?(?=^## [^R]|\Z)",
        "",
        content, flags=re.DOTALL | re.MULTILINE,
    )
    # Insert new section after the file's H1 / intro
    # Find the first '---' separator and insert after it
    parts = content.split("\n---\n", 1)
    if len(parts) == 2:
        content = parts[0] + "\n---\n\n" + new_section + parts[1]
    else:
        content = new_section + content
    THREAT_INTEL_FILE.write_text(content, encoding="utf-8")
    print(f"[+] Updated {THREAT_INTEL_FILE}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30,
                    help="Look back window in days (default: 30)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print to stdout, don't modify file")
    args = ap.parse_args()

    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    all_entries = []

    for src in SOURCES:
        print(f"[*] Fetching {src['name']}...")
        entries = parse_feed(src["feed"], src["tag"], since)
        print(f"    {len(entries)} new entries")
        all_entries.extend(entries)
        time.sleep(0.5)

    section = render_section(all_entries)
    if args.dry_run:
        print(section)
    else:
        update_file(section)
        print(f"[+] Total entries added: {len(all_entries)}")


if __name__ == "__main__":
    main()
