# -*- coding: utf-8 -*-
"""Selftest for business_logic.py (FDE Plan 5, Task 6).

Proves:
 (1) race_candidates(["/coupon/redeem", "/static/logo"]) -> exactly the redeem endpoint is a
     candidate; the static asset is not.
 (2) race_probe_plan(endpoint, n=20) -> N probes, every one marked idempotent_safe; execution is
     explicitly NOT performed here.
 (3) method_matrix(endpoint) -> exactly the 6-verb matrix.
 (4) mass_assignment_fields({"fields": ["name", "is_admin"]}) -> only "is_admin" (BOPLA candidate).
 (5) analyze_business_flow on a flow with a replay-able one-shot step -> at least one BL-NN row
     with vector == "replay".
 (6) analyze_business_flow on a flow with a gate-then-target ordering -> a "skip" candidate; a flow
     with only the target step (no gate) does not produce a skip candidate for it.
 (7) state_machine_analyzer.py web2 branch: analyze_business_flow() delegates to business_logic.py
     and returns the same shape (web3 .sol scanning path untouched -- import-only regression proof).

Run: py -3 -X utf8 scripts/web2/business_logic_selftest.py
"""
# Ensure UTF-8 stdout so the summary (arrows/checks) prints on any console (Windows cp1251, etc.).
import sys as _utf8_sys
try:
    _utf8_sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import os
import sys
import importlib.util

ROOT = os.getcwd()
while ROOT and not os.path.isdir(os.path.join(ROOT, "sessions")):
    nxt = os.path.dirname(ROOT)
    if nxt == ROOT:
        break
    ROOT = nxt
WEB2_DIR = os.path.join(ROOT, "scripts", "web2")
SMA_PATH = os.path.join(ROOT, "scripts", "web3", "advanced", "state_machine_analyzer.py")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


bl = _load("business_logic", os.path.join(WEB2_DIR, "business_logic.py"))

results = []


def check(n, c, d=""):
    results.append((n, bool(c), d))


# ── CASE 1: race_candidates ─────────────────────────────────────────────────────────────────────
cands = bl.race_candidates(["/coupon/redeem", "/static/logo"])
urls = [c["url"] for c in cands]
check("1a race_candidates: redeem endpoint IS a candidate", "/coupon/redeem" in urls, str(urls))
check("1b race_candidates: static asset is NOT a candidate", "/static/logo" not in urls, str(urls))
check("1c race_candidates: exactly 1 candidate out of 2 inputs", len(cands) == 1, str(cands))

# ── CASE 2: race_probe_plan ─────────────────────────────────────────────────────────────────────
plan = bl.race_probe_plan("/coupon/redeem", n=20)
check("2a race_probe_plan: N probes == 20", len(plan.get("probes", [])) == 20, str(len(plan.get("probes", []))))
check("2b race_probe_plan: top-level idempotent_safe marked True", plan.get("idempotent_safe") is True)
check("2c race_probe_plan: every probe marked idempotent_safe",
      all(p.get("idempotent_safe") is True for p in plan.get("probes", [])))
check("2d race_probe_plan: execution explicitly NOT performed here",
      "not here" in str(plan.get("execution", "")).lower())

# ── CASE 3: method_matrix ───────────────────────────────────────────────────────────────────────
mm = bl.method_matrix("/api/orders/1")
check("3 method_matrix == 6-verb matrix",
      mm == ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"], str(mm))

# ── CASE 4: mass_assignment_fields ──────────────────────────────────────────────────────────────
maf = bl.mass_assignment_fields({"fields": ["name", "is_admin"]})
check("4a mass_assignment_fields: is_admin IS a candidate", "is_admin" in maf, str(maf))
check("4b mass_assignment_fields: name is NOT a candidate", "name" not in maf, str(maf))
check("4c mass_assignment_fields: non-dict input -> []", bl.mass_assignment_fields(["x"]) == [])
check("4d mass_assignment_fields: missing 'fields' key -> []", bl.mass_assignment_fields({}) == [])

# ── CASE 5: analyze_business_flow -- replay ─────────────────────────────────────────────────────
replay_flow = [{"action": "add_to_cart"}, {"action": "apply_coupon"}, {"action": "checkout"}]
rows = bl.analyze_business_flow(replay_flow)
replay_rows = [r for r in rows if r["vector"] == "replay"]
check("5a analyze_business_flow: replay candidate found", len(replay_rows) >= 1, str(rows))
check("5b analyze_business_flow: BL-NN id format", all(r["id"].startswith("BL-") for r in rows), str(rows))
check("5c analyze_business_flow: skeleton status == {TODO}", all(r["status"] == "{TODO}" for r in rows), str(rows))

# ── CASE 6: analyze_business_flow -- skip ───────────────────────────────────────────────────────
skip_flow = [{"action": "verify_payment"}, {"action": "ship_order"}]
skip_rows = [r for r in bl.analyze_business_flow(skip_flow) if r["vector"] == "skip"]
check("6a analyze_business_flow: gate-then-target -> skip candidate found", len(skip_rows) >= 1, str(skip_rows))

no_gate_flow = [{"action": "ship_order"}]
no_gate_skip_rows = [r for r in bl.analyze_business_flow(no_gate_flow) if r["vector"] == "skip"]
check("6b analyze_business_flow: target with NO preceding gate -> no skip candidate",
      len(no_gate_skip_rows) == 0, str(no_gate_skip_rows))

# ── CASE 7: state_machine_analyzer.py web2 branch delegates to business_logic ──────────────────
sma = _load("state_machine_analyzer", SMA_PATH)
check("7a state_machine_analyzer exposes analyze_business_flow", hasattr(sma, "analyze_business_flow"))
if hasattr(sma, "analyze_business_flow"):
    sma_rows = sma.analyze_business_flow(replay_flow)
    check("7b state_machine_analyzer.analyze_business_flow == business_logic.analyze_business_flow output",
          sma_rows == rows, "sma=%s bl=%s" % (sma_rows, rows))
check("7c state_machine_analyzer web3 surface untouched (scan_file still present)",
      hasattr(sma, "scan_file") and hasattr(sma, "analyze_liveness") and hasattr(sma, "ENUM_DEF"))

print("=== business_logic.py SELFTEST ===")
ok = sum(1 for _, p, _ in results if p)
for n, p, d in results:
    print(("  [PASS] " if p else "  [FAIL] ") + n + (("  -- " + d) if d and not p else ""))
print("\n%d/%d green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
