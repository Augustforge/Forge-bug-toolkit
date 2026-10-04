# -*- coding: utf-8 -*-
"""Selftest for traffic_archive.py (Plan 9 Task 9, Tier D). Offline-only, mock exchange, no live network.

Proves it ACTUALLY FIRES (not just the absence of false positives):
  (1) the offline archive writes records under sessions/{target}/traffic/<name>.jsonl (the right PLACE);
  (2) re-mine/read-back returns ALL written records (independent-of-probe re-mining);
  (2b) the predicate filter for re-mining works (focused re-mining pass);
  (3) opsec fail-CLOSED ACTUALLY FIRES: live=True with bad opsec -> BLOCKED (ok=False, path=None,
      mode=MANUAL) AND record() writes NOTHING (no file / 0 lines) -- no live capture at all;
  (4) live=True with good opsec -> PASSES (ok=True, mode=AUTO), record writes, opsec audit recorded;
  (5) live without a target slug -> opsec blocks (we do not make up a slug/in_scope);
  (6) traversal/absolute `name` is dropped (local-session-only);
  (7) fail-open on non-security errors: no slug -> ok=False not a crash; remine on a missing
      file -> [] not a crash; broken input to record does not crash the flow;
  (8) to_har produces a HAR-compatible log from the records.
"""
# Ensure UTF-8 stdout so the summary (arrows/checks) prints on any console (Windows cp1251, etc.).
import sys as _utf8_sys
try:
    _utf8_sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import os
import sys
import json
import shutil
import tempfile
import importlib.util

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOLKIT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
SESSIONS_DIR = os.path.join(_TOOLKIT_ROOT, "sessions")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


ta = _load("traffic_archive", os.path.join(_HERE, "traffic_archive.py"))

results = []


def check(n, c, d=""):
    results.append((n, bool(c), d))


def _good_opsec():
    # web2 profile: all common + web2 checks green
    return {
        "vpn_active": True,
        "incognito": True,
        "not_logged_main": True,
        "rate_limit": "5/s",
        "objective": "comprehensive",
        "hosts_all_in_scope": True,
        "test_accounts": ["attacker@test", "victim@test"],
    }


def _bad_opsec():
    # vpn/incognito/not_logged_main missing -> fail-closed block
    return {
        "rate_limit": "5/s",
        "objective": "comprehensive",
        "hosts_all_in_scope": True,
        "test_accounts": ["attacker@test", "victim@test"],
    }


TARGET_SLUG = "p9t9-selftest-target"


# --- mock exchange: generates (request, response) pairs as if captured from a live target ---
def _mock_exchange(i):
    req = {"method": "GET", "url": "https://api.mock.exchange/v2/order/%d" % i,
           "headers": {"authorization": "Bearer TOK-%d" % i}}
    resp = {"status": 200 if i % 2 == 0 else 403,
            "headers": {"content-type": "application/json"},
            "body": json.dumps({"order_id": i, "owner": "acct-%d" % i})}
    return req, resp


def main():
    good_target = {"slug": TARGET_SLUG, "in_scope": True}
    sess = os.path.join(SESSIONS_DIR, TARGET_SLUG)
    created_sess = not os.path.isdir(sess)

    try:
        # ---- (1)(2) offline record + read-back ----
        arc = ta.open_archive(good_target, live=False, name="traffic")
        check("(1a) offline open ok=True, mode=MANUAL", arc.ok is True and arc.mode == "MANUAL", repr(arc))
        expect_path = os.path.abspath(os.path.join(sess, "traffic", "traffic.jsonl"))
        check("(1b) path resolved under sessions/{target}/traffic/",
              arc.path == expect_path, repr(arc.path))
        wrote = 0
        for i in range(5):
            req, resp = _mock_exchange(i)
            if arc.record(req, resp, meta={"seq": i}):
                wrote += 1
        check("(1c) 5 records written", wrote == 5, "wrote=%d" % wrote)
        check("(1d) the file actually exists on disk under sessions/{target}/", os.path.isfile(arc.path), repr(arc.path))

        mined = ta.remine(arc.path)
        check("(2) re-mine returns all 5 records", len(mined) == 5, "len=%d" % len(mined))
        check("(2a) a record carries request+response+meta",
              mined[0].get("request", {}).get("method") == "GET"
              and mined[0].get("response", {}).get("status") == 200
              and mined[0].get("meta", {}).get("seq") == 0,
              repr(mined[0]))
        # ---- (2b) focused re-mining predicate ----
        forbidden = ta.remine(arc.path, predicate=lambda r: r.get("response", {}).get("status") == 403)
        check("(2b) predicate filter (403 only) -> 2 records", len(forbidden) == 2, "len=%d" % len(forbidden))

        # ---- (3) opsec fail-CLOSED: live + bad opsec -> BLOCKED, writes NOTHING ----
        blk = ta.open_archive(good_target, opsec_config=_bad_opsec(), live=True, profile="web2",
                              name="blocked")
        check("(3a) live+bad opsec -> ok=False", blk.ok is False, repr(blk))
        check("(3b) live block -> path=None (nowhere to write)", blk.path is None, repr(blk.path))
        check("(3c) live block -> mode=MANUAL", blk.mode == "MANUAL", blk.mode)
        check("(3d) the live block references opsec", any("opsec" in e for e in blk.errors), repr(blk.errors))
        req, resp = _mock_exchange(99)
        rec_ok = blk.record(req, resp)
        check("(3e) record on a blocked archive -> False (fail-closed)", rec_ok is False, repr(rec_ok))
        blocked_file = os.path.join(sess, "traffic", "blocked.jsonl")
        check("(3f) live block: no capture file was created", not os.path.isfile(blocked_file), blocked_file)

        # ---- (4) opsec pass: live + good opsec -> PASSES, writes, audit recorded ----
        pas = ta.open_archive(good_target, opsec_config=_good_opsec(), live=True, profile="web2",
                              name="live")
        check("(4a) live+good opsec -> ok=True, mode=AUTO", pas.ok is True and pas.mode == "AUTO", repr(pas))
        req, resp = _mock_exchange(7)
        check("(4b) record on a passed live archive writes", pas.record(req, resp) is True)
        check("(4c) live file on disk", os.path.isfile(pas.path), repr(pas.path))
        check("(4d) opsec audit recorded (the gate passed fully)",
              os.path.isfile(os.path.join(sess, "opsec_preflight.json")))

        # ---- (5) live without a target slug -> opsec blocks ----
        notgt = ta.open_archive({"in_scope": True}, opsec_config=_good_opsec(), live=True, profile="web2")
        check("(5) live without a slug -> BLOCKED (ok=False, path=None)",
              notgt.ok is False and notgt.path is None, repr(notgt))

        # ---- (6) traversal / absolute name dropped ----
        ev1 = ta.open_archive(good_target, live=False, name="../../../../etc/passwd")
        check("(6a) traversal name -> ok=False, path=None",
              ev1.ok is False and ev1.path is None, repr(ev1))
        ev2 = ta.open_archive(good_target, live=False, name="C:/Windows/win.ini")
        check("(6b) absolute name -> ok=False, path=None",
              ev2.ok is False and ev2.path is None, repr(ev2))

        # ---- (7) fail-open on non-security errors ----
        nos = ta.open_archive({}, live=False)  # no slug, offline
        check("(7a) offline without a slug -> ok=False, not a crash", nos.ok is False, repr(nos))
        missing = ta.remine(os.path.join(sess, "traffic", "does_not_exist.jsonl"))
        check("(7b) remine of a missing file -> [] not a crash", missing == [], repr(missing))
        # broken input to record does not crash (fail-open): a non-serializable meta
        class _Weird(object):
            pass
        rec_weird = arc.record({"url": "x"}, {"status": 1}, meta={"bad": _Weird()})
        check("(7c) non-serializable meta -> record does not crash (fail-open)", rec_weird in (True, False),
              repr(rec_weird))

        # ---- (8) HAR conversion ----
        har = ta.to_har(mined)
        entries = har.get("log", {}).get("entries")
        check("(8) to_har -> a HAR log with entries", isinstance(entries, list) and len(entries) == 5,
              repr(type(entries)))
        check("(8a) a HAR entry carries request.method/url",
              entries[0].get("request", {}).get("method") == "GET"
              and entries[0].get("request", {}).get("url", "").startswith("https://"),
              repr(entries[0].get("request")))

    finally:
        if created_sess:
            shutil.rmtree(sess, ignore_errors=True)
        else:
            # clean up only our own artifacts
            shutil.rmtree(os.path.join(sess, "traffic"), ignore_errors=True)
            for f in ("opsec_preflight.json",):
                try:
                    os.remove(os.path.join(sess, f))
                except OSError:
                    pass

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    for name, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        line = "  [%s] %s" % (mark, name)
        if not ok and detail:
            line += "  -- " + detail
        print(line)
    print("\n%d/%d asserts pass" % (passed, total))
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
