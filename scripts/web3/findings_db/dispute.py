#!/usr/bin/env python3
"""
dispute.py — Record dispute when CRM status disagrees with hunter judgment.

E.g., CRM says "rejected" but hunter believes finding is valid:
  python3 dispute.py --finding-id fd_abc12345 --reason "Triager misread severity, see PoC..."

After resolution (when program responds or hunter abandons):
  python3 dispute.py --finding-id fd_abc12345 --resolve won
  python3 dispute.py --finding-id fd_abc12345 --resolve lost

Resolution feeds back into reputation.py (+1 won, -1 lost).
"""
import argparse
import json
import sys
import time
from pathlib import Path

DB_DIR = Path.home() / ".bbt" / "kb" / "findings_db"
FINDINGS_FILE = DB_DIR / "findings.jsonl"


def load_finding(finding_id: str) -> tuple[dict | None, int]:
    if not FINDINGS_FILE.exists():
        return None, -1
    lines = FINDINGS_FILE.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            e = json.loads(line)
            if e.get("finding_id") == finding_id:
                return e, i
        except Exception:
            continue
    return None, -1


def save_finding(entry: dict, idx: int):
    lines = FINDINGS_FILE.read_text(encoding="utf-8").splitlines()
    lines[idx] = json.dumps(entry, ensure_ascii=False)
    FINDINGS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--finding-id", required=True)
    ap.add_argument("--reason", help="Initial dispute reason (when opening)")
    ap.add_argument("--resolve", choices=["won", "lost", "abandoned"],
                    help="Resolve the most recent open dispute")
    args = ap.parse_args()

    entry, idx = load_finding(args.finding_id)
    if not entry:
        print(f"[err] finding {args.finding_id} not found", file=sys.stderr)
        sys.exit(1)

    disputes = entry.setdefault("disputes", [])

    if args.resolve:
        open_dispute = next((d for d in reversed(disputes) if not d.get("resolution")), None)
        if not open_dispute:
            print(f"[err] no open dispute on {args.finding_id}", file=sys.stderr)
            sys.exit(1)
        open_dispute["resolution"] = args.resolve
        open_dispute["resolved_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        save_finding(entry, idx)
        print(f"[ok] dispute on {args.finding_id} resolved: {args.resolve}")
        print(f"[hint] run `python3 reputation.py --update` for score recompute")
        return

    if not args.reason:
        ap.error("--reason required when opening dispute (or use --resolve)")

    disputes.append({
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "reason": args.reason,
        "resolution": None,
    })
    save_finding(entry, idx)
    print(f"[ok] dispute opened on {args.finding_id}")


if __name__ == "__main__":
    main()
