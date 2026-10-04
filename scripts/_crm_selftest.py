#!/usr/bin/env python3
"""
Persistent selftest for Task 8 (FDE Plan 7, §62): `_crm.py` payout-velocity fields
(`days_to_payout` in cmd_update, `_status_timestamp` helper, `payout-stats` command).

ISOLATION FROM THE TOOLKIT'S REAL DATA (mandatory requirement):
`_crm.py` builds `CRM_DIR = Path("sessions/_crm")` as a path RELATIVE to the process's
current working directory (not to the script's location) and creates it on import
(`CRM_DIR.mkdir(...)` — a module-level top-level side effect). So we do NOT import
`_crm` into this process (importing it would create/touch CRM_DIR relative to the
selftest's CWD) — instead we run `_crm.py` as a SUBPROCESS with `cwd=<tempfile.mkdtemp()>`
for every testcase. The relative `sessions/_crm` resolves inside the temp folder, so the
real `bug-bounty-toolkit/sessions/_crm/` (live reports.jsonl/abort_log.jsonl) is never
read or written. `isolation_guard()` additionally proves this: it snapshots mtime+size
of the real files BEFORE and AFTER the whole run and requires a byte-for-byte match.

Cases:
  (a) created -> submitted (5 days ago) -> paid  =>  days_to_payout == 5
  (b) payout-stats aggregates avg/min/max per platform (2 platforms, 3 paid records)
  (c) additive: a legacy record WITHOUT days_to_payout doesn't break list/payout-stats
  (d) fail-open: a corrupted submitted-timestamp doesn't break the paid status record
      (days_to_payout simply isn't set, the error is swallowed)

Usage:
    py -3 -X utf8 bug-bounty-toolkit/scripts/_crm_selftest.py
"""

import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

CRM_SCRIPT = Path(__file__).resolve().parent / "_crm.py"
REAL_CRM_DIR = Path(__file__).resolve().parent.parent / "sessions" / "_crm"

results = []  # list[(name, passed)]


def check(name, condition, detail=""):
    results.append((name, bool(condition)))
    status = "PASS" if condition else "FAIL"
    line = f"  [{status}] {name}"
    if not condition and detail:
        line += f"\n         detail: {detail!r}"
    print(line)


def run(cwd, *args):
    """Run _crm.py <args> as a subprocess with cwd=<isolated tempdir>."""
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(CRM_SCRIPT), *args],
        cwd=str(cwd), capture_output=True, text=True,
    )


def reports_file(cwd) -> Path:
    return Path(cwd) / "sessions" / "_crm" / "reports.jsonl"


def append_raw(cwd, entry: dict):
    """Append a raw JSONL line directly (bypass CLI) — needed to control timestamps
    that cmd_update always stamps with now()."""
    f = reports_file(cwd)
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_entries(cwd) -> list:
    f = reports_file(cwd)
    if not f.exists():
        return []
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]


def no_traceback(*texts) -> bool:
    return all("Traceback" not in t for t in texts)


# ---------------------------------------------------------------------------
# (a) created -> submitted (5 days ago) -> paid  =>  days_to_payout == 5
# ---------------------------------------------------------------------------
def test_days_to_payout_basic():
    print("[test a] days_to_payout basic (5-day submitted->paid gap)")
    with tempfile.TemporaryDirectory() as td:
        r = run(td, "add", "--target", "testtarget-a", "--finding", "F001",
                "--platform", "hackerone", "--severity", "high", "--bounty", "100")
        check("a: add exits 0", r.returncode == 0, r.stderr)
        check("a: add creates R001", "R001" in r.stdout, r.stdout)

        submitted_ts = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        append_raw(td, {"event": "updated", "timestamp": submitted_ts,
                         "report_id": "R001", "status": "submitted"})

        r = run(td, "update", "--id", "R001", "--status", "paid", "--amount", "500")
        check("a: update paid exits 0", r.returncode == 0, r.stderr)
        check("a: stdout prints days_to_payout: 5", "days_to_payout: 5" in r.stdout, r.stdout)

        entries = read_entries(td)
        paid = [e for e in entries if e.get("report_id") == "R001" and e.get("status") == "paid"]
        check("a: exactly one paid entry recorded", len(paid) == 1, entries)
        if paid:
            check("a: days_to_payout field == 5 in stored entry",
                  paid[-1].get("days_to_payout") == 5, paid[-1])


# ---------------------------------------------------------------------------
# (b) payout-stats aggregates avg/min/max per platform
# ---------------------------------------------------------------------------
def submit_and_pay(td, report_id, days_ago):
    submitted_ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    append_raw(td, {"event": "updated", "timestamp": submitted_ts,
                     "report_id": report_id, "status": "submitted"})
    return run(td, "update", "--id", report_id, "--status", "paid")


def test_payout_stats_aggregation():
    print("[test b] payout-stats aggregates avg/min/max per platform")
    with tempfile.TemporaryDirectory() as td:
        run(td, "add", "--target", "t1", "--finding", "F1", "--platform", "hackerone")  # -> R001
        run(td, "add", "--target", "t2", "--finding", "F2", "--platform", "hackerone")  # -> R002
        run(td, "add", "--target", "t3", "--finding", "F3", "--platform", "bugcrowd")   # -> R003

        r1 = submit_and_pay(td, "R001", 3)
        r2 = submit_and_pay(td, "R002", 7)
        r3 = submit_and_pay(td, "R003", 10)
        check("b: all 3 update-paid calls exit 0",
              r1.returncode == 0 and r2.returncode == 0 and r3.returncode == 0,
              (r1.stderr, r2.stderr, r3.stderr))

        r = run(td, "payout-stats")
        check("b: payout-stats exits 0", r.returncode == 0, r.stderr)
        print("  --- payout-stats stdout ---")
        for line in r.stdout.splitlines():
            print(f"    {line}")

        rows = {}
        for line in r.stdout.splitlines():
            parts = line.split()
            if parts and parts[0] in ("hackerone", "bugcrowd"):
                rows[parts[0]] = parts

        check("b: hackerone row present", "hackerone" in rows, r.stdout)
        check("b: bugcrowd row present", "bugcrowd" in rows, r.stdout)

        if "hackerone" in rows:
            platform, payouts, avg, mn, mx = rows["hackerone"]
            check("b: hackerone payouts == 2", payouts == "2", rows["hackerone"])
            check("b: hackerone avg == 5.0 ((3+7)/2)", avg == "5.0", rows["hackerone"])
            check("b: hackerone min == 3", mn == "3", rows["hackerone"])
            check("b: hackerone max == 7", mx == "7", rows["hackerone"])

        if "bugcrowd" in rows:
            platform, payouts, avg, mn, mx = rows["bugcrowd"]
            check("b: bugcrowd payouts == 1", payouts == "1", rows["bugcrowd"])
            check("b: bugcrowd avg == 10.0", avg == "10.0", rows["bugcrowd"])
            check("b: bugcrowd min == 10", mn == "10", rows["bugcrowd"])
            check("b: bugcrowd max == 10", mx == "10", rows["bugcrowd"])


# ---------------------------------------------------------------------------
# (c) additive: legacy record WITHOUT days_to_payout doesn't crash list/payout-stats
# ---------------------------------------------------------------------------
def test_additive_legacy_record():
    print("[test c] additive — legacy record without days_to_payout survives list/payout-stats")
    with tempfile.TemporaryDirectory() as td:
        now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        # Simulate a pre-Task8 CRM record written by an older version of the script:
        # 'paid' status present, but NO days_to_payout key at all (field didn't exist yet).
        append_raw(td, {"event": "created", "timestamp": now_ts, "report_id": "R900",
                         "target": "legacy-target", "finding_id": "F900", "platform": "immunefi",
                         "severity": "medium", "estimated_bounty": 5000, "status": "draft"})
        append_raw(td, {"event": "updated", "timestamp": now_ts, "report_id": "R900",
                         "status": "paid", "bounty_paid_usd": 5000})  # note: no days_to_payout

        r_list = run(td, "list")
        check("c: list exits 0 on legacy record", r_list.returncode == 0, r_list.stderr)
        check("c: list has no traceback", no_traceback(r_list.stdout, r_list.stderr),
              r_list.stdout + r_list.stderr)
        check("c: list shows legacy R900", "R900" in r_list.stdout, r_list.stdout)

        r_stats = run(td, "payout-stats")
        check("c: payout-stats exits 0 on legacy record", r_stats.returncode == 0, r_stats.stderr)
        check("c: payout-stats has no traceback", no_traceback(r_stats.stdout, r_stats.stderr),
              r_stats.stdout + r_stats.stderr)


# ---------------------------------------------------------------------------
# (d) fail-open: malformed submitted timestamp doesn't crash the 'paid' status write
# ---------------------------------------------------------------------------
def test_fail_open_broken_timestamp():
    print("[test d] fail-open — malformed submitted timestamp doesn't crash paid update")
    with tempfile.TemporaryDirectory() as td:
        r = run(td, "add", "--target", "testtarget-d", "--finding", "F001", "--platform", "hackerone")
        check("d: add exits 0", r.returncode == 0, r.stderr)

        append_raw(td, {"event": "updated", "timestamp": "not-a-valid-timestamp",
                         "report_id": "R001", "status": "submitted"})

        r = run(td, "update", "--id", "R001", "--status", "paid")
        check("d: update paid exits 0 despite malformed submitted timestamp",
              r.returncode == 0, r.stderr)
        check("d: no traceback in output", no_traceback(r.stdout, r.stderr),
              r.stdout + r.stderr)
        check("d: days_to_payout NOT printed (fail-open skip, no crash)",
              "days_to_payout" not in r.stdout, r.stdout)
        check("d: status update line still printed",
              "R001" in r.stdout and "paid" in r.stdout, r.stdout)

        entries = read_entries(td)
        paid = [e for e in entries if e.get("report_id") == "R001" and e.get("status") == "paid"]
        check("d: paid entry still recorded despite bad timestamp", len(paid) == 1, entries)
        if paid:
            check("d: paid entry has no days_to_payout key (fail-open, not a bogus value)",
                  "days_to_payout" not in paid[-1], paid[-1])


# ---------------------------------------------------------------------------
# Isolation guard: real toolkit CRM data must be byte-for-byte untouched
# ---------------------------------------------------------------------------
def snapshot_real_dir():
    snap = {}
    if REAL_CRM_DIR.exists():
        for f in sorted(REAL_CRM_DIR.iterdir()):
            if f.is_file():
                st = f.stat()
                snap[f.name] = (st.st_mtime_ns, st.st_size)
    return snap


def main():
    before = snapshot_real_dir()
    print(f"[isolation] real CRM dir: {REAL_CRM_DIR}")
    print(f"[isolation] snapshot before run: {before}\n")

    test_days_to_payout_basic()
    test_payout_stats_aggregation()
    test_additive_legacy_record()
    test_fail_open_broken_timestamp()

    print()
    after = snapshot_real_dir()
    check("isolation: real CRM dir untouched by selftest (mtime+size unchanged)",
          before == after, {"before": before, "after": after})

    print()
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"{passed}/{total} passed")
    for name, ok in results:
        if not ok:
            print(f"  FAILED: {name}")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
