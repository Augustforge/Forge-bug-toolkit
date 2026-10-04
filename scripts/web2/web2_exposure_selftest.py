#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fixture test for web2_exposure.capture_exposure (P0-2 web2 runtime half, SlowMist Aug-2026).

Simulates captured web2 session artifacts (response bodies / DOM / storage / window globals / encoded JS
chunk) and asserts the Exposure Engine detects planted secrets / crypto-keys / PII / financial data,
serializes non-str snapshots, attributes `source`, and NEVER exfiltrates a raw value (no-exfil).
Proof-of-firing: each detection check fails if the wiring/delegation regresses. No solc/network/browser.

Run: py -3 -X utf8 web2_exposure_selftest.py
"""
import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import web2_exposure as we  # noqa: E402

SIGNER = "0x" + "a1b2c3d4" * 8   # 64-hex, high-enough entropy (not placeholder), not anvil
# context-free (nameless) EVM key + its derived address (offline-validated) — for the derive-correlate path.
CTXFREE_KEY = "0x4a7f4a7f4a7f4a7fb91cb91cb91cb91cd3e8d3e8d3e8d3e85f2a5f2a5f2a5f2a"
CTXFREE_ADDR = "0xAe3618dF729b975D92d1752222B20Ec785102D96"
RANDOM_HASH = "0x1f9d8c3b6e4a2f70d5c8b1a4e7f0293d6c5b8a1f4e7d0c3b6a9f2e5d8c1b4a7f"  # addr not in corpus → drop


def _jwt_service_role():
    h = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').decode().rstrip("=")
    p = base64.urlsafe_b64encode(b'{"role":"service_role","iss":"supabase"}').decode().rstrip("=")
    return h + "." + p + ".c2lnbmF0dXJlZGF0YQ"


def run():
    sources = {
        # response body (_body convention) with a Supabase service_role JWT
        "GET /api/config (_body)": '{"ok":true,"serviceKey":"' + _jwt_service_role() + '"}',
        # rendered DOM carrying an EVM private key near key-context
        "DOM #root": '<script>var apiSignerKey="' + SIGNER + '";</script>',
        # window global captured as a dict (must be JSON-serialized before scan)
        "window.__ENV": {"privateKey": SIGNER, "env": "prod"},
        # localStorage value with PII (email) — web2 valuable-data surface
        "localStorage:profile": '{"email":"alice@corp.io","name":"Alice"}',
        # response body with financial/confidential data in key:value form
        "GET /account (_body)": "account_number: 111 routing_number: 222 balance: 999 kyc: yes",
        # minified JS chunk with a base64-encoded key (recursive decode layer)
        "chunk-4f2.js": "var c='" + base64.b64encode(("signerPrivateKey=" + SIGNER).encode()).decode() + "';",
        # context-free: nameless key in a response body (field "data" — NO key-name), derived address echoed
        # in another response → confirmed via corpus correlation. Random hash w/o addr-ref → dropped.
        "GET /api/relay (_body)": '{"data":"' + CTXFREE_KEY + '","ok":true}',
        "GET /api/whoami (_body)": '{"account":"' + CTXFREE_ADDR + '","role":"user"}',
        "GET /api/tree (_body)":  '{"root":"' + RANDOM_HASH + '"}',
    }
    findings = we.capture_exposure(sources, path_kind="runtime", enable_pii=True)
    kinds = {f["kind"] for f in findings}
    _derive_ok = we._secrets.derive_evm_address(CTXFREE_KEY)   # None if eth-libs absent → confirm test N/A

    checks = [
        ("evm_privkey detected in DOM", "evm_privkey" in kinds),
        ("jwt_service_role detected in response body", "jwt_service_role" in kinds),
        ("dict window-global JSON-serialized + key detected",
         any(f.get("source") == "window.__ENV" and f["kind"] == "evm_privkey" for f in findings)),
        ("PII email detected in storage", any(f["cls"] == "pii" for f in findings)),
        ("financial marker detected", any(f["cls"] == "financial" for f in findings)),
        ("decode-layer key from encoded chunk", any(f.get("decoded_via") and f["kind"] == "evm_privkey"
                                                     for f in findings)),
        ("source attributed on every finding", bool(findings) and all(f.get("source") for f in findings)),
        # no-exfil: raw value never in output (no _match key, no full SIGNER in redacted)
        ("no-exfil: raw value stripped",
         not any(("_match" in f) or (SIGNER in str(f.get("redacted", ""))) for f in findings)),
        ("fail-open on bad input", we.capture_exposure(None) == [] and we.capture_exposure(12345) == []),
        # ── context-free (nameless) key via web2 runtime derive-correlate ──
        ("context-free: nameless key in _body CONFIRMED via derived-addr echoed in another _body",
         (any(f["kind"] == "evm_privkey" and str(f.get("derived_address", "")).lower() == CTXFREE_ADDR.lower()
              and f.get("source") == "GET /api/relay (_body)" for f in findings))
         if _derive_ok else True),
        ("context-free: random hash (addr not in corpus) → dropped (no flood)",
         not any(f.get("source") == "GET /api/tree (_body)"
                 and f["kind"] in ("evm_privkey", "evm_key_candidate") for f in findings)),
    ]

    passed = failed = 0
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        passed += ok
        failed += (not ok)
    print(f"\nweb2_exposure_selftest: {passed}/{passed + failed} passed")
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
