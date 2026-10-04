# -*- coding: utf-8 -*-
"""web2_exposure.py — runtime half of the Exposure Engine for the /hunt web2 profile (P0-2, SlowMist Aug-2026).

Symmetric to dapphunt's `runtime_harness.capture_exposure` (parallel-profile pattern over the shared
`secret_patterns` core): scans ALREADY-CAPTURED live web2 artifacts — response bodies (`_body` convention),
rendered DOM, JS chunks, localStorage/sessionStorage values, window globals captured during an authz-diff
browser session — for secrets / crypto-keys / PII / financial data (+ recursive decode layer).

Why this exists: the static exposure scanner (`secret_exposure_scanner.py`) is wired PRIMARY into /hunt, but
the web2 runtime path (a live authz-diff browser session) had no exposure hook — a secret injected at runtime
or living only in a response body / storage value / window global was invisible to a static file walk. This
closes that gap for web2 (mirrors what runtime_harness does for dapphunt).

OPSEC/white-hat (fail-closed, same discipline as `authz_diff.py` live-capture): the caller (/hunt web2 skill)
performs the live browser capture ONLY after `opsec_preflight.preflight("web2", ...)` succeeds
(VPN / incognito / not-logged-main / in-scope / rate-limit / >=2 test accounts). This module does NO live
I/O — it only scans passed snapshots. no-exfil: raw secret values are STRIPPED before return (delegated to
`secret_patterns.capture_exposure`).

    capture_exposure(sources, path_kind="runtime", enable_pii=True) -> list[dict]

`sources`: dict {label: text} | list[(label, text)] | list[str]. For the authz-diff session, put each captured
response body (the `_body` convention), DOM view, JS chunk, storage value, or window-global snapshot as one
labelled blob. PII/financial are IN-SCOPE for web2 (the "valuable data" surface), so `enable_pii` defaults True.
"""
import os
import importlib.util

# toolkit is self-contained (_methodology NOT on sys.path) — load the shared core by file path, resolved from
# __file__ (this is a reusable library imported by the skill/test from varying cwd), NOT from os.getcwd().
_METHOD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_methodology")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


_secrets = _load("secret_patterns", os.path.join(_METHOD_DIR, "secret_patterns.py"))


def capture_exposure(sources, path_kind="runtime", enable_pii=True):
    """Scan captured web2 session artifacts for exposure. Delegates to the shared `secret_patterns` core
    (strips the raw `_match` value — no-exfil). Fail-open: bad input -> []. See module docstring for the
    fail-closed OPSEC gate the caller MUST pass before doing the live capture that produces `sources`."""
    return _secrets.capture_exposure(sources, path_kind=path_kind, enable_pii=enable_pii)
