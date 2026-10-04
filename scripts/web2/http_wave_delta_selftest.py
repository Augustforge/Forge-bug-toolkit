# -*- coding: utf-8 -*-
"""Selftest для http_wave_delta.py — NEW/REGRESSION/PERSISTENT/CHANGE/REVERSED классификация,
weak↔safe семантика, REVERSED=P0 (защита откачена)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import http_wave_delta as hwd  # noqa: E402

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))

def cats(delta, cat):
    """множество (target,field) в категории"""
    return {(x["target"], x["field"]) for x in delta.get(cat, [])}

# ── weak_of семантика ──
check("weak_of: status 200 → weak", hwd.weak_of("status", 200) is True)
check("weak_of: status 403 → safe", hwd.weak_of("status", 403) is False)
check("weak_of: cors reflect → weak", hwd.weak_of("cors", "reflect") is True)
check("weak_of: cors none → safe", hwd.weak_of("cors", "none") is False)
check("weak_of: unknown field → None (нет семантики)", hwd.weak_of("wp_users", 10) is None)
check("weak_of: суффикс *_status → статус-семантика", hwd.weak_of("admin_status", 200) is True)
check("weak_of: auth_required=True → safe (инверсия)", hwd.weak_of("auth_required", "true") is False)

O = hwd.observe

# ── 1) PERSISTENT: не менялось ──
d1 = hwd.wave_delta([[O("/a", status=403)], [O("/a", status=403)]])
check("1 PERSISTENT: 403→403", ("/a", "status") in cats(d1, "PERSISTENT"))

# ── 2) REGRESSION: 200→403 (стало защищено) ──
d2 = hwd.wave_delta([[O("/a", status=200)], [O("/a", status=403)]])
check("2 REGRESSION: 200→403 (weak→safe)", ("/a", "status") in cats(d2, "REGRESSION"))

# ── 3) REVERSED: 200→403→200 (защита откачена после усиления) = P0 ──
d3 = hwd.wave_delta([[O("/a", status=200)], [O("/a", status=403)], [O("/a", status=200)]])
check("3 REVERSED: 200→403→200 (откат защиты)", ("/a", "status") in cats(d3, "REVERSED"))
rev_item = [x for x in d3["REVERSED"] if x["target"] == "/a"][0]
check("3 REVERSED priority = P0", rev_item["priority"] == "P0")

# ── 4) NEW: endpoint появился во 2-й волне ──
d4 = hwd.wave_delta([[O("/a", status=200)], [O("/a", status=200), O("/new", status=200)]])
check("4 NEW: /new появился во 2-й волне", ("/new", "status") in cats(d4, "NEW"))

# ── 5) CHANGE: несемантическое поле изменилось ──
d5 = hwd.wave_delta([[O("/u", wp_users=10)], [O("/u", wp_users=9)]])
check("5 CHANGE: wp_users 10→9 (нет weak-оси)", ("/u", "wp_users") in cats(d5, "CHANGE"))

# ── 6) CORS: reflect→none = REGRESSION; reflect→none→reflect = REVERSED ──
d6a = hwd.wave_delta([[O("/api", cors="reflect")], [O("/api", cors="none")]])
check("6a REGRESSION: cors reflect→none", ("/api", "cors") in cats(d6a, "REGRESSION"))
d6b = hwd.wave_delta([[O("/api", cors="reflect")], [O("/api", cors="none")], [O("/api", cors="reflect")]])
check("6b REVERSED: cors reflect→none→reflect (откат CORS-фикса)", ("/api", "cors") in cats(d6b, "REVERSED"))

# ── 7) format_delta несёт P0 для REVERSED ──
out = hwd.format_delta(d3)
check("7 format: REVERSED помечен P0 в выводе", "P0" in out and "REVERSED" in out.upper() or "откач" in out.lower())

# ── 8) многополевой снимок: смешанные категории в одной волне-паре ──
d8 = hwd.wave_delta([
    [O("/x", status=200, cors="reflect")],
    [O("/x", status=403, cors="reflect")],   # status усилился (REGRESSION), cors не менялся (PERSISTENT)
])
check("8 mixed: /x.status → REGRESSION", ("/x", "status") in cats(d8, "REGRESSION"))
check("8 mixed: /x.cors → PERSISTENT", ("/x", "cors") in cats(d8, "PERSISTENT"))

print("=== HTTP_WAVE_DELTA SELFTEST (behavioral REVERSED) ===\n")
ok = 0
for name, passed, detail in results:
    print(("  [PASS] " if passed else "  [FAIL] ") + name + (("  — " + str(detail)) if detail and not passed else ""))
    ok += 1 if passed else 0
print("\n%d/%d проверок зелёные" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
