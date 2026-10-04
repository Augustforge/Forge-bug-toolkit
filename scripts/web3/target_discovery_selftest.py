#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Selftest for target_discovery.py (Plan 9, T12).

Proves on an OFFLINE fixture (no network):
  1. The scoring math is correct (exact factors + EV for constructed programs).
  2. The ranking is correct (descending EV order).
  3. The anonymity precondition is ENFORCED BEFORE any live call — on failure fetch_fn is NOT called (FIRING
     of the block), on success it is called (good case). Fail-closed on a missing key.
  4. Scoring fail-open: a broken record → EV 0, doesn't crash the ranking.

Run: py -3 -X utf8 scripts/web3/target_discovery_selftest.py
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

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("target_discovery", os.path.join(_HERE, "target_discovery.py"))
td = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(td)

results = []


def ok(name, cond, detail=""):
    results.append(bool(cond))
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name, ("  -- " + detail) if detail and not cond else ""))


def approx(a, b, eps=1e-9):
    return abs(a - b) < eps


NOW = 1_000_000_000.0  # fixed "now" for determinism
DAY = 86400.0

# ---------------------------------------------------------------------------
# 1. Scoring math (exact values)
# ---------------------------------------------------------------------------
print("-- scoring math (exact factors)")

# Program A: payout=1M→1.0, age=0→fresh 1.0, reports=0 private→crowd 1.0, tags full-match→pattern 1.0, EV=1.0
progA = {"name": "A", "max_payout": 1_000_000, "launched_ts": NOW,
         "reports_count": 0, "is_public": False, "tags": ["solana", "amm"]}
sA = td.ev_score(progA, now=NOW, strong_patterns=["solana", "amm"])
ok("A payout_factor == 1.0", approx(sA.factors["payout"], 1.0))
ok("A freshness == 1.0 (age 0)", approx(sA.factors["freshness"], 1.0))
ok("A crowd == 1.0 (0 reports, private)", approx(sA.factors["crowd"], 1.0))
ok("A pattern == 1.0 (full match)", approx(sA.factors["pattern"], 1.0))
ok("A EV == 1.0", approx(sA.ev, 1.0), "got %r" % sA.ev)

# Program B: payout=500k→0.5, age=90d→fresh 0.5, crowd 1.0, pattern 1.0 → EV=0.25
progB = {"name": "B", "max_payout": 500_000, "launched_ts": NOW - 90 * DAY,
         "reports_count": 0, "is_public": False, "tags": ["solana"]}
sB = td.ev_score(progB, now=NOW, strong_patterns=["solana"])
ok("B payout == 0.5", approx(sB.factors["payout"], 0.5))
ok("B freshness == 0.5 (age=halflife)", approx(sB.factors["freshness"], 0.5))
ok("B EV == 0.25", approx(sB.ev, 0.25), "got %r" % sB.ev)

# Program C: crowd_heat = 1 + 9 reports + 3 public = 13 → crowd_factor 1/13
progC = {"name": "C", "max_payout": 1_000_000, "launched_ts": NOW,
         "reports_count": 9, "is_public": True, "tags": ["solana", "amm"]}
sC = td.ev_score(progC, now=NOW, strong_patterns=["solana", "amm"])
ok("C crowd_heat == 13", approx(td.crowd_heat(progC), 13.0))
ok("C crowd_factor == 1/13", approx(sC.factors["crowd"], 1.0 / 13.0))
ok("C EV == 1/13", approx(sC.ev, 1.0 / 13.0), "got %r" % sC.ev)

# pattern floor: no matching tags → PATTERN_BASE (0.5), NOT zero
progNoMatch = {"name": "N", "max_payout": 1_000_000, "launched_ts": NOW,
               "reports_count": 0, "is_public": False, "tags": ["web2", "api"]}
sN = td.ev_score(progNoMatch, now=NOW, strong_patterns=["solana", "amm"])
ok("no-match pattern == PATTERN_BASE (floor, not 0)", approx(sN.factors["pattern"], td.PATTERN_BASE))
ok("no-match EV nonzero", sN.ev > 0)

# unknown payout → UNKNOWN_PAYOUT floor, not crash/zero-total
progUnk = {"name": "U", "launched_ts": NOW, "reports_count": 0}
sU = td.ev_score(progUnk, now=NOW)
ok("unknown payout == UNKNOWN_PAYOUT", approx(sU.factors["payout"], td.UNKNOWN_PAYOUT))

# no strong_patterns → pattern neutral 1.0
sNeutral = td.ev_score(progA, now=NOW, strong_patterns=None)
ok("no strong_patterns → pattern 1.0 neutral", approx(sNeutral.factors["pattern"], 1.0))

# ---------------------------------------------------------------------------
# 2. Ranking (descending EV)
# ---------------------------------------------------------------------------
print("-- ranking")
ranked = td.rank_programs([progC, progA, progB], now=NOW, strong_patterns=["solana", "amm"])
ok("ranking order A > B > C", [s.name for s in ranked] == ["A", "B", "C"],
   "got %r" % [s.name for s in ranked])
ok("ranking EV monotonic desc", all(ranked[i].ev >= ranked[i + 1].ev for i in range(len(ranked) - 1)))

# ---------------------------------------------------------------------------
# 3. Anonymity precondition ENFORCED BEFORE the live call (FIRING)
# ---------------------------------------------------------------------------
print("-- anonymity precondition (fail-closed, blocks live call)")

calls = {"n": 0}

def fake_fetch(url):
    calls["n"] += 1
    return {"name": url, "max_payout": 100_000, "launched_ts": NOW,
            "reports_count": 0, "is_public": False, "tags": ["solana"]}

# BAD config: incognito missing → precondition fails → fetch_fn MUST NOT be called
bad_cfg = {"vpn_active": True, "not_main_login": True}  # incognito missing
anon_bad, ranked_bad = td.discover_live(["u1", "u2"], bad_cfg, fake_fetch, now=NOW)
ok("bad config → anon.ok False", anon_bad.ok is False)
ok("bad config → 'incognito' in failed_checks", any("incognito" in c for c in anon_bad.failed_checks))
ok("FIRING: fetch_fn NOT called on anon failure", calls["n"] == 0, "calls=%d" % calls["n"])
ok("bad config → empty ranked", ranked_bad == [])

# config not a dict → fail-closed, also without a call
calls["n"] = 0
anon_none, ranked_none = td.discover_live(["u1"], None, fake_fetch, now=NOW)
ok("non-dict config → anon.ok False", anon_none.ok is False)
ok("non-dict config → fetch NOT called", calls["n"] == 0)

# GOOD config: all True → precondition passes → fetch_fn called for each URL
calls["n"] = 0
good_cfg = {"vpn_active": True, "incognito": True, "not_main_login": True}
anon_ok, ranked_ok = td.discover_live(["u1", "u2", "u3"], good_cfg, fake_fetch,
                                     now=NOW, strong_patterns=["solana"])
ok("good config → anon.ok True", anon_ok.ok is True)
ok("good config → fetch called for each URL", calls["n"] == 3, "calls=%d" % calls["n"])
ok("good config → 3 programs ranked", len(ranked_ok) == 3)

# fetch_fn raises an exception on one URL → fail-open per-URL (the rest are scored)
calls["n"] = 0

def flaky_fetch(url):
    calls["n"] += 1
    if url == "bad":
        raise RuntimeError("network blip")
    return {"name": url, "max_payout": 100_000, "launched_ts": NOW, "tags": ["solana"]}

anon_f, ranked_f = td.discover_live(["good1", "bad", "good2"], good_cfg, flaky_fetch, now=NOW)
ok("flaky fetch → fail-open, 2 of 3 ranked", len(ranked_f) == 2, "got %d" % len(ranked_f))

# ---------------------------------------------------------------------------
# 4. Scoring fail-open on a broken record
# ---------------------------------------------------------------------------
print("-- scoring fail-open on malformed input")
mixed = [progA, "not a dict", {"name": "junk", "max_payout": object(), "tags": 123}, progB]
ranked_mixed = td.rank_programs(mixed, now=NOW, strong_patterns=["solana", "amm"])
ok("malformed list doesn't crash the ranking", isinstance(ranked_mixed, list))
ok("non-dict element skipped, dict records remain", "A" in [s.name for s in ranked_mixed])
ok("junk record with odd fields doesn't crash (EV assigned)",
   any(s.name == "junk" for s in ranked_mixed))

# ---------------------------------------------------------------------------
n = sum(results)
print("\n%d/%d target_discovery selftest cases green" % (n, len(results)))
sys.exit(0 if n == len(results) else 1)
