#!/usr/bin/env python3
"""
reputation.py — Per-class reputation score derived from CRM outcomes.

Per-finding score deltas:
  +10  for paid bounty
  +3   for accepted (no payout / informational)
  -2   for rejected
  -1   for confirmed duplicate
  +0   for draft/triaged/submitted (pending)
  +1   for successful dispute resolution
  -1   for failed dispute

Per-class score = sum of deltas for findings of that class.

Usage:
  python3 reputation.py --update             # recompute scores
  python3 reputation.py --show               # print current scores
  python3 reputation.py --show --class oracle_manipulation
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

DB_DIR = Path.home() / ".bbt" / "kb" / "findings_db"
FINDINGS_FILE = DB_DIR / "findings.jsonl"
REPUTATION_FILE = DB_DIR / "reputation.json"
CRM_FILE = Path.cwd() / "sessions" / "_crm" / "reports.jsonl"

DELTA_BY_STATUS = {
    "paid": 10,
    "accepted": 3,
    "duplicate": -1,
    "rejected": -2,
    "draft": 0,
    "submitted": 0,
    "triaged": 0,
    "no-response": 0,
}


def load_findings() -> list[dict]:
    if not FINDINGS_FILE.exists():
        return []
    return [json.loads(l) for l in FINDINGS_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_crm_outcomes() -> dict[str, dict]:
    """Returns crm_id → crm entry."""
    if not CRM_FILE.exists():
        return {}
    out = {}
    for line in CRM_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
            if e.get("id"):
                out[e["id"]] = e
        except Exception:
            continue
    return out


def compute(findings: list[dict], crm: dict[str, dict]) -> dict:
    by_class = defaultdict(lambda: {"total": 0, "paid": 0, "accepted": 0,
                                    "rejected": 0, "duplicate": 0,
                                    "pending": 0, "score": 0, "bounty_usd": 0.0})
    for f in findings:
        cls = f.get("class", "unknown") or "unknown"
        by_class[cls]["total"] += 1

        status = f.get("crm_status")
        crm_id = f.get("crm_id")
        if (not status or status in ("draft", "submitted", "triaged")) and crm_id:
            crm_entry = crm.get(crm_id)
            if crm_entry:
                status = crm_entry.get("status")
                f["crm_status"] = status

        delta = DELTA_BY_STATUS.get(status, 0)

        for d in f.get("disputes", []):
            res = d.get("resolution")
            if res == "won":
                delta += 1
            elif res == "lost":
                delta -= 1

        f["reputation_impact"] = delta
        by_class[cls]["score"] += delta

        if status == "paid":
            by_class[cls]["paid"] += 1
            by_class[cls]["bounty_usd"] += f.get("bounty_amount_usd", 0) or 0
        elif status == "accepted":
            by_class[cls]["accepted"] += 1
        elif status == "rejected":
            by_class[cls]["rejected"] += 1
        elif status == "duplicate":
            by_class[cls]["duplicate"] += 1
        else:
            by_class[cls]["pending"] += 1

    return {k: dict(v) for k, v in by_class.items()}


def save_findings(findings: list[dict]):
    FINDINGS_FILE.write_text(
        "\n".join(json.dumps(f, ensure_ascii=False) for f in findings) + "\n",
        encoding="utf-8")


def cmd_update():
    findings = load_findings()
    if not findings:
        print("[i] no findings yet")
        return
    crm = load_crm_outcomes()
    print(f"[info] {len(findings)} findings, {len(crm)} CRM entries")
    by_class = compute(findings, crm)
    save_findings(findings)
    REPUTATION_FILE.write_text(json.dumps(by_class, indent=2), encoding="utf-8")
    print(f"[ok] reputation written to {REPUTATION_FILE}")
    print()
    cmd_show(class_filter=None)


def cmd_show(class_filter: str | None = None):
    if not REPUTATION_FILE.exists():
        print("[i] reputation.json not found — run --update first")
        return
    data = json.loads(REPUTATION_FILE.read_text(encoding="utf-8"))
    items = sorted(data.items(), key=lambda x: x[1].get("score", 0), reverse=True)
    print(f"{'Class':<35} {'Total':>6} {'Paid':>5} {'Acc':>4} {'Rej':>4} {'Dup':>4} {'Score':>6} {'Bounty':>10}")
    print("-" * 80)
    for cls, stats in items:
        if class_filter and cls != class_filter:
            continue
        print(f"{cls:<35} {stats['total']:>6} {stats['paid']:>5} {stats['accepted']:>4} "
              f"{stats['rejected']:>4} {stats['duplicate']:>4} {stats['score']:>+6} ${stats['bounty_usd']:>9,.0f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--class", dest="cls", help="Filter by class")
    args = ap.parse_args()

    if args.update:
        cmd_update()
    elif args.show:
        cmd_show(class_filter=args.cls)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
