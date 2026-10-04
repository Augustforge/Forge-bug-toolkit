"""Shared utilities for monitor scripts."""

import json
import re
import time
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

ROOT = Path(__file__).resolve().parent
SOURCES = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
KEYWORDS = json.loads((ROOT / "keywords.json").read_text(encoding="utf-8"))
CACHE_DIR = Path.home() / ".bbt" / "cache" / "monitors"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def classify(text: str) -> tuple[str, list[str]]:
    """Return (severity, matched_keywords)."""
    text_l = text.lower()
    if any(re.search(rf"\b{re.escape(kw)}\b", text_l) for kw in KEYWORDS["exclude_noise"]):
        return ("noise", [])
    matched_high = [kw for kw in KEYWORDS["high_severity"]
                    if re.search(rf"\b{re.escape(kw)}\b", text_l)]
    matched_med = [kw for kw in KEYWORDS["medium_severity"]
                   if re.search(rf"\b{re.escape(kw)}\b", text_l)]
    matched_money = [kw for kw in KEYWORDS["monetary_indicators"]
                     if re.search(kw, text)]
    if matched_high or matched_money:
        return ("high", matched_high + matched_money)
    if matched_med:
        return ("medium", matched_med)
    return ("low", [])


def fetch(url: str, timeout: int = 20, retries: int = 3) -> requests.Response | None:
    """HTTP GET with exponential backoff."""
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=timeout, headers={"User-Agent": "BBT/1.0"})
            if r.status_code == 200:
                return r
            if r.status_code in (429, 503):
                time.sleep(2 ** attempt)
                continue
            return r
        except requests.exceptions.RequestException:
            time.sleep(2 ** attempt)
    return None


def parse_rss(content: bytes) -> list[dict]:
    """Parse RSS/Atom into uniform dicts."""
    try:
        root = ET.fromstring(content)
    except Exception:
        return []
    entries = []
    items = (root.findall(".//item")
             or root.findall(".//{http://www.w3.org/2005/Atom}entry"))
    for item in items[:50]:
        title = _text(item, "title")
        link = _text(item, "link") or _attr(item, "{http://www.w3.org/2005/Atom}link", "href")
        date = _text(item, "pubDate") or _text(item, "{http://www.w3.org/2005/Atom}updated")
        desc = _text(item, "description") or _text(item, "{http://www.w3.org/2005/Atom}summary")
        if not title or not link:
            continue
        entries.append({
            "title": title.strip(),
            "link": link.strip(),
            "date": date.strip() if date else "",
            "description": (desc or "").strip()[:500],
        })
    return entries


def _text(item, tag):
    el = item.find(tag)
    return el.text if el is not None and el.text else ""


def _attr(item, tag, attr):
    el = item.find(tag)
    return el.get(attr, "") if el is not None else ""


def load_seen(name: str) -> set[str]:
    """Load deduplication set from cache."""
    f = CACHE_DIR / f"{name}_seen.json"
    if not f.exists():
        return set()
    try:
        return set(json.loads(f.read_text()))
    except Exception:
        return set()


def save_seen(name: str, seen: set[str], max_entries: int = 5000):
    f = CACHE_DIR / f"{name}_seen.json"
    keep = list(seen)[-max_entries:]
    f.write_text(json.dumps(keep))


def hash_id(s: str) -> str:
    """Simple stable id."""
    import hashlib
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]
