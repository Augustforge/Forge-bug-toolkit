#!/usr/bin/env python3
"""
Cantina scope checker (https://cantina.xyz/opportunities).

Cantina has no public JSON API. Uses sitemap.xml as program index
(daily-updated, contains all bounties + competitions UUIDs).
Per-program details fetched lazily via SSR HTML parsing.

Cached locally (~/.bbt/cache/cantina/programs.json), TTL 1 hour.

Usage:
    python3 cantina_scope.py --list-new          # programs lastmod < 7 days
    python3 cantina_scope.py --protocol uniswap  # name substring search (slow, full enrich)
    python3 cantina_scope.py --enrich            # force enrich every program (slow first run)
"""

import argparse
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

SITEMAP_URL = "https://cantina.xyz/sitemap-0.xml"
BASE = "https://cantina.xyz"
CACHE_DIR = Path.home() / ".bbt" / "cache" / "cantina"
INDEX_CACHE = CACHE_DIR / "programs.json"
DETAIL_CACHE = CACHE_DIR / "details"
CACHE_TTL = 3600
HEADERS = {"User-Agent": "bbt-cantina-scope/1.0"}
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def load_index() -> list[dict]:
    """Pull sitemap, extract bounty + competition URLs with lastmod."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if INDEX_CACHE.exists() and time.time() - INDEX_CACHE.stat().st_mtime < CACHE_TTL:
        try:
            return json.loads(INDEX_CACHE.read_text(encoding="utf-8"))
        except Exception:
            pass
    try:
        r = requests.get(SITEMAP_URL, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.text)
    except Exception:
        return []

    out = []
    for url_node in root.findall("sm:url", NS):
        loc = (url_node.findtext("sm:loc", default="", namespaces=NS) or "").strip()
        lastmod = (url_node.findtext("sm:lastmod", default="", namespaces=NS) or "").strip()
        if "/bounties/" in loc:
            kind = "bounty"
        elif "/competitions/" in loc:
            kind = "contest"
        else:
            continue
        uuid = loc.rstrip("/").split("/")[-1]
        out.append({"uuid": uuid, "type": kind, "url": loc, "lastmod": lastmod})

    INDEX_CACHE.write_text(json.dumps(out), encoding="utf-8")
    return out


def _clean_name(raw: str) -> str:
    n = raw.strip()
    for suf in (" bounty | Cantina", " | Cantina", " - Cantina", " competition | Cantina"):
        if n.endswith(suf):
            n = n[: -len(suf)]
    return n.strip()


def _to_usd(num: str, suf: str) -> float:
    v = float(num.replace(",", ""))
    mult = {"K": 1e3, "M": 1e6, "B": 1e9}.get((suf or "").upper(), 1)
    return v * mult


_MONEY = r"\$\s?([0-9][0-9,]*(?:\.[0-9]+)?)\s?([KMB])?"
_PAYOUT_CAP_USD = 10_000_000  # bounty payouts rarely exceed $10M; above = likely TVL/claim


def _parse_detail(html: str) -> dict:
    """Extract project name + max payout + status from SSR HTML.

    Robust to minor markup drift: prefers og:title/<title> for name, scans for
    money near "Bounty"/"Reward"/"Critical" keywords (avoids picking up TVL/
    protocol claims in description). Returns best-effort dict; missing fields
    are None rather than raising.
    """
    name = None
    m = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', html, re.I)
    if m:
        name = _clean_name(m.group(1))
    if not name:
        m = re.search(r"<title>([^<]+)</title>", html, re.I)
        if m:
            name = _clean_name(m.group(1))

    flat = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))

    candidates: list[float] = []
    for kw in ("Max bounty", "Maximum bounty", "Max reward", "Total prize", "Prize pool",
               "Critical", "Reward"):
        for m in re.finditer(rf"\b{kw}\b[^$]{{0,80}}{_MONEY}", flat, re.I):
            v = _to_usd(m.group(1), m.group(2))
            if v <= _PAYOUT_CAP_USD:
                candidates.append(v)
    max_payout = max(candidates) if candidates else None

    if max_payout is None:
        all_money = [_to_usd(n, s) for n, s in re.findall(_MONEY, flat)]
        capped = [v for v in all_money if v <= _PAYOUT_CAP_USD]
        max_payout = max(capped) if capped else None

    status = None
    for s in ("Live", "Paused", "Ended", "Upcoming", "Active"):
        if re.search(rf"\b{s}\b", flat):
            status = s
            break

    return {"project": name, "max_payout_usd": max_payout, "status": status}


def enrich_one(item: dict) -> dict:
    """Fetch SSR HTML for one program, parse details, cache on disk."""
    DETAIL_CACHE.mkdir(parents=True, exist_ok=True)
    cached = DETAIL_CACHE / f"{item['uuid']}.json"
    if cached.exists() and time.time() - cached.stat().st_mtime < CACHE_TTL:
        try:
            data = json.loads(cached.read_text(encoding="utf-8"))
            merged = {**item, **data}
            if not merged.get("project"):
                merged["project"] = f"cantina-{item['type']}-{item['uuid'][:8]}"
            return merged
        except Exception:
            pass
    try:
        r = requests.get(item["url"], headers=HEADERS, timeout=30)
        if r.status_code != 200:
            return {**item, "project": f"cantina-{item['type']}-{item['uuid'][:8]}"}
        detail = _parse_detail(r.text)
        if not detail.get("project"):
            detail["project"] = f"cantina-{item['type']}-{item['uuid'][:8]}"
        cached.write_text(json.dumps(detail), encoding="utf-8")
        return {**item, **detail}
    except Exception:
        return {**item, "project": f"cantina-{item['type']}-{item['uuid'][:8]}"}


def _parallel_enrich(items: list[dict], workers: int = 8) -> list[dict]:
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(enrich_one, items))


def list_new(programs: list[dict], days: int = 7, enrich: bool = True) -> list[dict]:
    """Active programs. Cantina sitemap lastmod is a single global timestamp
    (not per-program), so we fall back to enrich + status=Live filter."""
    cutoff = time.time() - days * 86400
    fresh = []
    for p in programs:
        ts = 0
        if p.get("lastmod"):
            try:
                ts = time.mktime(time.strptime(p["lastmod"][:10], "%Y-%m-%d"))
            except Exception:
                ts = 0
        if ts and ts > cutoff:
            fresh.append(p)
    if not fresh:
        fresh = programs
    if enrich:
        fresh = _parallel_enrich(fresh)
        fresh = [x for x in fresh if (x.get("status") or "Live") != "Ended"]
    return fresh


def find_by_protocol(programs: list[dict], name: str) -> list[dict]:
    """Full-index search by name substring. Enriches every program (slow first run, cached after)."""
    n = name.lower()
    enriched = _parallel_enrich(programs)
    return [e for e in enriched if n in (e.get("project") or "").lower()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol", help="Project name substring (full enrich, slow)")
    ap.add_argument("--list-new", action="store_true",
                    help="List programs with lastmod within last 7 days")
    ap.add_argument("--enrich", action="store_true",
                    help="Force enrich every program (slow, ~100 HTTP requests)")
    ap.add_argument("--output")
    args = ap.parse_args()

    programs = load_index()
    if not programs:
        print(json.dumps({"error": "could not load Cantina sitemap"}))
        sys.exit(1)

    if args.protocol:
        result = {"matches": find_by_protocol(programs, args.protocol)}
    elif args.list_new:
        result = {"new_programs": list_new(programs)}
    elif args.enrich:
        result = {"programs": _parallel_enrich(programs)}
    else:
        result = {
            "total_programs": len(programs),
            "by_type": {
                "bounty": sum(1 for p in programs if p["type"] == "bounty"),
                "contest": sum(1 for p in programs if p["type"] == "contest"),
            },
            "sample": programs[:10],
        }

    out = json.dumps(result, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
