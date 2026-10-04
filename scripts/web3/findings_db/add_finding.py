#!/usr/bin/env python3
"""
add_finding.py — Submit new finding to findings_db.

Required pre-review fields:
  --target, --severity, --class, --text (or --text-file)

Optional:
  --kb-id (bridge to existing KB), --threat-models (comma-separated), --target-kind

After add — automatically invokes peer_review.py (if --auto-review).

Usage:
  python3 add_finding.py --target uniswap-v4 --severity high \\
      --class oracle_manipulation \\
      --text "TWAP can be manipulated via single-block sandwich..." \\
      --threat-models "" --auto-review

  python3 add_finding.py --kb-id kb_abc123 --severity critical \\
      --class tss_validator_extraction --text-file ./writeup.md \\
      --threat-models tss_validator_extraction
"""
import argparse
import json
import secrets
import sys
import time
from pathlib import Path

DB_DIR = Path.home() / ".bbt" / "kb" / "findings_db"
DB_DIR.mkdir(parents=True, exist_ok=True)
FINDINGS_FILE = DB_DIR / "findings.jsonl"
KB_FILE = Path.home() / ".bbt" / "kb" / "findings.jsonl"


def new_finding_id() -> str:
    return f"fd_{secrets.token_hex(4)}"


def load_kb_entry(kb_id: str) -> dict | None:
    if not KB_FILE.exists():
        return None
    for line in KB_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
            if e.get("kb_id") == kb_id:
                return e
        except Exception:
            continue
    return None


def build_entry(args) -> dict:
    entry = {
        "finding_id": new_finding_id(),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "kb_id": args.kb_id,
        "target": args.target or "",
        "target_kind": args.target_kind or "",
        "severity_claimed": args.severity,
        "severity_after_review": None,
        "class": args.cls,
        "threat_models": [t.strip() for t in (args.threat_models or "").split(",") if t.strip()],
        "pre_review_text": "",
        "peer_review": [],
        "consensus": None,
        "crm_id": None,
        "crm_status": None,
        "bounty_amount_usd": None,
        "reputation_impact": None,
        "related_findings": [],
        "disputes": [],
    }

    if args.kb_id:
        kb = load_kb_entry(args.kb_id)
        if kb:
            entry["target"] = entry["target"] or kb.get("target_kind", "") or kb.get("session", "").split("/")[-1]
            entry["target_kind"] = entry["target_kind"] or kb.get("target_kind", "")
            if not entry["class"]:
                entry["class"] = kb.get("vulnerability", "unknown")
            print(f"[info] bridged from KB entry {args.kb_id}")
        else:
            print(f"[warn] KB entry {args.kb_id} not found", file=sys.stderr)

    if args.text_file:
        entry["pre_review_text"] = Path(args.text_file).read_text(encoding="utf-8")
    elif args.text:
        entry["pre_review_text"] = args.text
    else:
        print("[err] --text or --text-file required", file=sys.stderr)
        sys.exit(1)

    if not entry["target"]:
        print("[err] --target required (or --kb-id with valid bridge)", file=sys.stderr)
        sys.exit(1)
    if not entry["class"]:
        print("[err] --class required", file=sys.stderr)
        sys.exit(1)

    return entry


def append(entry: dict):
    with FINDINGS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", help="Protocol/repo name")
    ap.add_argument("--target-kind", help="defi-amm / defi-lending / bridge / mpc-custody / ...")
    ap.add_argument("--severity", required=True, choices=["low", "medium", "high", "critical"])
    ap.add_argument("--class", dest="cls", required=True, help="Root-cause class")
    ap.add_argument("--threat-models", help="Comma-separated threat_model IDs")
    ap.add_argument("--text", help="Pre-review writeup text")
    ap.add_argument("--text-file", help="Path to file containing writeup")
    ap.add_argument("--kb-id", help="Bridge from existing KB entry")
    ap.add_argument("--auto-review", action="store_true", help="Auto-invoke peer_review.py after add")
    args = ap.parse_args()

    entry = build_entry(args)
    append(entry)
    print(f"[ok] added {entry['finding_id']} → {FINDINGS_FILE}")

    if args.auto_review:
        import subprocess
        review_py = Path(__file__).parent / "peer_review.py"
        if review_py.exists():
            print(f"\n[info] auto-invoking peer_review...")
            subprocess.call(["python3", str(review_py), "--finding-id", entry["finding_id"]])
        else:
            print(f"[warn] peer_review.py not found at {review_py}", file=sys.stderr)


if __name__ == "__main__":
    main()
