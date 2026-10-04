#!/usr/bin/env python3
"""
Aggregate signals from all monitors, dedupe, score, and rank.

Reads:  twitter.json, github.json, tvl.json, telegram.json
Writes: aggregated.json — top signals across all sources
"""

import argparse
import json
import sys
import time
from pathlib import Path

SEVERITY_WEIGHT = {"high": 3, "medium": 2, "low": 1, "noise": 0}
SOURCE_WEIGHT = {"ownership": 3, "tvl": 3, "twitter": 2, "github": 2, "telegram": 1}


def read_or_empty(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def normalize_twitter(data: dict) -> list[dict]:
    return [
        {
            "source": "twitter", "subsource": e.get("account"),
            "title": e.get("title", "")[:200],
            "link": e.get("link"), "date": e.get("date"),
            "severity": e.get("severity", "low"),
            "keywords": e.get("matched_keywords", []),
            "description": e.get("description", ""),
        }
        for e in data.get("entries", [])
    ]


def normalize_telegram(data: dict) -> list[dict]:
    return [
        {
            "source": "telegram", "subsource": e.get("channel"),
            "title": e.get("title", "")[:200],
            "link": e.get("link"), "date": e.get("date"),
            "severity": e.get("severity", "low"),
            "keywords": e.get("matched_keywords", []),
            "description": e.get("description", ""),
        }
        for e in data.get("entries", [])
    ]


def normalize_github(data: dict) -> list[dict]:
    out = []
    for s in data.get("stars_surges", []):
        out.append({
            "source": "github", "subsource": "stars-surge",
            "title": f"{s['name']} stars surge +{s['growth_percent']}%",
            "link": s.get("url"),
            "date": "",
            "severity": "medium",
            "keywords": ["stars-surge"],
            "description": f"{s['stars_before']} → {s['stars_after']} stars",
        })
    for c in data.get("suspicious_commits", []):
        out.append({
            "source": "github", "subsource": "suspicious-commit",
            "title": f"{c['repo']}: {c['message'][:80]}",
            "link": c.get("url"), "date": "",
            "severity": "high" if "critical" in " ".join(c.get("matched", [])).lower() else "medium",
            "keywords": c.get("matched", []),
            "description": c.get("message", ""),
        })
    for t in data.get("trending_solidity", [])[:10]:
        out.append({
            "source": "github", "subsource": "trending",
            "title": f"Trending: {t['name']} ({t['stars']}⭐)",
            "link": t.get("url"), "date": t.get("created", ""),
            "severity": "low", "keywords": ["trending"],
            "description": t.get("description", ""),
        })
    return out


def normalize_tvl(data: dict) -> list[dict]:
    out = []
    for s in data.get("golden_cases", []):
        out.append({
            "source": "tvl", "subsource": "golden-case",
            "title": f"🌟 GOLDEN: {s['name']} TVL ${s['tvl_now']:,.0f} (+{s['growth_percent']}%, no Immunefi program)",
            "link": s.get("url"), "date": "",
            "severity": "high", "keywords": ["golden-case", "no-program"],
            "description": f"Category: {s['category']}, audits: {s.get('audits', '0')}",
        })
    for s in data.get("surges_24h", [])[:10]:
        out.append({
            "source": "tvl", "subsource": "surge-24h",
            "title": f"{s['name']} TVL +{s['growth_percent']}% (24h)",
            "link": s.get("url"), "date": "",
            "severity": "medium", "keywords": ["tvl-surge"],
            "description": f"${s['tvl_now']:,.0f}, was ${s['tvl_prev']:,.0f}",
        })
    return out


def normalize_ownership(data: dict) -> list[dict]:
    return [
        {
            "source": "ownership", "subsource": e.get("protocol"),
            "title": e.get("title", "")[:200],
            "link": e.get("link"), "date": e.get("date"),
            "severity": e.get("severity", "high"),
            "keywords": e.get("matched_keywords", []),
            "description": e.get("description", ""),
        }
        for e in data.get("entries", [])
    ]


def score(entry: dict, all_entries: list[dict]) -> float:
    sw = SOURCE_WEIGHT.get(entry["source"], 1)
    sev = SEVERITY_WEIGHT.get(entry["severity"], 0)
    # Cross-source bonus: same target name in 2+ sources
    name_lower = entry["title"].lower()
    cross_count = sum(
        1 for other in all_entries
        if other is not entry and any(
            kw in other["title"].lower()
            for kw in name_lower.split()[:3] if len(kw) > 4
        )
    )
    cross_bonus = 1 + min(cross_count, 3) * 0.3
    return sw * sev * cross_bonus


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Directory with monitor JSONs")
    ap.add_argument("--output", required=True)
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()

    inp = Path(args.input)
    all_entries = []
    all_entries.extend(normalize_twitter(read_or_empty(inp / "twitter.json")))
    all_entries.extend(normalize_telegram(read_or_empty(inp / "telegram.json")))
    all_entries.extend(normalize_github(read_or_empty(inp / "github.json")))
    all_entries.extend(normalize_tvl(read_or_empty(inp / "tvl.json")))
    all_entries.extend(normalize_ownership(read_or_empty(inp / "ownership.json")))

    for e in all_entries:
        e["score"] = round(score(e, all_entries), 2)

    all_entries.sort(key=lambda x: x["score"], reverse=True)
    top = all_entries[:args.top]

    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_signals": len(all_entries),
        "by_source": {
            src: sum(1 for e in all_entries if e["source"] == src)
            for src in ("ownership", "twitter", "telegram", "github", "tvl")
        },
        "by_severity": {
            sev: sum(1 for e in all_entries if e["severity"] == sev)
            for sev in ("high", "medium", "low")
        },
        "top": top,
    }
    Path(args.output).write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"[+] Total: {len(all_entries)} | Top: {len(top)}")
    print(f"[+] By source: {output['by_source']}")
    print(f"[+] By severity: {output['by_severity']}")


if __name__ == "__main__":
    main()
