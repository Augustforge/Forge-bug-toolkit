#!/usr/bin/env python3
"""
TVL surge monitor via DeFiLlama.

Daily snapshot of all protocols. Compares with previous snapshots to find:
- 24h surge >20%
- 7d surge >100%
- 30d surge >500%

For each surge — cross-checks Immunefi scope to find "TVL growing + no
program yet" — the golden pattern (pre-program coordinated disclosure).
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import SOURCES, fetch

CACHE = Path.home() / ".bbt" / "cache" / "monitors" / "tvl"
CACHE.mkdir(parents=True, exist_ok=True)


def snapshot_today():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    file = CACHE / f"snapshot_{today}.json"
    if file.exists():
        return json.loads(file.read_text())
    r = fetch(SOURCES["defillama_protocols"])
    if not r or r.status_code != 200:
        return []
    data = r.json()
    file.write_text(json.dumps(data))
    return data


def load_snapshot(days_ago: int) -> dict:
    target = (datetime.now(timezone.utc) - __import__("datetime").timedelta(days=days_ago)).strftime("%Y-%m-%d")
    file = CACHE / f"snapshot_{target}.json"
    if not file.exists():
        return {}
    try:
        data = json.loads(file.read_text())
    except Exception:
        return {}
    return {p["slug"]: p for p in data if p.get("slug")}


def compute_surges(today: list[dict], window_days: int, threshold_pct: float) -> list[dict]:
    prev = load_snapshot(window_days)
    if not prev:
        return []
    surges = []
    for p in today:
        slug = p.get("slug")
        if not slug or slug not in prev:
            continue
        tvl_now = p.get("tvl") or 0
        tvl_prev = prev[slug].get("tvl") or 0
        if tvl_prev <= 1000:  # ignore micro-protocols
            continue
        growth = (tvl_now - tvl_prev) / tvl_prev * 100
        if growth >= threshold_pct:
            surges.append({
                "name": p.get("name"),
                "slug": slug,
                "category": p.get("category"),
                "chain": p.get("chain"),
                "tvl_now": round(tvl_now, 0),
                "tvl_prev": round(tvl_prev, 0),
                "growth_percent": round(growth, 1),
                "window_days": window_days,
                "audits": p.get("audits", "0"),
                "audit_links": p.get("audit_links", []),
                "url": p.get("url"),
            })
    return surges


def cross_check_immunefi(surges: list[dict]) -> list[dict]:
    """Mark surges where protocol has NO Immunefi program yet — golden cases."""
    immunefi_file = Path(__file__).resolve().parents[1] / "_data" / "immunefi_projects.json"
    immunefi_names = set()
    if immunefi_file.exists():
        try:
            for p in json.loads(immunefi_file.read_text()):
                if p.get("project"):
                    immunefi_names.add(p["project"].lower())
        except Exception:
            pass

    for s in surges:
        s["in_immunefi"] = s["name"].lower() in immunefi_names if s.get("name") else False
        s["golden_case"] = (
            not s["in_immunefi"]
            and (s.get("audits") or "0") in ("0", 0, "1", 1)
            and s["tvl_now"] >= 1_000_000
        )
    return surges


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    print("[*] Taking today's TVL snapshot...")
    today = snapshot_today()
    print(f"    {len(today)} protocols")

    surges_24h = compute_surges(today, 1, 20)
    surges_7d = compute_surges(today, 7, 100)
    surges_30d = compute_surges(today, 30, 500)

    all_surges = surges_24h + surges_7d + surges_30d
    all_surges = cross_check_immunefi(all_surges)
    golden = [s for s in all_surges if s.get("golden_case")]

    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "snapshots_available": sorted(f.name for f in CACHE.glob("snapshot_*.json")),
        "surges_24h": surges_24h,
        "surges_7d": surges_7d,
        "surges_30d": surges_30d,
        "golden_cases": golden,
    }
    (out / "tvl.json").write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"[+] 24h surges: {len(surges_24h)} | 7d: {len(surges_7d)} | 30d: {len(surges_30d)}")
    print(f"[!] Golden cases (no Immunefi program, no audit, TVL ≥ $1M): {len(golden)}")
    if golden:
        for g in golden[:5]:
            print(f"    🌟 {g['name']} ({g['category']}) — TVL ${g['tvl_now']:,.0f}, +{g['growth_percent']}% ({g['window_days']}d)")


if __name__ == "__main__":
    main()
