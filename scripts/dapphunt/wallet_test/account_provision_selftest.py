# -*- coding: utf-8 -*-
"""Selftest for account_provision.py (Plan 9 Task 8). Offline-only, mock creds-config.

Proves TRIGGERING (not just the absence of false positives):
  (1) load_creds_config reads a mock config with >=2 roles -> attacker+victim are actually loaded;
  (2) session_path resolves under sessions/{target}/ and cookies are actually read from disk;
  (3) traversal/absolute session_path is DISCARDED (local-session-only);
  (4) missing-role: a config with 1 role -> ok=False, accounts not handed out;
  (5) opsec fail-CLOSED ACTUALLY FIRES -- live=True with a bad opsec-config -> BLOCK (ok=False,
      accounts empty, mode=MANUAL), with a good opsec-config -> PASS (ok=True, mode=AUTO);
  (6) live run without a target dict (no in_scope) -> opsec blocks (we do not invent in_scope);
  (7) test_accounts is auto-filled from roles if the operator did not set it;
  (8) live=False (offline) -> opsec is NOT run, accounts handed out with mode=MANUAL;
  (9) session_bundle hands out creds+cookies for authz-diff exposure.
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


ap = _load("account_provision", os.path.join(_HERE, "account_provision.py"))

results = []


def check(n, c, d=""):
    results.append((n, bool(c), d))


# --- good opsec-config: all web2 checks green (provision fills in >=2 test_accounts) ---
def _good_opsec():
    return {
        "vpn_active": True,
        "incognito": True,
        "not_logged_main": True,
        "rate_limit": "5/s",
        "objective": "comprehensive",
        "hosts_all_in_scope": True,
    }


def _bad_opsec():
    # vpn/incognito/not_logged_main missing -> fail-closed block
    return {
        "rate_limit": "5/s",
        "objective": "comprehensive",
        "hosts_all_in_scope": True,
    }


TARGET_SLUG = "p9t8-selftest-target"


_cfg_counter = [0]


def _write_config(tmp, roles, target=TARGET_SLUG):
    cfg = {"target": target, "roles": roles}
    _cfg_counter[0] += 1
    p = os.path.join(tmp, "creds_%d.json" % _cfg_counter[0])
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    return p


def main():
    tmp = tempfile.mkdtemp(prefix="ap_selftest_")
    # target's session folder (where provisioning resolves cookies) -- create it and put the attacker's mock cookies in
    sess = os.path.join(SESSIONS_DIR, TARGET_SLUG)
    created_sess = not os.path.isdir(sess)
    os.makedirs(sess, exist_ok=True)
    atk_cookie = os.path.join(sess, "attacker.cookies.json")
    with open(atk_cookie, "w", encoding="utf-8") as f:
        json.dump([{"name": "sid", "value": "ATK-SESSION"}], f)

    try:
        # ---- (1)(2) two-role config, attacker cookies on disk ----
        two_roles = {
            "attacker": {"credentials": {"user": "atk@test", "pw": "x"},
                         "session_path": "attacker.cookies.json"},
            "victim": {"credentials": {"user": "vic@test", "pw": "y"}},
        }
        cfg_path = _write_config(tmp, two_roles)
        slug, accounts, errors = ap.load_creds_config(cfg_path)
        check("(1) >=2 roles loaded (attacker+victim)",
              set(accounts.keys()) == {"attacker", "victim"}, repr(sorted(accounts)))
        check("(2) attacker cookies actually read from disk",
              accounts.get("attacker") is not None
              and accounts["attacker"].cookies == [{"name": "sid", "value": "ATK-SESSION"}],
              repr(accounts["attacker"].cookies if accounts.get("attacker") else None))
        check("(2b) attacker.session_path resolved under sessions/{target}/",
              accounts["attacker"].session_path == os.path.abspath(atk_cookie),
              repr(accounts["attacker"].session_path))

        # ---- (3) traversal / absolute session_path is discarded ----
        evil_roles = {
            "attacker": {"credentials": {"user": "a"},
                         "session_path": "../../../../etc/passwd"},
            "victim": {"credentials": {"user": "v"},
                       "session_path": "C:/Windows/win.ini"},
        }
        cfg_evil = _write_config(tmp, evil_roles)
        _, ev_accounts, ev_errors = ap.load_creds_config(cfg_evil)
        check("(3) traversal session_path discarded (attacker)",
              ev_accounts["attacker"].session_path is None, repr(ev_accounts["attacker"].session_path))
        check("(3b) absolute session_path discarded (victim)",
              ev_accounts["victim"].session_path is None, repr(ev_accounts["victim"].session_path))
        check("(3c) discard logged in errors", len(ev_errors) >= 2, repr(ev_errors))

        # ---- (4) missing-role: 1 role -> block ----
        one_role = {"attacker": {"credentials": {"user": "a"}}}
        cfg_one = _write_config(tmp, one_role)
        r_one = ap.provision(cfg_one, live=False)
        check("(4) 1 role -> ok=False (missing-role)", r_one.ok is False, repr(r_one))
        check("(4b) 1 role -> accounts NOT handed out", r_one.accounts == {}, repr(r_one.accounts))
        check("(4c) missing-role logged",
              any(">=2" in e for e in r_one.errors), repr(r_one.errors))

        # ---- (5) opsec fail-CLOSED: FIRES on bad, PASSES on good ----
        good_target = {"slug": TARGET_SLUG, "in_scope": True}
        r_block = ap.provision(cfg_path, target=good_target, opsec_config=_bad_opsec(), live=True)
        check("(5) live + bad opsec -> BLOCK (ok=False)", r_block.ok is False, repr(r_block))
        check("(5b) live block -> accounts empty", r_block.accounts == {}, repr(r_block.accounts))
        check("(5c) live block -> mode=MANUAL", r_block.mode == "MANUAL", r_block.mode)
        check("(5d) live block references opsec", any("opsec" in e for e in r_block.errors),
              repr(r_block.errors))

        r_pass = ap.provision(cfg_path, target=good_target, opsec_config=_good_opsec(), live=True)
        check("(5e) live + good opsec -> PASS (ok=True)", r_pass.ok is True, repr(r_pass))
        check("(5f) live pass -> mode=AUTO", r_pass.mode == "AUTO", r_pass.mode)
        check("(5g) live pass -> both roles handed out",
              set(r_pass.accounts.keys()) == {"attacker", "victim"}, repr(sorted(r_pass.accounts)))
        # opsec audit file actually written (proof that the gate passed fully)
        check("(5h) opsec audit file written",
              os.path.isfile(os.path.join(sess, "opsec_preflight.json")))

        # ---- (6) live without target dict -> opsec blocks (we do not invent in_scope) ----
        r_notgt = ap.provision(cfg_path, target=None, opsec_config=_good_opsec(), live=True)
        check("(6) live without target dict -> BLOCK (in_scope not invented)",
              r_notgt.ok is False and r_notgt.mode == "MANUAL", repr(r_notgt))

        # ---- (7) test_accounts auto-filled from roles (bad opsec, but with explicit good
        #          common checks; we remove test_accounts and check that provision filled it in) ----
        opsec_no_ta = _good_opsec()  # test_accounts not set at all
        r_auto = ap.provision(cfg_path, target=good_target, opsec_config=opsec_no_ta, live=True)
        check("(7) test_accounts auto-filled from roles -> opsec passed", r_auto.ok is True, repr(r_auto))
        # ---- (7b) prove it is exactly the auto-fill: 1 role fails opsec test_accounts
        #      (we cannot bypass the missing-role guard -- it comes earlier; instead we check opsec directly) ----
        opsec_mod = ap._load_opsec()
        one_ta_cfg = _good_opsec()
        one_ta_cfg["test_accounts"] = ["only-one"]
        r_ota = opsec_mod.preflight("web2", good_target, one_ta_cfg)
        check("(7c) sanity: opsec ITSELF fails on <2 test_accounts", r_ota.ok is False, repr(r_ota))

        # ---- (8) live=False offline -> opsec is NOT run, accounts handed out as MANUAL ----
        r_off = ap.provision(cfg_path, live=False)
        check("(8) offline -> ok=True, mode=MANUAL, roles handed out",
              r_off.ok is True and r_off.mode == "MANUAL"
              and set(r_off.accounts.keys()) == {"attacker", "victim"}, repr(r_off))

        # ---- (9) session_bundle exposure ----
        bundle = ap.session_bundle(r_off.accounts)
        check("(9) session_bundle hands out creds+cookies for authz-diff",
              bundle["attacker"]["credentials"] == {"user": "atk@test", "pw": "x"}
              and bundle["attacker"]["cookies"] == [{"name": "sid", "value": "ATK-SESSION"}]
              and bundle["victim"]["cookies"] is None,
              repr(bundle))

        # ---- (10) broken config fail-open (not a crash) ----
        bad_path = os.path.join(tmp, "nope.json")
        r_bad = ap.provision(bad_path, live=False)
        check("(10) missing config -> ok=False, not a crash", r_bad.ok is False, repr(r_bad))

    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        # clean up the selftest's session artifacts
        try:
            os.remove(atk_cookie)
        except OSError:
            pass
        opf = os.path.join(sess, "opsec_preflight.json")
        try:
            os.remove(opf)
        except OSError:
            pass
        if created_sess:
            shutil.rmtree(sess, ignore_errors=True)

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
