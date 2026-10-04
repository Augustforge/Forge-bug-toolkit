#!/usr/bin/env python3
"""
Bug bounty CRM — track communications, statuses, deadlines.

Without this, reports get lost within a month. It is not a tool, it is organisation.

Statuses:
- draft         — report written, not sent
- submitted     — sent to the program
- triaged       — program confirmed receipt
- accepted      — accepted as valid
- duplicate     — duplicate
- rejected      — rejected
- paid          — paid out
- no-response   — no response for > 30 days

Storage:
- sessions/_crm/reports.jsonl       — submitted findings lifecycle
- sessions/_crm/abort_log.jsonl     — first-pass abort decisions + reversal tracking
                                      (powers Mandate 0.2 self-calibration)

Usage:
    python3 _crm.py add --target example.com --finding F003 --platform hackerone
    python3 _crm.py update --id R001 --status accepted
    python3 _crm.py list
    python3 _crm.py pending     # awaiting reply
    python3 _crm.py overdue     # > 30 days no response
    python3 _crm.py payout-stats  # per-platform payout velocity/fairness (avg days_to_payout)

    # Abort tracking (Mandate 0.2):
    python3 _crm.py abort --target superform --hours-spent 4.5 --hypotheses-tried 10 \\
                          --reason "all single-vector refuted, no chain found"
    python3 _crm.py abort-reverse --id A001 --findings-after 2 --note "Med/High Morpho+Ethena"
    python3 _crm.py abort-confirm --id A001 --note "target genuinely clean after deep second pass"
    python3 _crm.py abort-stats           # false-abort rate, calibration signal
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

CRM_DIR = Path("sessions/_crm")
CRM_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_FILE = CRM_DIR / "reports.jsonl"
ABORT_FILE = CRM_DIR / "abort_log.jsonl"


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def append(entry: dict):
    with REPORTS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def append_abort(entry: dict):
    with ABORT_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_aborts() -> list[dict]:
    if not ABORT_FILE.exists():
        return []
    return [json.loads(l) for l in ABORT_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]


def read_all() -> list[dict]:
    if not REPORTS_FILE.exists():
        return []
    return [json.loads(l) for l in REPORTS_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]


def latest_state(report_id: str, entries: list[dict]) -> dict:
    """Return the latest state for report_id."""
    matching = [e for e in entries if e.get("report_id") == report_id]
    if not matching:
        return {}
    return matching[-1]


def _status_timestamp(report_id: str, entries: list[dict], status: str) -> str | None:
    """First timestamp when report_id entered the given status (fail-open — None if absent)."""
    for e in entries:
        if e.get("report_id") == report_id and e.get("status") == status:
            return e.get("timestamp")
    return None


def cmd_add(args):
    entries = read_all()
    next_id = f"R{len(set(e.get('report_id') for e in entries if e.get('report_id'))) + 1:03d}"
    entry = {
        "event": "created",
        "timestamp": now(),
        "report_id": next_id,
        "target": args.target,
        "finding_id": args.finding,
        "platform": args.platform,
        "severity": args.severity,
        "estimated_bounty": args.bounty,
        "status": "draft",
    }
    append(entry)
    print(f"[+] Created {next_id} for {args.target}/{args.finding}")


def cmd_update(args):
    entries = read_all()
    state = latest_state(args.id, entries)
    if not state:
        sys.exit(f"Report {args.id} not found")
    update = {
        "event": "updated",
        "timestamp": now(),
        "report_id": args.id,
        "status": args.status,
    }
    if args.note:
        update["note"] = args.note
    if args.amount:
        update["bounty_paid_usd"] = args.amount
    if args.status == "paid":
        submitted_ts = _status_timestamp(args.id, entries, "submitted")
        if submitted_ts:
            try:
                t_submitted = datetime.fromisoformat(submitted_ts.replace("Z", "+00:00"))
                t_paid = datetime.fromisoformat(update["timestamp"].replace("Z", "+00:00"))
                update["days_to_payout"] = (t_paid - t_submitted).days
            except Exception:
                pass  # fail-open — don't block the status write over a bad timestamp
    append(update)
    print(f"[+] {args.id} → {args.status}")
    if "days_to_payout" in update:
        print(f"    days_to_payout: {update['days_to_payout']}")


def cmd_list(args):
    entries = read_all()
    by_id = {}
    for e in entries:
        rid = e.get("report_id")
        if rid:
            by_id[rid] = {**by_id.get(rid, {}), **e}

    print(f"{'ID':<6} {'TARGET':<30} {'PLATFORM':<12} {'STATUS':<14} {'BOUNTY':<10}")
    print("-" * 80)
    for rid, state in sorted(by_id.items()):
        target = (state.get("target") or "")[:28]
        platform = (state.get("platform") or "")[:10]
        status = (state.get("status") or "")[:12]
        bounty = state.get("bounty_paid_usd") or state.get("estimated_bounty") or ""
        print(f"{rid:<6} {target:<30} {platform:<12} {status:<14} {bounty}")


def cmd_pending(args):
    entries = read_all()
    by_id = {}
    for e in entries:
        rid = e.get("report_id")
        if rid:
            by_id[rid] = {**by_id.get(rid, {}), **e}

    pending_statuses = {"submitted", "triaged"}
    pending = [s for s in by_id.values() if s.get("status") in pending_statuses]
    print(f"[*] Pending response: {len(pending)} reports")
    for s in pending:
        ts = s.get("timestamp", "")
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(ts.replace("Z", "+00:00"))).days
        except Exception:
            age = "?"
        print(f"  {s['report_id']:<6} {s.get('target', ''):<30} "
              f"{s.get('platform', ''):<12} age={age}d")


def cmd_overdue(args):
    entries = read_all()
    by_id = {}
    for e in entries:
        rid = e.get("report_id")
        if rid:
            by_id[rid] = {**by_id.get(rid, {}), **e}

    cutoff_days = args.days
    cutoff = datetime.now(timezone.utc) - timedelta(days=cutoff_days)
    pending_statuses = {"submitted", "triaged"}
    overdue = []
    for s in by_id.values():
        if s.get("status") not in pending_statuses:
            continue
        try:
            ts = datetime.fromisoformat(s["timestamp"].replace("Z", "+00:00"))
        except Exception:
            continue
        if ts < cutoff:
            overdue.append(s)

    print(f"[!] Overdue (>{cutoff_days}d, no progress): {len(overdue)}")
    for s in overdue:
        print(f"  {s['report_id']} {s.get('target', '')} — {s.get('platform', '')} "
              f"[{s.get('status', '')}] — follow-up needed!")


def cmd_payout_stats(args):
    """Per-program aggregation by platform: payout velocity/fairness (avg/min/max days_to_payout)."""
    entries = read_all()
    by_id = {}
    for e in entries:
        rid = e.get("report_id")
        if rid:
            by_id[rid] = {**by_id.get(rid, {}), **e}

    by_platform: dict[str, list[float]] = {}
    for state in by_id.values():
        dtp = state.get("days_to_payout")
        if dtp is None:
            continue
        platform = state.get("platform") or "?"
        by_platform.setdefault(platform, []).append(dtp)

    if not by_platform:
        print("[payout-stats] no paid reports with days_to_payout yet")
        return

    print(f"{'PLATFORM':<14} {'PAYOUTS':<9} {'AVG DAYS':<10} {'MIN':<6} {'MAX':<6}")
    print("-" * 50)
    for platform, days_list in sorted(by_platform.items()):
        avg = sum(days_list) / len(days_list)
        print(f"{platform:<14} {len(days_list):<9} {avg:<10.1f} {min(days_list):<6.0f} {max(days_list):<6.0f}")


def _next_abort_id(aborts: list[dict]) -> str:
    ids = {e.get("abort_id") for e in aborts if e.get("abort_id")}
    return f"A{len(ids) + 1:03d}"


def cmd_abort(args):
    """Record a first-pass abort decision (Mandate 0.2 calibration source)."""
    aborts = read_aborts()
    aid = _next_abort_id(aborts)
    entry = {
        "event": "abort_decision",
        "timestamp": now(),
        "abort_id": aid,
        "target": args.target,
        "hours_spent": args.hours_spent,
        "hypotheses_tried": args.hypotheses_tried,
        "phases_completed": args.phases_completed,
        "reason": args.reason,
        "status": "abort_declared",
    }
    append_abort(entry)
    print(f"[abort] {aid} declared for {args.target} after {args.hours_spent}h / "
          f"{args.hypotheses_tried} hypotheses. Status: abort_declared.")
    print(f"[reminder] per Mandate 0.2 — run aggressive SECOND PASS before treating this as final.")


def cmd_abort_reverse(args):
    """First-pass abort reversed by second pass — finding(s) eventually emerged.

    This is the false-abort signal — calibration source for "I gave up too early".
    """
    aborts = read_aborts()
    if not any(e.get("abort_id") == args.id for e in aborts):
        sys.exit(f"Abort {args.id} not found")
    entry = {
        "event": "abort_reversed",
        "timestamp": now(),
        "abort_id": args.id,
        "findings_after": args.findings_after,
        "second_pass_trigger": args.trigger,
        "note": args.note,
        "status": "false_abort",
    }
    append_abort(entry)
    print(f"[abort] {args.id} REVERSED — {args.findings_after} findings found after second pass.")
    print(f"[calibration] this is a false_abort. Adds to self-calibration signal.")


def cmd_abort_confirm(args):
    """Second pass also produced nothing — target genuinely empty."""
    aborts = read_aborts()
    if not any(e.get("abort_id") == args.id for e in aborts):
        sys.exit(f"Abort {args.id} not found")
    entry = {
        "event": "abort_confirmed",
        "timestamp": now(),
        "abort_id": args.id,
        "note": args.note,
        "status": "confirmed_abort",
    }
    append_abort(entry)
    print(f"[abort] {args.id} CONFIRMED — second pass also empty.")


def cmd_abort_stats(args):
    """Self-calibration: how often does first-pass abort = wrong?"""
    aborts = read_aborts()
    by_id: dict[str, dict] = {}
    for e in aborts:
        aid = e.get("abort_id")
        if not aid:
            continue
        by_id[aid] = {**by_id.get(aid, {}), **e}

    declared = [e for e in by_id.values() if e.get("status") in
                ("abort_declared", "false_abort", "confirmed_abort")]
    false_aborts = [e for e in by_id.values() if e.get("status") == "false_abort"]
    confirmed = [e for e in by_id.values() if e.get("status") == "confirmed_abort"]
    still_open = [e for e in by_id.values() if e.get("status") == "abort_declared"]

    total = len(declared)
    print(f"[abort-stats] total abort decisions: {total}")
    print(f"  false_abort (reversed by 2nd pass):  {len(false_aborts)}")
    print(f"  confirmed_abort (truly empty):       {len(confirmed)}")
    print(f"  still_open (no resolution yet):      {len(still_open)}")
    resolved = len(false_aborts) + len(confirmed)
    if resolved > 0:
        rate = 100.0 * len(false_aborts) / resolved
        print(f"  → FALSE-ABORT RATE: {rate:.1f}%  "
              f"(of resolved decisions)")
        if rate >= 30:
            print(f"  [SIGNAL] you abort too early. Push further BEFORE next abort decision.")
        elif rate <= 10:
            print(f"  [SIGNAL] abort discipline calibrated well.")
    else:
        print(f"  → not enough resolved data for calibration signal yet.")

    if false_aborts:
        print(f"\n[false abort details]")
        for e in false_aborts:
            print(f"  {e['abort_id']} {e.get('target','')} — "
                  f"reversed with {e.get('findings_after','?')} findings  "
                  f"(trigger: {e.get('second_pass_trigger','—')})")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add")
    p.add_argument("--target", required=True)
    p.add_argument("--finding", required=True)
    p.add_argument("--platform", required=True,
                   choices=["hackerone", "bugcrowd", "immunefi",
                            "intigriti", "yeswehack", "hackenproof",
                            "standoff365", "bizone", "cantina", "direct"])
    p.add_argument("--severity")
    p.add_argument("--bounty", type=float)

    p = sub.add_parser("update")
    p.add_argument("--id", required=True)
    p.add_argument("--status", required=True,
                   choices=["draft", "submitted", "triaged", "accepted",
                            "duplicate", "rejected", "paid", "no-response"])
    p.add_argument("--note")
    p.add_argument("--amount", type=float)

    sub.add_parser("list")
    sub.add_parser("pending")
    p = sub.add_parser("overdue")
    p.add_argument("--days", type=int, default=30)
    sub.add_parser("payout-stats", help="Per-program aggregation by platform: payout velocity/fairness")

    # --- abort tracking (Mandate 0.2 calibration) ---
    p = sub.add_parser("abort", help="Record first-pass abort decision")
    p.add_argument("--target", required=True)
    p.add_argument("--hours-spent", type=float, required=True)
    p.add_argument("--hypotheses-tried", type=int, required=True)
    p.add_argument("--phases-completed", default="")
    p.add_argument("--reason", required=True)

    p = sub.add_parser("abort-reverse",
                       help="Abort reversed — second pass found bug(s)")
    p.add_argument("--id", required=True)
    p.add_argument("--findings-after", type=int, required=True)
    p.add_argument("--trigger", default="operator_pushback",
                   help="what triggered the second pass")
    p.add_argument("--note")

    p = sub.add_parser("abort-confirm",
                       help="Second pass also produced nothing — abort stands")
    p.add_argument("--id", required=True)
    p.add_argument("--note")

    sub.add_parser("abort-stats",
                   help="Self-calibration: false-abort rate over time")

    args = ap.parse_args()
    cmd_map = {"add": cmd_add, "update": cmd_update, "list": cmd_list,
               "pending": cmd_pending, "overdue": cmd_overdue,
               "payout-stats": cmd_payout_stats,
               "abort": cmd_abort, "abort-reverse": cmd_abort_reverse,
               "abort-confirm": cmd_abort_confirm,
               "abort-stats": cmd_abort_stats}
    cmd_map[args.cmd](args)


if __name__ == "__main__":
    main()
