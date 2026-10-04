#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Selftest for yield_rollup.py (Plan 9 T7, Tier C — BASE).

Proves: found_by is PARSED from the Banked Findings section and AGGREGATED cross-hunt;
template placeholder rows are ignored; internal `|` in found_by are stitched back;
fail-open on a missing ledger; the real `hypotheses_template.md` (empty Banked) yields 0 findings.

Run: py -3 -X utf8 scripts/_methodology/yield_rollup_selftest.py
"""
# Ensure UTF-8 stdout so the summary (arrows/checks) prints on any console (Windows cp1251, etc.).
import sys as _utf8_sys
try:
    _utf8_sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import importlib.util
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("yield_rollup", os.path.join(_HERE, "yield_rollup.py"))
yr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(yr)

ROOT = os.path.dirname(os.path.dirname(_HERE))
REAL_TPL = os.path.join(ROOT, "sessions", "_methodology", "hypotheses_template.md")

results = []


def ok(name, cond, detail=""):
    results.append(bool(cond))
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name, ("  — " + detail) if detail else ""))


# ── fixture ledger with a filled Banked table (2 findings, one with internal `|` in found_by)
# NOTE: the Russian table header cells below ("What (1 line)", "from rubric", "Status") are parser input
# and are kept verbatim; the parser keys on the lowercased Russian "Status" column name.
FIX = """# Foo — Hypotheses Registry

## Banked Findings (confirmed Medium/Low)

| # | Severity | H-NN | Что (1 строка) | Payout-tier (из рубрики) | found_by | Статус |
|---|---|---|---|---|---|---|
| 1 | Medium | H-03 | share rounding | $2-5K | deephunt-J5-depth | opus | composition-seam | ~3h | T4-done |
| 2 | Low | H-07 | event topic | $1K | scout-P6 | sonnet | negative-space | ~1h | confirmed |
| | | | | | | |

## Active Hypotheses
"""

rows = yr.parse_banked(FIX)
ok("parse_banked finds 2 filled rows (placeholder skipped)", len(rows) == 2,
   "got %d" % len(rows))

if len(rows) == 2:
    r0 = rows[0]["found_by_parsed"]
    ok("internal-pipe found_by parsed: phase", r0["phase"] == "deephunt-J5-depth", repr(r0))
    ok("internal-pipe found_by parsed: model", r0["model"] == "opus", repr(r0))
    ok("internal-pipe found_by parsed: undup-origin", r0["undup_origin"] == "composition-seam", repr(r0))
    ok("internal-pipe found_by parsed: cost", r0["cost"] == "~3h", repr(r0))
    ok("status column intact after overflow-merge", rows[0].get("статус") == "T4-done",
       repr(rows[0].get("статус")))

# ── rollup aggregates across two fixture ledgers in a temp sessions/
work = tempfile.mkdtemp()
for slug in ("alpha", "beta"):
    d = os.path.join(work, slug)
    os.makedirs(d)
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(FIX)

summ = yr.rollup(sessions_dir=work)
ok("rollup total_found across 2 ledgers == 4", summ["total_found"] == 4, repr(summ["total_found"]))
ok("aggregate by_model opus==2", summ["by_model"].get("opus") == 2, repr(summ["by_model"]))
ok("aggregate by_phase scout-P6==2", summ["by_phase"].get("scout-P6") == 2, repr(summ["by_phase"]))
ok("aggregate by_undup_origin composition-seam==2",
   summ["by_undup_origin"].get("composition-seam") == 2, repr(summ["by_undup_origin"]))

# ── fail-open: a nonexistent ledger does not crash
summ2 = yr.rollup(ledgers=[os.path.join(work, "does-not-exist", "hypotheses.md")])
ok("fail-open on missing ledger (total 0, no crash)", summ2["total_found"] == 0)

# ── real template: Banked is empty (placeholder only) → 0 findings (detector matches the template)
if os.path.exists(REAL_TPL):
    with open(REAL_TPL, encoding="utf-8") as f:
        tpl_rows = yr.parse_banked(f.read())
    ok("real hypotheses_template.md Banked has header col found_by, 0 filled rows",
       len(tpl_rows) == 0, "got %d" % len(tpl_rows))
else:
    ok("real template present", False, "missing template")

import shutil
shutil.rmtree(work, ignore_errors=True)

n = sum(results)
print("\n%d/%d yield_rollup cases green" % (n, len(results)))
sys.exit(0 if n == len(results) else 1)
