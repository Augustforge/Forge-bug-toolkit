# -*- coding: utf-8 -*-
"""OPSEC preflight gate (§4.3, §33, Plan 3 Task 2) -- a mandatory check BEFORE any launch of the live
browser harness (Playwright), for both profiles (web3 dapphunt / web2 hunt).

Fail-CLOSED (unlike the rest of the FDE plan): safety outweighs hunting. Any ambiguity --
config/target not a dict, a missing key where a bool/value is expected, an invalid profile -- is treated
as a fail (ok=False), and NEVER escapes as an exception. No live network I/O and no
live VPN/incognito detection (unreliable cross-platform) -- they arrive as booleans in config,
the gate only requires them to be True.

preflight(profile, target, config) -> Result:
    Common checks (both profiles): vpn_active/incognito/not_logged_main, target.in_scope, rate_limit,
    objective. web3 branch: burner wallet (case-insensitive) + balance<=balance_cap. web2 branch:
    >=2 test_accounts + hosts_all_in_scope. On ok=True it writes a json audit to
    sessions/{target[slug]}/opsec_preflight.json.
"""

import os
import json
import time


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Canonical burner address (see wallets/burner_evm_001), compared case-insensitively.
BURNER_ADDRESS = "0x000000000000000000000000000000000000dEaD"

ALLOWED_OBJECTIVES = ("quick", "comprehensive", "stealth")
ALLOWED_PROFILES = ("web3", "web2")

# Filename of the operator's persistent OPSEC baseline (kept in the root of , NOT
# committed -- like .env). It holds ONLY static environment facts signed off once: vpn/incognito/
# not_logged_main + burner address + balance_cap + rate_limit + objective default. It does NOT hold per-target
# facts (balance, target.in_scope, test_accounts) -- those are supplied by the caller per-call, and they
# OVERRIDE the baseline on merge. Overridable via env OPSEC_BASELINE_PATH (for isolation in tests).
BASELINE_FILENAME = "opsec_baseline.json"

# The path to sessions/ is derived from the location of THIS file (not from os.getcwd()) -- the module lives
# in scripts/dapphunt/wallet_test/, three levels up = .
# This way the gate does not depend on where it was imported from (see CLAUDE.md on the sessions/ vs CWD confusion).
_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOLKIT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
SESSIONS_DIR = os.path.join(_TOOLKIT_ROOT, "sessions")


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

class Result(object):
    """{ok, failed_checks, mode}. mode = 'AUTO' if ok, otherwise 'MANUAL' (static fallback)."""

    def __init__(self, ok, failed_checks, mode):
        self.ok = ok
        self.failed_checks = failed_checks
        self.mode = mode

    def __repr__(self):
        return "Result(ok=%r, failed_checks=%r, mode=%r)" % (self.ok, self.failed_checks, self.mode)


# ---------------------------------------------------------------------------
# Checks (mutate failed/passed in place -- simpler than collecting and merging several lists)
# ---------------------------------------------------------------------------

def _common_checks(config, target, failed, passed):
    if config.get("vpn_active") is True:
        passed.append("vpn_active")
    else:
        failed.append("VPN/Tor not active")

    if config.get("incognito") is True:
        passed.append("incognito")
    else:
        failed.append("incognito profile not active")

    if config.get("not_logged_main") is True:
        passed.append("not_logged_main")
    else:
        failed.append("logged into main account (Google/Twitter)")

    if target.get("in_scope") is True:
        passed.append("in_scope")
    else:
        failed.append("target not confirmed in-scope")

    if config.get("rate_limit"):
        passed.append("rate_limit")
    else:
        failed.append("rate-limit not configured")

    if config.get("objective") in ALLOWED_OBJECTIVES:
        passed.append("objective")
    else:
        failed.append("objective not selected/invalid")


def _web3_checks(config, failed, passed):
    wallet = config.get("wallet_address")
    if isinstance(wallet, str) and wallet.lower() == BURNER_ADDRESS.lower():
        passed.append("wallet_address")
    else:
        failed.append("not a burner wallet")

    balance = config.get("balance")
    balance_cap = config.get("balance_cap")
    if balance is None or balance_cap is None:
        failed.append("balance/cap not set")
    else:
        try:
            within_cap = balance <= balance_cap
        except TypeError:
            within_cap = False
        if within_cap:
            passed.append("balance_within_cap")
        else:
            failed.append("burner balance exceeds cap")


def _web2_checks(config, failed, passed):
    test_accounts = config.get("test_accounts")
    if isinstance(test_accounts, list) and len(test_accounts) >= 2:
        passed.append("test_accounts")
    else:
        failed.append("need >=2 in-scope test accounts")

    if config.get("hosts_all_in_scope") is True:
        passed.append("hosts_all_in_scope")
    else:
        failed.append("not all hosts in-scope")


def load_baseline(path=None):
    """Reads the operator's persistent OPSEC baseline (environment statics: vpn_active/incognito/not_logged_main +
    burner wallet_address + balance_cap + rate_limit + objective default).

    FAIL-SAFE TOWARD SECURITY, not hunting: no file / corrupt JSON / not a dict / any exception ->
    {} (empty baseline). An empty baseline "rescues" NOTHING -- the gate stays fail-closed on every
    uncovered axis. That is, the baseline can ONLY fill in missing static keys of a valid
    per-call config; it cannot make an invalid launch valid.

    Path: env OPSEC_BASELINE_PATH (for test isolation), otherwise opsec_baseline.json.
    The baseline does NOT contain per-target/factual axes (balance, target.in_scope, test_accounts): those are
    supplied by the caller per-call, and on merge they override the baseline (see preflight)."""
    if path is None:
        path = os.environ.get("OPSEC_BASELINE_PATH") or os.path.join(_TOOLKIT_ROOT, BASELINE_FILENAME)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_audit(target, profile, passed, objective):
    slug = target.get("slug")
    if not slug:
        raise ValueError("target.slug missing/empty")
    session_dir = os.path.join(SESSIONS_DIR, str(slug))
    os.makedirs(session_dir, exist_ok=True)
    audit_path = os.path.join(session_dir, "opsec_preflight.json")
    payload = {
        "ts": int(time.time()),
        "profile": profile,
        "passed_checks": passed,
        "objective": objective,
    }
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# preflight -- entry point
# ---------------------------------------------------------------------------

def preflight(profile, target, config, _baseline=None):
    failed = []
    passed = []
    objective = None

    try:
        if profile not in ALLOWED_PROFILES:
            failed.append("profile invalid (expected web3/web2): %r" % (profile,))

        cfg_is_dict = isinstance(config, dict)
        tgt_is_dict = isinstance(target, dict)
        if not cfg_is_dict:
            failed.append("config not a dict/invalid")
        if not tgt_is_dict:
            failed.append("target not a dict/invalid")

        if cfg_is_dict and tgt_is_dict:
            # The baseline is merged in ONLY under a valid per-call config: an invalid config has already
            # failed above, and the baseline does not "rescue" it. The per-call config overrides the baseline
            # (balance/in_scope/test_accounts -- facts, which outweigh the signed statics).
            base = _baseline if isinstance(_baseline, dict) else load_baseline()
            eff = dict(base)
            eff.update(config)

            _common_checks(eff, target, failed, passed)
            objective = eff.get("objective")

            if profile == "web3":
                _web3_checks(eff, failed, passed)
            elif profile == "web2":
                _web2_checks(eff, failed, passed)
            # else: an invalid profile was already logged above, we cannot determine the branch -- skip it.
    except Exception as exc:
        # Defense in depth: anything unexpected (a weird __eq__, a TypeError on comparison, etc.)
        # -- also fail-closed, not a crash.
        failed.append("preflight: unexpected validation error (%r)" % (exc,))

    if failed:
        return Result(False, failed, "MANUAL")

    try:
        _write_audit(target, profile, passed, objective)
    except Exception as exc:
        # Audit was not written (no slug, disk/permissions, etc.) -- no paper trail => we do not consider
        # the launch permitted, and block it the same as any other fail-closed case.
        return Result(False, ["audit write failed (%r)" % (exc,)], "MANUAL")

    return Result(True, [], "AUTO")
