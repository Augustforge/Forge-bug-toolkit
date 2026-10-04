# -*- coding: utf-8 -*-
"""Account-provisioning, SIMPLIFIED (Plan 9 Task 8, Tier D, R12).

Problem: the authz-diff harness (`scripts/web2/authz_diff.py`) is idle without >=2 roles (attacker/victim) --
`opsec_preflight._web2_checks` does not let a live run through at all with <2 test accounts. This module is a
creds-config CONVENTION that feeds the harness its roles. It is NOT full auto email/OTP/signup automation
(overkill for our volume -- accounts are created by hand, the harness READS their creds/sessions).

What it does:
    load_creds_config(path) -> {role: RoleAccount}   -- reads a local JSON creds-config
    provision(config_path, target, opsec_config, live) -> ProvisionResult
    session_bundle(accounts) -> {role: {credentials, cookies, session_path}}  -- what the live driver consumes

SECURITY (R5):
    * Any LIVE run MUST pass `opsec_preflight.preflight("web2", ...)` fail-CLOSED BEFORE
      handing out usable accounts. Gate did not pass -> ProvisionResult(ok=False, accounts={}, mode=MANUAL),
      we NEVER hand out creds for a live test. `live=False` (default) -- pure config read for
      offline planning, no network, no gate needed.
    * creds/cookies are local-session-only: `session_path` is resolved ONLY under
      `sessions/{target}/` (traversal/absolute external paths are discarded). No external I/O.
    * ONLY test accounts (like the whole opsec contour).

The module is fail-open BY DEFAULT (broken config -> ProvisionResult(ok=False), not a crash) EXCEPT the opsec branch,
which is fail-CLOSED (see opsec_preflight.py).
"""

import os
import json
import importlib.util

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOLKIT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
SESSIONS_DIR = os.path.join(_TOOLKIT_ROOT, "sessions")

# Minimum number of roles so authz-diff is not idle (attacker + victim). Matches
# opsec_preflight._web2_checks (>=2 test_accounts) -- the same threshold.
MIN_ROLES = 2


# ---------------------------------------------------------------------------
# opsec_preflight -- loaded via importlib (toolkit is self-contained, _methodology is not on sys.path,
# pattern copied from runtime_harness.py / authz_diff.py).
# ---------------------------------------------------------------------------

def _load_opsec():
    path = os.path.join(_HERE, "opsec_preflight.py")
    spec = importlib.util.spec_from_file_location("opsec_preflight", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ---------------------------------------------------------------------------
# RoleAccount / ProvisionResult
# ---------------------------------------------------------------------------

class RoleAccount(object):
    """One provisioned account: role (attacker/victim/user-A...), creds dict, path to session/cookies
    (already resolved under sessions/{target}/, None if not set), loaded cookies (None until the
    session is loaded / no file)."""

    def __init__(self, role, credentials, session_path=None, cookies=None):
        self.role = role
        self.credentials = credentials or {}
        self.session_path = session_path
        self.cookies = cookies

    def __repr__(self):
        return "RoleAccount(role=%r, session_path=%r, has_cookies=%r)" % (
            self.role, self.session_path, self.cookies is not None)


class ProvisionResult(object):
    """{ok, accounts, errors, mode}. mode = 'AUTO' (ready to feed the live harness) / 'MANUAL'
    (offline plan OR opsec block -- a live test is NOT allowed)."""

    def __init__(self, ok, accounts, errors, mode):
        self.ok = ok
        self.accounts = accounts          # {role: RoleAccount}
        self.errors = errors              # list[str]
        self.mode = mode

    def __repr__(self):
        return "ProvisionResult(ok=%r, roles=%r, errors=%r, mode=%r)" % (
            self.ok, sorted(self.accounts.keys()), self.errors, self.mode)


# ---------------------------------------------------------------------------
# session_path resolution -- local-session-only
# ---------------------------------------------------------------------------

def _resolve_session_path(session_path, target_slug):
    """`session_path` from the config -> absolute path INSIDE sessions/{target}/ or None.

    Only relative paths are allowed; we resolve under sessions/{target}/ and check that the result did NOT
    escape that folder (traversal guard). Absolute/external paths are discarded -- creds and
    cookies are kept strictly local-session-only."""
    if not session_path or not isinstance(session_path, str):
        return None
    if not target_slug:
        return None
    if os.path.isabs(session_path):
        return None
    base = os.path.abspath(os.path.join(SESSIONS_DIR, str(target_slug)))
    candidate = os.path.abspath(os.path.join(base, session_path))
    # Traversal guard: candidate must lie inside base.
    if candidate != base and not candidate.startswith(base + os.sep):
        return None
    return candidate


def _load_cookies(resolved_path):
    """Reads cookies JSON from an already-resolved local-session path. No file / broken -> None
    (fail-open: a missing session does not break provisioning, the live driver will log in via credentials)."""
    if not resolved_path or not os.path.isfile(resolved_path):
        return None
    try:
        with open(resolved_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# load_creds_config
# ---------------------------------------------------------------------------

def load_creds_config(config_path):
    """Reads a local creds-config JSON:
        {"target": "<slug>", "roles": {"<role>": {"credentials": {...},
                                                   "session_path": "<rel-path>"}, ...}}
    -> (target_slug, {role: RoleAccount}, errors). Fail-open: any problem -> ([], {}, [errors])."""
    errors = []
    if not config_path or not os.path.isfile(config_path):
        return None, {}, ["creds-config not found: %r" % (config_path,)]
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as exc:
        return None, {}, ["creds-config unreadable/not JSON (%r)" % (exc,)]

    if not isinstance(raw, dict):
        return None, {}, ["creds-config: root is not an object"]

    target_slug = raw.get("target")
    roles_raw = raw.get("roles")
    if not isinstance(roles_raw, dict) or not roles_raw:
        return target_slug, {}, ["creds-config: 'roles' section is empty/not an object"]

    accounts = {}
    for role, spec in roles_raw.items():
        if not isinstance(spec, dict):
            errors.append("role %r: description is not an object -- skipped" % (role,))
            continue
        creds = spec.get("credentials")
        if not isinstance(creds, dict):
            creds = {}
        resolved = _resolve_session_path(spec.get("session_path"), target_slug)
        if spec.get("session_path") and resolved is None:
            errors.append("role %r: session_path outside sessions/%s/ -- discarded" % (role, target_slug))
        cookies = _load_cookies(resolved)
        accounts[role] = RoleAccount(role, creds, session_path=resolved, cookies=cookies)

    return target_slug, accounts, errors


# ---------------------------------------------------------------------------
# session_bundle -- exposure to authz_diff
# ---------------------------------------------------------------------------

def session_bundle(accounts):
    """{role: RoleAccount} -> {role: {credentials, cookies, session_path}} -- the material the
    live driver attaches to the session to obtain role_responses for `authz_diff.build_role_contexts`.
    This module itself NEVER sends live requests -- it only hands out creds/sessions."""
    out = {}
    for role, acc in (accounts or {}).items():
        out[role] = {
            "credentials": acc.credentials,
            "cookies": acc.cookies,
            "session_path": acc.session_path,
        }
    return out


# ---------------------------------------------------------------------------
# provision -- entry point
# ---------------------------------------------------------------------------

def provision(config_path, target=None, opsec_config=None, live=False):
    """Reads the creds-config, validates >=2 roles; for a live run it runs opsec_preflight fail-CLOSED.

    config_path -- path to the creds-config JSON.
    target      -- dict for opsec_preflight (`{"slug":..., "in_scope":...}`); if None, we take
                   `{"slug": <target from config>, "in_scope": True(?)}` -- NO, we do not
                   invent in_scope: without an explicit target dict the live run is blocked (fail-closed).
    opsec_config -- flat config for opsec_preflight (see opsec_preflight._common_checks/_web2_checks).
                    If 'test_accounts' is not set, it is auto-filled from the config roles (exactly what
                    we provision) -- a convenience, not a bypass: >=2 roles from config => >=2 test_accounts.
    live        -- False (default): offline plan, opsec not needed (no network), mode='MANUAL'.
                   True: before handing out accounts it MUST pass opsec_preflight -> mode='AUTO'.
    """
    target_slug, accounts, errors = load_creds_config(config_path)

    if len(accounts) < MIN_ROLES:
        errors = errors + ["need >=%d roles (attacker/victim), found %d" % (MIN_ROLES, len(accounts))]
        return ProvisionResult(False, {}, errors, "MANUAL")

    if not live:
        # Offline plan: pure read, no live test -> we do not run opsec, accounts are usable
        # only for offline labeling (e.g. an authz-matrix over ALREADY captured responses).
        return ProvisionResult(True, accounts, errors, "MANUAL")

    # ---- LIVE: fail-CLOSED opsec gate BEFORE handing out creds ----
    opsec = _load_opsec()

    cfg = dict(opsec_config) if isinstance(opsec_config, dict) else {}
    # Auto-fill test_accounts from the provisioned roles if the operator did not set it explicitly.
    if "test_accounts" not in cfg:
        cfg["test_accounts"] = sorted(accounts.keys())

    # A target dict is required for the in_scope check; without it opsec fails on its own (fail-closed).
    if isinstance(target, dict):
        tgt = target
    else:
        # No explicit target dict -> hand opsec an incomplete target (slug from config, in_scope
        # missing) => opsec fails the in_scope check. We do NOT invent in_scope.
        tgt = {"slug": target_slug}

    result = opsec.preflight("web2", tgt, cfg)
    if not result.ok:
        return ProvisionResult(
            False, {},
            errors + ["opsec_preflight blocked the live run: %s" % ("; ".join(result.failed_checks),)],
            "MANUAL",
        )

    return ProvisionResult(True, accounts, errors, "AUTO")


# ---------------------------------------------------------------------------
# CLI (operator convenience: check a config offline)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: account_provision.py <creds-config.json>")
        sys.exit(2)
    r = provision(sys.argv[1], live=False)
    print(repr(r))
    for role, acc in sorted(r.accounts.items()):
        print("  ", repr(acc))
    for e in r.errors:
        print("  ! ", e)
