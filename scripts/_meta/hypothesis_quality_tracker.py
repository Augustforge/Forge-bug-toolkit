#!/usr/bin/env python3
"""
hypothesis_quality_tracker.py — track novel:known ratio across hunts.

Scans `sessions/*/hypothesis/*.json` + `sessions/*/deep/specialized/*.json`,
extracts classification field, computes ratio.

Target: >= 0.5 (50%+ findings = novel). If < 0.3 → "pattern-matching warning".
"""
import argparse, json, sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path


def collect_findings(sessions_dir: Path, since_days: int) -> list[dict]:
    cutoff = datetime.now() - timedelta(days=since_days)
    out = []
    for json_path in sessions_dir.rglob("*.json"):
        try:
            mtime = datetime.fromtimestamp(json_path.stat().st_mtime)
            if mtime < cutoff:
                continue
            data = json.loads(json_path.read_text(encoding="utf-8"))
            items = []
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get("findings", []) if "findings" in data else [data]
            for item in items:
                if isinstance(item, dict) and "classification" in item:
                    item.setdefault("source", str(json_path))
                    out.append(item)
        except Exception:
            continue
    return out


def main():
    ap = argparse.ArgumentParser(description="Track [novel] vs [known] ratio")
    ap.add_argument("--sessions-dir", default="sessions", help="Sessions root")
    ap.add_argument("--since-days", type=int, default=30)
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    findings = collect_findings(Path(args.sessions_dir), args.since_days)
    if not findings:
        print(f"[!] No findings found in {args.sessions_dir} since {args.since_days}d")
        sys.exit(0)

    by_class = defaultdict(lambda: {"novel": 0, "known": 0})
    total_novel = 0
    total_known = 0
    per_script = defaultdict(lambda: {"novel": 0, "known": 0})

    for f in findings:
        c = f.get("classification", "")
        cls = f.get("class", "?")
        script = Path(f.get("source", "?")).name
        if c == "novel_instance":
            total_novel += 1
            by_class[cls]["novel"] += 1
            per_script[script]["novel"] += 1
        elif c == "known_class":
            total_known += 1
            by_class[cls]["known"] += 1
            per_script[script]["known"] += 1

    total = total_novel + total_known
    ratio = (total_novel / total) if total else 0

    print(f"[+] Findings last {args.since_days} days: {total}")
    print(f"    Novel instances: {total_novel}")
    print(f"    Known classes:   {total_known}")
    print(f"    Ratio (novel/total): {ratio:.2%}")

    if ratio < 0.3:
        print(f"\n[!] WARNING: ratio < 30%. You're pattern-matching, not hunting properly.")
        print(f"    Mindset shift: every exploit = INSTANCE of a broader class. Generalize.")
    elif ratio < 0.5:
        print(f"\n[*] Below target (50%). Push for novel instances priority.")
    else:
        print(f"\n[+] Target met (>= 50%). Good hunting mindset.")

    print(f"\nTop classes by novel count:")
    sorted_classes = sorted(by_class.items(), key=lambda x: -x[1]["novel"])
    for cls, counts in sorted_classes[:10]:
        print(f"  {cls:35} novel={counts['novel']:3} known={counts['known']:3}")

    print(f"\nMost productive scripts (by novel count):")
    sorted_scripts = sorted(per_script.items(), key=lambda x: -x[1]["novel"])
    for script, counts in sorted_scripts[:10]:
        print(f"  {script:40} novel={counts['novel']:3} known={counts['known']:3}")

    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        report = {
            "period_days": args.since_days,
            "total": total,
            "novel": total_novel,
            "known": total_known,
            "ratio": ratio,
            "by_class": dict(by_class),
            "per_script": dict(per_script),
        }
        (out / "quality_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
