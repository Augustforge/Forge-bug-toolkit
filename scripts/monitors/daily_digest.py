#!/usr/bin/env python3
"""
Daily digest — runs all monitors, aggregates, sends formatted summary
to Telegram bot. Designed for cron at 9:00 AM daily.

Workflow:
  1. Run twitter_monitor + telegram_monitor + github_monitor + tvl_monitor
  2. Run aggregator
  3. Format daily digest (top 5 by category)
  4. Send to Telegram

Usage:
  python3 daily_digest.py
  python3 daily_digest.py --output sessions/_monitors/
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def run(cmd: list[str]) -> bool:
    print(f"[*] Running: {' '.join(cmd)}")
    try:
        r = subprocess.run(cmd, timeout=600, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  [!] exit {r.returncode}: {r.stderr[:200]}")
        return r.returncode == 0
    except Exception as e:
        print(f"  [!] {e}")
        return False


def format_digest(agg_path: Path) -> str:
    if not agg_path.exists():
        return "*BBT Daily Digest*\n\n(no signals available)"
    data = json.loads(agg_path.read_text())
    today = time.strftime("%Y-%m-%d")
    lines = [f"*BBT Daily Digest — {today}*", ""]
    lines.append(f"📊 Total signals: {data.get('total_signals', 0)}")
    by_sev = data.get("by_severity", {})
    lines.append(f"🔴 High: {by_sev.get('high', 0)} | 🟡 Med: {by_sev.get('medium', 0)} | 🟢 Low: {by_sev.get('low', 0)}")
    lines.append("")

    top = data.get("top", [])

    ownership = [e for e in top if e.get("source") == "ownership"][:5]
    if ownership:
        lines.append("🔑 *Ownership/admin changes on custody contracts:*")
        for e in ownership:
            lines.append(f"  {e['title']}")
        lines.append("")

    high = [e for e in top if e.get("severity") == "high"][:3]
    if high:
        lines.append("🔥 *Top 3 High-severity:*")
        for e in high:
            lines.append(f"  {e['title']}")
            lines.append(f"  {e.get('link', '')}")
        lines.append("")

    tvl_golden = [e for e in top if e.get("subsource") == "golden-case"][:5]
    if tvl_golden:
        lines.append("🌟 *Golden TVL cases (no Immunefi yet):*")
        for e in tvl_golden:
            lines.append(f"  {e['title']}")
        lines.append("")

    twitter = [e for e in top if e.get("source") == "twitter"][:5]
    if twitter:
        lines.append("🐦 *Top tweets:*")
        for e in twitter:
            lines.append(f"  @{e.get('subsource')}: {e['title'][:120]}")
        lines.append("")

    github = [e for e in top if e.get("source") == "github"][:5]
    if github:
        lines.append("💻 *GitHub signals:*")
        for e in github:
            lines.append(f"  {e['title']}")
        lines.append("")

    # Mempool watcher stats (H1 integration)
    mempool_stats = read_mempool_audit()
    if mempool_stats["matches_24h"]:
        lines.append(f"🚨 *Mempool watcher (24h):* {mempool_stats['matches_24h']} matches")
        for pat, n in mempool_stats["by_pattern"].items():
            lines.append(f"  · {pat}: {n}")
        lines.append("")

    # Reputation snapshot (H3 integration)
    rep = read_reputation()
    if rep:
        lines.append("📈 *Hunt reputation (top 5 classes):*")
        for cls, score in rep[:5]:
            lines.append(f"  · {cls}: {score:+d}")
        lines.append("")

    return "\n".join(lines)


def read_mempool_audit() -> dict:
    """Read ~/.bbt/audit.log entries from last 24h, group by pattern."""
    from collections import Counter
    audit = Path.home() / ".bbt" / "audit.log"
    if not audit.exists():
        return {"matches_24h": 0, "by_pattern": {}}
    cutoff = time.time() - 86400
    by_pattern = Counter()
    try:
        for line in audit.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                e = json.loads(line)
                ts = e.get("timestamp", "")
                if ts and ts < time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(cutoff)):
                    continue
                if e.get("pattern"):
                    by_pattern[e["pattern"]] += 1
            except Exception:
                continue
    except Exception:
        pass
    return {"matches_24h": sum(by_pattern.values()), "by_pattern": dict(by_pattern.most_common(5))}


def read_reputation() -> list[tuple[str, int]]:
    """Read findings_db reputation.json, return top classes."""
    rep_file = Path.home() / ".bbt" / "kb" / "findings_db" / "reputation.json"
    if not rep_file.exists():
        return []
    try:
        data = json.loads(rep_file.read_text(encoding="utf-8"))
        return sorted(
            ((cls, stats.get("score", 0)) for cls, stats in data.items()),
            key=lambda x: -x[1],
        )
    except Exception:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="sessions/_monitors")
    ap.add_argument("--skip-fetch", action="store_true",
                    help="Use existing JSONs (skip running monitors)")
    args = ap.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    if not args.skip_fetch:
        run([sys.executable, str(SCRIPT_DIR / "twitter_monitor.py"), "--output", str(out)])
        run([sys.executable, str(SCRIPT_DIR / "telegram_monitor.py"), "--output", str(out)])
        run([sys.executable, str(SCRIPT_DIR / "github_monitor.py"), "--output", str(out)])
        run([sys.executable, str(SCRIPT_DIR / "tvl_monitor.py"), "--output", str(out)])
        run([sys.executable, str(SCRIPT_DIR / "ownership_transfer_monitor.py"), "--output", str(out)])

    run([sys.executable, str(SCRIPT_DIR / "aggregator.py"),
         "--input", str(out), "--output", str(out / "aggregated.json")])

    digest = format_digest(out / "aggregated.json")
    digest_file = out / f"digest_{time.strftime('%Y-%m-%d')}.md"
    digest_file.write_text(digest, encoding="utf-8")
    print(f"[+] Digest saved: {digest_file}")

    sent = run([sys.executable, str(SCRIPT_DIR / "notify.py"),
                "--message", digest])
    if sent:
        print("[+] Digest sent to Telegram")
    else:
        print("[i] Telegram not configured — digest only saved locally")


if __name__ == "__main__":
    main()
