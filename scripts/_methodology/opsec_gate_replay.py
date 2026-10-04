# -*- coding: utf-8 -*-
"""OPSEC-preflight gate replay (§4.3, §33, Plan 3 Task 2). Proves: the common checks (vpn/incognito/
not_logged_main/in_scope/rate_limit/objective) + the web3 branch (burner case-insensitive/balance<=cap) +
the web2 branch (>=2 test_accounts/hosts_all_in_scope) keep ok=False on any violation; fail-CLOSED on
non-dict config/target and on a missing key does NOT raise an exception outward; on ok=True a json
audit is written to sessions/{slug}/opsec_preflight.json; the real sessions/ are untouched (unique test slug,
cleaned up in finally)."""
import os, sys, json, shutil, importlib.util

ROOT = os.getcwd()
while ROOT and not os.path.isdir(os.path.join(ROOT, "sessions")):
    nxt = os.path.dirname(ROOT)
    if nxt == ROOT: break
    ROOT = nxt
MODPATH = os.path.join(ROOT, "scripts", "dapphunt", "wallet_test", "opsec_preflight.py")
SESSIONS = os.path.join(ROOT, "sessions")

def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

mod = _load("opsec_preflight", MODPATH)

# ISOLATION from the real bug-bounty-toolkit/opsec_baseline.json: point load_baseline() at a
# guaranteed-nonexistent path -> baseline is empty -> cases 1-13 behave exactly as before the baseline
# feature (full config, nothing mixed in). Cases 14* use THEIR OWN temporary baseline.
os.environ["OPSEC_BASELINE_PATH"] = os.path.join(ROOT, "_no_such_baseline_ZZ.json")

SLUG = "opsectest-Q7"          # unique slug -> does not collide with any real target session
SESS = os.path.join(SESSIONS, SLUG)
AUDIT = os.path.join(SESS, "opsec_preflight.json")

CANON_BURNER = "0x000000000000000000000000000000000000dEaD"

results = []
def check(n, c, d=""):
    results.append((n, bool(c), d))

def base_target():
    return {"slug": SLUG, "host": "test.example.com", "in_scope": True}

def base_web3_config():
    return {
        "vpn_active": True, "incognito": True, "not_logged_main": True,
        "rate_limit": 5, "objective": "comprehensive",
        "wallet_address": CANON_BURNER, "balance": 2, "balance_cap": 10,
    }

def base_web2_config():
    return {
        "vpn_active": True, "incognito": True, "not_logged_main": True,
        "rate_limit": 5, "objective": "comprehensive",
        "test_accounts": ["acct-a", "acct-b"], "hosts_all_in_scope": True,
    }

def call_no_crash(profile, target, config):
    """Calls preflight and catches any exception -- for fail-closed cases (case7)."""
    try:
        return mod.preflight(profile, target, config), False
    except Exception:
        return None, True

try:
    # Case 1 -- web3 all-pass -> ok True, mode AUTO, audit file created.
    r1 = mod.preflight("web3", base_target(), base_web3_config())
    check("case1 web3 all-pass: ok is True", r1.ok is True, repr(getattr(r1, "failed_checks", None)))
    check("case1 web3 all-pass: mode == AUTO", r1.mode == "AUTO", repr(getattr(r1, "mode", None)))
    check("case1 web3 all-pass: failed_checks is empty", len(r1.failed_checks) == 0, repr(r1.failed_checks))
    check("case1 web3 all-pass: audit file sessions/{slug}/opsec_preflight.json created", os.path.isfile(AUDIT))
    if os.path.isfile(AUDIT):
        with open(AUDIT, "r", encoding="utf-8") as f:
            data = json.load(f)
        check("case1 audit: contains ts/profile/passed_checks/objective",
              all(k in data for k in ("ts", "profile", "passed_checks", "objective")), repr(data))
        check("case1 audit: profile == web3", data.get("profile") == "web3", repr(data.get("profile")))
        check("case1 audit: objective == comprehensive", data.get("objective") == "comprehensive")

    # Case 2 -- burner != canonical -> block, the reason mentions burner.
    cfg2 = base_web3_config(); cfg2["wallet_address"] = "0x0000000000000000000000000000000000dEaD"
    r2 = mod.preflight("web3", base_target(), cfg2)
    check("case2 non-burner address: ok is False", r2.ok is False)
    check("case2 non-burner address: reason is about burner",
          any("burner" in m.lower() for m in r2.failed_checks), repr(r2.failed_checks))

    # Prove "audit is NOT written on non-ok" explicitly, not just by reading the code: remove the file left
    # by case1, run one more failing case on the SAME slug, make sure the file did not come back.
    if os.path.isfile(AUDIT):
        os.remove(AUDIT)
    mod.preflight("web3", base_target(), cfg2)
    check("audit is NOT written on ok=False (file did not reappear after one more failing call)",
          not os.path.isfile(AUDIT))

    # Case 3 -- web2 without test accounts (test_accounts=[]) -> block.
    cfg3 = base_web2_config(); cfg3["test_accounts"] = []
    r3 = mod.preflight("web2", base_target(), cfg3)
    check("case3 web2 test_accounts=[] -> ok is False", r3.ok is False, repr(r3.failed_checks))

    # Case 4 -- rate_limit missing / == 0 -> block ("rate-limit").
    cfg4a = base_web3_config(); del cfg4a["rate_limit"]
    r4a = mod.preflight("web3", base_target(), cfg4a)
    check("case4a rate_limit missing -> ok is False", r4a.ok is False)
    check("case4a reason is about rate-limit", any("rate" in m.lower() for m in r4a.failed_checks), repr(r4a.failed_checks))

    cfg4b = base_web3_config(); cfg4b["rate_limit"] = 0
    r4b = mod.preflight("web3", base_target(), cfg4b)
    check("case4b rate_limit=0 -> ok is False", r4b.ok is False)
    check("case4b reason is about rate-limit", any("rate" in m.lower() for m in r4b.failed_checks), repr(r4b.failed_checks))

    # Case 5 -- vpn_active=False -> block.
    cfg5 = base_web3_config(); cfg5["vpn_active"] = False
    r5 = mod.preflight("web3", base_target(), cfg5)
    check("case5 vpn_active=False -> ok is False", r5.ok is False, repr(r5.failed_checks))

    # Case 6 -- not_logged_main=False (logged in to main) -> block.
    cfg6 = base_web3_config(); cfg6["not_logged_main"] = False
    r6 = mod.preflight("web3", base_target(), cfg6)
    check("case6 not_logged_main=False -> ok is False", r6.ok is False, repr(r6.failed_checks))

    # Case 7 -- fail-CLOSED: missing key / non-dict config / non-dict target -> ok False,
    # WITHOUT an exception outward (the heart of Task 2 -- first prove it does not crash, then that it blocks).
    cfg7a = base_web3_config(); del cfg7a["vpn_active"]
    r7a, crashed7a = call_no_crash("web3", base_target(), cfg7a)
    check("case7a config without key vpn_active -> does NOT crash", not crashed7a)
    check("case7a config without key vpn_active -> ok is False", (r7a is not None) and (r7a.ok is False))

    r7b, crashed7b = call_no_crash("web3", base_target(), None)
    check("case7b config=None (not a dict) -> does NOT crash", not crashed7b)
    check("case7b config=None (not a dict) -> ok is False", (r7b is not None) and (r7b.ok is False))

    r7c, crashed7c = call_no_crash("web3", base_target(), "not-a-dict-config")
    check("case7c config=string (not a dict) -> does NOT crash", not crashed7c)
    check("case7c config=string (not a dict) -> ok is False", (r7c is not None) and (r7c.ok is False))

    r7d, crashed7d = call_no_crash("web3", None, base_web3_config())
    check("case7d target=None (not a dict) -> does NOT crash", not crashed7d)
    check("case7d target=None (not a dict) -> ok is False", (r7d is not None) and (r7d.ok is False))

    r7e, crashed7e = call_no_crash("web3", [1, 2], {"whatever": 1})
    check("case7e target=list AND config without the needed keys -> does NOT crash", not crashed7e)
    check("case7e target=list AND config without the needed keys -> ok is False", (r7e is not None) and (r7e.ok is False))

    # Fail-closed on an unknown profile (the third case from the §Fail-CLOSED behavior list).
    r7f, crashed7f = call_no_crash("mobile", base_target(), base_web3_config())
    check("case7f invalid profile ('mobile') -> does NOT crash", not crashed7f)
    check("case7f invalid profile ('mobile') -> ok is False", (r7f is not None) and (r7f.ok is False))

    # Case 8 -- invalid objective -> block.
    cfg8 = base_web3_config(); cfg8["objective"] = "aggressive"
    r8 = mod.preflight("web3", base_target(), cfg8)
    check("case8 objective='aggressive' -> ok is False", r8.ok is False, repr(r8.failed_checks))

    # Case 9 (bonus, required by the numbered list of the brief) -- web3 balance > cap -> block.
    cfg9 = base_web3_config(); cfg9["balance"] = 20; cfg9["balance_cap"] = 10
    r9 = mod.preflight("web3", base_target(), cfg9)
    check("case9 balance(20) > balance_cap(10) -> ok is False", r9.ok is False)
    check("case9 reason is about cap", any("cap" in m.lower() for m in r9.failed_checks), repr(r9.failed_checks))

    # Case 10 -- case-insensitive burner: the same address in UPPER/lower case -> still pass.
    cfg10u = base_web3_config(); cfg10u["wallet_address"] = CANON_BURNER.upper()
    r10u = mod.preflight("web3", base_target(), cfg10u)
    check("case10 burner UPPERCASE -> ok is True (case does not break it)", r10u.ok is True, repr(getattr(r10u, "failed_checks", None)))

    cfg10l = base_web3_config(); cfg10l["wallet_address"] = CANON_BURNER.lower()
    r10l = mod.preflight("web3", base_target(), cfg10l)
    check("case10 burner lowercase -> ok is True (case does not break it)", r10l.ok is True, repr(getattr(r10l, "failed_checks", None)))

    # Extra: web2 all-pass mirrors case1, proves the second branch also really writes audit/AUTO.
    r11 = mod.preflight("web2", base_target(), base_web2_config())
    check("case11 web2 all-pass: ok is True", r11.ok is True, repr(getattr(r11, "failed_checks", None)))
    check("case11 web2 all-pass: mode == AUTO", r11.mode == "AUTO")

    # Extra: hosts_all_in_scope=False -> block (second half of the web2 branch, not covered by case3).
    cfg12 = base_web2_config(); cfg12["hosts_all_in_scope"] = False
    r12 = mod.preflight("web2", base_target(), cfg12)
    check("case12 web2 hosts_all_in_scope=False -> ok is False", r12.ok is False, repr(r12.failed_checks))

    # Extra: target.in_scope=False -> block (a common check, not separately covered by the other cases).
    cfg13 = base_web3_config()
    t13 = base_target(); t13["in_scope"] = False
    r13 = mod.preflight("web3", t13, cfg13)
    check("case13 target.in_scope=False -> ok is False", r13.ok is False, repr(r13.failed_checks))

    # ---- Case 14 -- OPSEC baseline (operator: "approved a priori": static signed off once, no re-asking) ----
    # baseline holds the environment statics: vpn/incognito/not_logged_main + burner + cap + rate_limit +
    # objective. It does NOT hold per-target/fact data (balance, in_scope, test_accounts). Checked via
    # _baseline= (direct dict injection) AND via a real env file (that the path is read).
    BASELINE = {
        "vpn_active": True, "incognito": True, "not_logged_main": True,
        "rate_limit": "2rps", "objective": "comprehensive",
        "wallet_address": CANON_BURNER, "balance_cap": 10,
    }

    # 14a -- MAIN: baseline covers the statics, per-call supplies ONLY the fact (balance) -> AUTO without
    # any manual question. This is exactly "does not ask about VPN/incognito/burner every time".
    r14a = mod.preflight("web3", base_target(), {"balance": 2}, _baseline=BASELINE)
    check("case14a baseline+per-call balance -> ok True (statics are not asked)",
          r14a.ok is True, repr(getattr(r14a, "failed_checks", None)))
    check("case14a mode == AUTO", getattr(r14a, "mode", None) == "AUTO")

    # 14b -- fail-closed INTACT: baseline present, but per-call balance > cap -> MANUAL (top-up triggers).
    r14b = mod.preflight("web3", base_target(), {"balance": 999}, _baseline=BASELINE)
    check("case14b baseline + balance(999)>cap(10) -> ok is False (top-up)", r14b.ok is False,
          repr(r14b.failed_checks))

    # 14c -- fail-closed INTACT: baseline present, but per-call did NOT supply balance -> MANUAL (the on-chain
    # fact is needed, baseline does not fake it).
    r14c = mod.preflight("web3", base_target(), {}, _baseline=BASELINE)
    check("case14c baseline without per-call balance -> ok is False (fact is not from a file)", r14c.ok is False,
          repr(r14c.failed_checks))

    # 14d -- fail-closed INTACT: baseline empty (no file) + minimal per-call -> all statics fail.
    r14d = mod.preflight("web3", base_target(), {"balance": 2}, _baseline={})
    check("case14d empty baseline -> ok is False (statics not covered)", r14d.ok is False,
          repr(r14d.failed_checks))

    # 14e -- override: baseline says vpn True, per-call EXPLICITLY vpn False -> per-call wins,
    # MANUAL. Baseline cannot silence a VPN that is actually off.
    r14e = mod.preflight("web3", base_target(), {"balance": 2, "vpn_active": False}, _baseline=BASELINE)
    check("case14e per-call vpn_active=False overrides baseline -> ok is False", r14e.ok is False,
          repr(r14e.failed_checks))

    # 14f -- load_baseline() really reads the env-specified file (not only _baseline=): write a temp
    # baseline, point env at it, a default preflight call (without _baseline) must take the statics from there.
    _bl_path = os.path.join(SESSIONS, "_baseline_14f.json")
    _saved_env = os.environ.get("OPSEC_BASELINE_PATH")
    try:
        os.makedirs(SESSIONS, exist_ok=True)
        with open(_bl_path, "w", encoding="utf-8") as f:
            json.dump(BASELINE, f)
        os.environ["OPSEC_BASELINE_PATH"] = _bl_path
        loaded = mod.load_baseline()
        check("case14f load_baseline() reads the env file (dict with burner)",
              isinstance(loaded, dict) and loaded.get("wallet_address") == CANON_BURNER, repr(loaded))
        r14f = mod.preflight("web3", base_target(), {"balance": 2})
        check("case14f preflight without _baseline takes statics from the env file -> ok True", r14f.ok is True,
              repr(getattr(r14f, "failed_checks", None)))
    finally:
        os.environ["OPSEC_BASELINE_PATH"] = _saved_env or os.path.join(ROOT, "_no_such_baseline_ZZ.json")
        if os.path.isfile(_bl_path):
            os.remove(_bl_path)

    # 14g -- a broken baseline file -> load_baseline() returns {} (fail-safe, not a crash).
    _bad_path = os.path.join(SESSIONS, "_baseline_bad_14g.json")
    try:
        os.makedirs(SESSIONS, exist_ok=True)
        with open(_bad_path, "w", encoding="utf-8") as f:
            f.write("{ this is not json ]]]")
        check("case14g broken JSON -> load_baseline() == {} (fail-safe)",
              mod.load_baseline(_bad_path) == {})
    finally:
        if os.path.isfile(_bad_path):
            os.remove(_bad_path)

finally:
    shutil.rmtree(SESS, ignore_errors=True)

check("cleanup: no sessions/opsectest-* left after the run (real sessions/ untouched)",
      not os.path.isdir(SESS))

print("=== OPSEC PREFLIGHT GATE REPLAY (Plan 3 Task 2, §4.3/§33) ===")
ok = sum(1 for _, p, _ in results if p)
for n, p, d in results:
    print(("  [PASS] " if p else "  [FAIL] ") + n + (("  -- " + d) if d and not p else ""))
print("\n%d/%d green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
