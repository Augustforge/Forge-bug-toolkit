#!/usr/bin/env python3
"""
export.py — Export sanitized findings for sharing with trusted peers.

Sanitization:
- Strip raw pre_review_text (may contain PII or unfinished PoC)
- Strip CRM IDs (internal references)
- Keep: finding_id, class, threat_models, consensus, severity_claimed/after_review, paid status

Output: JSON file. Optionally PGP-sign if `--sign --gpg-key <id>` provided
(requires gpg binary in PATH).

Usage:
  python3 export.py --output ./shared_findings.json
  python3 export.py --class oracle_manipulation --paid-only --output shared.json
  python3 export.py --sign --gpg-key 0xABCD --output shared.json
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

DB_DIR = Path.home() / ".bbt" / "kb" / "findings_db"
FINDINGS_FILE = DB_DIR / "findings.jsonl"


def load_findings() -> list[dict]:
    if not FINDINGS_FILE.exists():
        return []
    return [json.loads(l) for l in FINDINGS_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]


def sanitize(entry: dict) -> dict:
    return {
        "finding_id": entry.get("finding_id"),
        "timestamp": entry.get("timestamp"),
        "target": entry.get("target"),
        "target_kind": entry.get("target_kind"),
        "class": entry.get("class"),
        "threat_models": entry.get("threat_models", []),
        "severity_claimed": entry.get("severity_claimed"),
        "severity_after_review": entry.get("severity_after_review"),
        "consensus": entry.get("consensus"),
        "crm_status": entry.get("crm_status"),
        "bounty_amount_usd": entry.get("bounty_amount_usd"),
        "reputation_impact": entry.get("reputation_impact"),
        "peer_review_summary": [
            {"reviewer": r.get("reviewer"), "verdict": r.get("verdict"),
             "confidence": r.get("confidence")}
            for r in entry.get("peer_review", [])
        ],
    }


def filter_findings(findings: list[dict], args) -> list[dict]:
    out = findings
    if args.cls:
        out = [f for f in out if f.get("class") == args.cls]
    if args.paid_only:
        out = [f for f in out if f.get("crm_status") == "paid"]
    if args.min_severity:
        sev_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        min_sev = sev_order.get(args.min_severity, 0)
        out = [f for f in out if sev_order.get(f.get("severity_claimed", "low"), 0) >= min_sev]
    return out


def pgp_sign(filepath: Path, key_id: str) -> Path:
    sig = filepath.with_suffix(filepath.suffix + ".asc")
    try:
        result = subprocess.run(
            ["gpg", "--armor", "--detach-sign", "--local-user", key_id, "--output", str(sig), str(filepath)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            print(f"[err] gpg sign failed: {result.stderr}", file=sys.stderr)
            return filepath
        return sig
    except FileNotFoundError:
        print("[warn] gpg not installed — skipping signature", file=sys.stderr)
        return filepath


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True, help="Output JSON path")
    ap.add_argument("--class", dest="cls", help="Filter by class")
    ap.add_argument("--paid-only", action="store_true")
    ap.add_argument("--min-severity", choices=["low", "medium", "high", "critical"])
    ap.add_argument("--sign", action="store_true", help="PGP-sign output")
    ap.add_argument("--gpg-key", help="GPG key ID (required with --sign)")
    args = ap.parse_args()

    findings = load_findings()
    findings = filter_findings(findings, args)
    sanitized = [sanitize(f) for f in findings]

    bundle = {
        "version": "1",
        "count": len(sanitized),
        "findings": sanitized,
    }

    out = Path(args.output)
    out.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[ok] exported {len(sanitized)} findings → {out}")

    if args.sign:
        if not args.gpg_key:
            print("[err] --sign requires --gpg-key", file=sys.stderr)
            sys.exit(1)
        sig = pgp_sign(out, args.gpg_key)
        if sig != out:
            print(f"[ok] signature: {sig}")


if __name__ == "__main__":
    main()
