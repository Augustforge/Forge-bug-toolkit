# -*- coding: utf-8 -*-
"""Selftest for provenance_from_traffic (authz_diff.py, Plan 9 Task T10 — Tier E composite ←T4, T9).

Proves the cross-thread fusion FIRES on an OFFLINE mock traffic-archive (no network/probe):
 (1) FIRING: an archive with a create-event (POST minting id 'A', owner user-A) AUTO-registers the
     object into {session_dir}/object_registry.json, and a LATER foreign-account (user-B) access to
     '/objects/A' is returned as a PROVEN create->access Divergence (provenance_backed=True; chain
     names object_id='A', created_by='user-A', accessed_by='user-B').
 (1b) the ledger file was physically auto-populated (record for 'A', owner 'user-A') — the caller
      registered NOTHING manually; re-mining did it.
 (2) NEGATIVE self-access: the SAME create + a later access to 'A' by user-A (the owner) yields NO
     proven chain (accessor is owner).
 (3) NEGATIVE no-create: an archive with a foreign access to 'A' but NO create-event fabricates
     nothing (empty list) AND leaves the ledger empty (no record 'A').
 (4) reuse — traffic_archive read-back: records written via traffic_archive.open_archive(live=False)
     .record() then re-mined by PATH through provenance_from_traffic(archive.path) still fire (proves
     the fusion consumes the real T9 remine round-trip, not just an in-memory list).
 (5) actor-from-header fallback: no meta actor -> the Authorization header stands in for identity
     (create by token-A, foreign access by token-B) still proves the chain.
 (6) create-id extraction variants: Location-header create (POST + Location:/objects/C) and PUT with
     a client-specified URL id (PUT /objects/B) both register and prove a later foreign access.
 (7) anti-FP: a leaked owner marker that DISAGREES with the registered owner is NOT proven (mirrors
     _apply_provenance's own guard) even though the id is registered.

Run: py -3 -X utf8 bug-bounty-toolkit/scripts/web2/provenance_from_traffic_selftest.py
"""
# Ensure UTF-8 stdout so the summary (arrows/checks) prints on any console (Windows cp1251, etc.).
import sys as _utf8_sys
try:
    _utf8_sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import os
import sys
import shutil
import importlib.util

ROOT = os.getcwd()
while ROOT and not os.path.isdir(os.path.join(ROOT, "sessions")):
    nxt = os.path.dirname(ROOT)
    if nxt == ROOT:
        break
    ROOT = nxt
WEB2_DIR = os.path.join(ROOT, "scripts", "web2")
WALLET_TEST_DIR = os.path.join(ROOT, "scripts", "dapphunt", "wallet_test")
SESSIONS_DIR = os.path.join(ROOT, "sessions")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


ad = _load("authz_diff", os.path.join(WEB2_DIR, "authz_diff.py"))
ta = _load("traffic_archive", os.path.join(WALLET_TEST_DIR, "traffic_archive.py"))

results = []


def check(n, c, d=""):
    results.append((n, bool(c), d))


def _fresh_dir(tag):
    d = os.path.join(SESSIONS_DIR, "_selftest_tmp_web2_t10_" + tag)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d, exist_ok=True)
    return d


def _chain_of(divs):
    for d in divs:
        ev = d.evidence if isinstance(d.evidence, dict) else {}
        if ev.get("provenance_backed"):
            return ev.get("provenance_chain") or {}
    return None


# Reusable records -----------------------------------------------------------------------------------
CREATE_A = {"request": {"method": "POST", "url": "https://api.example.com/objects", "headers": {}},
            "response": {"status": 201, "body": {"id": "A", "owner_id": "user-A"}},
            "meta": {"actor": "user-A"}, "ts": 1.0}
ACCESS_A_FOREIGN = {"request": {"method": "GET", "url": "https://api.example.com/objects/A",
                                "headers": {}},
                    "response": {"status": 200, "body": {"owner_id": "user-A", "balance": 999}},
                    "meta": {"actor": "user-B"}, "ts": 2.0}
ACCESS_A_SELF = {"request": {"method": "GET", "url": "https://api.example.com/objects/A",
                             "headers": {}},
                 "response": {"status": 200, "body": {"owner_id": "user-A", "balance": 10}},
                 "meta": {"actor": "user-A"}, "ts": 3.0}

_TMP_DIRS = []
_ARCH_SLUG = "_selftest_tmp_web2_t10_arch"

try:
    # ── CASE 1: FIRING — create auto-registers + foreign access -> proven chain ─────────────────────
    d1 = _fresh_dir("fire"); _TMP_DIRS.append(d1)
    proven1 = ad.provenance_from_traffic([CREATE_A, ACCESS_A_FOREIGN], d1)
    check("case1a FIRING: foreign access to a traffic-created object -> >=1 proven create->access chain",
          len(proven1) >= 1 and all((p.evidence or {}).get("provenance_backed") for p in proven1),
          "got=%r" % ([(p.dclass, (p.evidence or {}).get("provenance_backed")) for p in proven1],))
    chain1 = _chain_of(proven1)
    check("case1b FIRING: chain names object_id='A', created_by='user-A', accessed_by='user-B'",
          bool(chain1) and str(chain1.get("object_id")) == "A"
          and str(chain1.get("created_by")) == "user-A" and str(chain1.get("accessed_by")) == "user-B",
          "chain=%r" % (chain1,))
    check("case1c FIRING: attack_path_hint reads as a PROVEN create->access chain (not marker-diff)",
          any("PROVEN create->access chain" in (p.attack_path_hint or "") for p in proven1),
          "hints=%r" % ([p.attack_path_hint for p in proven1],))

    # ── CASE 1b: the ledger file was auto-populated by re-mining (no manual register_object) ────────
    reg1 = ad._object_registry.load_registry(d1)
    rec_A = ad._object_registry.lookup(reg1, "A")
    check("case1d ledger auto-populated: object_registry.json physically written by re-mining",
          os.path.isfile(os.path.join(d1, "object_registry.json")))
    check("case1e ledger auto-populated: record 'A' present, owner='user-A', 0 manual registrations",
          isinstance(rec_A, dict) and str(rec_A.get("owner")) == "user-A"
          and str(rec_A.get("created_by")) == "user-A", "rec=%r" % (rec_A,))

    # ── CASE 2: NEGATIVE self-access — accessor IS the owner -> no fabricated chain ─────────────────
    d2 = _fresh_dir("self"); _TMP_DIRS.append(d2)
    proven2 = ad.provenance_from_traffic([CREATE_A, ACCESS_A_SELF], d2)
    check("case2 NEGATIVE self-access: owner reading own object -> NO proven chain",
          proven2 == [], "got=%r" % ([(p.dclass, (p.evidence or {}).get("provenance_chain"))
                                      for p in proven2],))

    # ── CASE 3: NEGATIVE no-create — access without a recorded create fabricates nothing ────────────
    d3 = _fresh_dir("nocreate"); _TMP_DIRS.append(d3)
    proven3 = ad.provenance_from_traffic([ACCESS_A_FOREIGN], d3)
    reg3 = ad._object_registry.load_registry(d3)
    check("case3a NEGATIVE no-create: foreign access with no create-event -> empty (no fabrication)",
          proven3 == [], "got=%r" % (proven3,))
    check("case3b NEGATIVE no-create: ledger stays empty (no record 'A')",
          ad._object_registry.lookup(reg3, "A") is None and not reg3.get("records"),
          "records=%r" % (reg3.get("records"),))

    # ── CASE 4: reuse — traffic_archive.open_archive().record() -> remine by PATH ───────────────────
    shutil.rmtree(os.path.join(SESSIONS_DIR, _ARCH_SLUG), ignore_errors=True)
    arch = ta.open_archive({"slug": _ARCH_SLUG, "in_scope": True}, live=False)
    check("case4a archive opened offline (live=False, MANUAL, writable)", arch.ok and arch.path,
          "arch=%r" % (arch,))
    arch.record(CREATE_A["request"], CREATE_A["response"], meta=CREATE_A["meta"])
    arch.record(ACCESS_A_FOREIGN["request"], ACCESS_A_FOREIGN["response"], meta=ACCESS_A_FOREIGN["meta"])
    d4 = _fresh_dir("path"); _TMP_DIRS.append(d4)
    proven4 = ad.provenance_from_traffic(arch.path, d4)   # PATH -> traffic_archive.remine round-trip
    check("case4b reuse: re-mining the JSONL archive by PATH still proves the chain",
          len(proven4) >= 1 and all((p.evidence or {}).get("provenance_backed") for p in proven4),
          "got=%r" % ([(p.dclass, (p.evidence or {}).get("provenance_backed")) for p in proven4],))

    # ── CASE 5: actor-from-header fallback (no meta actor) ──────────────────────────────────────────
    d5 = _fresh_dir("hdr"); _TMP_DIRS.append(d5)
    create_h = {"request": {"method": "POST", "url": "https://api.example.com/objects",
                            "headers": {"Authorization": "tok-A"}},
                "response": {"status": 201, "body": {"id": "H", "owner_id": "tok-A"}}, "ts": 1.0}
    access_h = {"request": {"method": "GET", "url": "https://api.example.com/objects/H",
                            "headers": {"Authorization": "tok-B"}},
                "response": {"status": 200, "body": {"owner_id": "tok-A"}}, "ts": 2.0}
    proven5 = ad.provenance_from_traffic([create_h, access_h], d5)
    chain5 = _chain_of(proven5)
    check("case5 actor-from-header: Authorization header identity proves create(tok-A)->access(tok-B)",
          bool(chain5) and str(chain5.get("created_by")) == "tok-A"
          and str(chain5.get("accessed_by")) == "tok-B", "chain=%r" % (chain5,))

    # ── CASE 6: create-id extraction variants (Location header + PUT url id) ─────────────────────────
    d6 = _fresh_dir("idvar"); _TMP_DIRS.append(d6)
    create_loc = {"request": {"method": "POST", "url": "https://api.example.com/objects", "headers": {}},
                  "response": {"status": 201, "headers": {"Location": "/objects/C"},
                               "body": {"owner_id": "user-A"}}, "meta": {"actor": "user-A"}, "ts": 1.0}
    access_c = {"request": {"method": "GET", "url": "https://api.example.com/objects/C", "headers": {}},
                "response": {"status": 200, "body": {"owner_id": "user-A"}},
                "meta": {"actor": "user-B"}, "ts": 2.0}
    create_put = {"request": {"method": "PUT", "url": "https://api.example.com/objects/B", "headers": {}},
                  "response": {"status": 200, "body": {"owner_id": "user-A"}},
                  "meta": {"actor": "user-A"}, "ts": 3.0}
    access_b = {"request": {"method": "GET", "url": "https://api.example.com/objects/B", "headers": {}},
                "response": {"status": 200, "body": {"owner_id": "user-A"}},
                "meta": {"actor": "user-B"}, "ts": 4.0}
    proven6 = ad.provenance_from_traffic([create_loc, access_c, create_put, access_b], d6)
    proven6_ids = sorted(str((p.evidence or {}).get("provenance_chain", {}).get("object_id"))
                         for p in proven6 if (p.evidence or {}).get("provenance_backed"))
    check("case6 create-id extraction: Location-header ('C') and PUT-url-id ('B') both proven",
          proven6_ids == ["B", "C"], "ids=%r" % (proven6_ids,))

    # ── CASE 7: anti-FP — leaked owner disagrees with registered owner -> not proven ────────────────
    d7 = _fresh_dir("antifp"); _TMP_DIRS.append(d7)
    access_mismatch = {"request": {"method": "GET", "url": "https://api.example.com/objects/A",
                                   "headers": {}},
                       "response": {"status": 200, "body": {"owner_id": "user-Q", "balance": 999}},
                       "meta": {"actor": "user-B"}, "ts": 2.0}
    proven7 = ad.provenance_from_traffic([CREATE_A, access_mismatch], d7)
    check("case7 anti-FP: leaked owner ('user-Q') != registered owner ('user-A') -> NO proven chain",
          proven7 == [], "got=%r" % ([(p.evidence or {}).get("provenance_chain") for p in proven7],))

finally:
    for d in _TMP_DIRS:
        shutil.rmtree(d, ignore_errors=True)
    shutil.rmtree(os.path.join(SESSIONS_DIR, _ARCH_SLUG), ignore_errors=True)


print("=== PROVENANCE_FROM_TRAFFIC SELFTEST (Plan 9, Task T10) ===")
ok = sum(1 for _, p, _ in results if p)
for n, p, d in results:
    print(("  [PASS] " if p else "  [FAIL] ") + n + (("  -- " + str(d)) if d and not p else ""))
print("\n%d/%d green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
