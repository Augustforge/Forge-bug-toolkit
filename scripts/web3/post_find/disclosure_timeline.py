#!/usr/bin/env python3
"""
disclosure_timeline.py — Generate disclosure timeline for a finding.

Outputs calendar of milestones from submission to public disclosure.
"""

import argparse
import json
from datetime import date, timedelta
from pathlib import Path


def generate_timeline(severity: str, submission_date: date = None) -> dict:
    if not submission_date:
        submission_date = date.today()

    timeline = {
        "submission": str(submission_date),
        "expected_ack": str(submission_date + timedelta(days=2)),
        "expected_triage": str(submission_date + timedelta(days=7 if severity in ("High", "Critical") else 14)),
        "expected_fix": str(submission_date + timedelta(days=30 if severity == "Critical" else 60)),
        "follow_up_1": str(submission_date + timedelta(days=14)),
        "follow_up_2": str(submission_date + timedelta(days=30)),
        "public_disclosure_window_opens": str(submission_date + timedelta(days=90)),
        "severity": severity,
    }
    return timeline


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--severity", default="Medium", choices=["Critical", "High", "Medium", "Low", "Informational"])
    p.add_argument("--submission-date", help="YYYY-MM-DD (default today)")
    p.add_argument("--output", default=".")
    args = p.parse_args()

    sub_date = date.fromisoformat(args.submission_date) if args.submission_date else date.today()
    tl = generate_timeline(args.severity, sub_date)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "disclosure_timeline.json").write_text(json.dumps(tl, indent=2), encoding="utf-8")

    print(f"=== Disclosure Timeline (severity={args.severity}) ===")
    for k, v in tl.items():
        print(f"  {k:35s}: {v}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
