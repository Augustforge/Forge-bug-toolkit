#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fixture test for the runtime half of the Exposure Engine (P0-2) — runtime_harness.capture_exposure.

No live browser/network I/O (the same discipline as all of runtime_harness): we feed in ALREADY CAPTURED
snapshots (DOM / JS chunk / storage value / encoded page / window global / response body) and check
that the sweep catches secrets/keys/JWT/PII, attributes the source, decodes encoded data, and does not leak the value.
Run: py -3 -X utf8 runtime_exposure_selftest.py
"""
import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import runtime_harness as rh  # noqa: E402

KEY = "0x" + "a1b2c3d4" * 8
# context-free (nameless) EVM key + its derived address (validated offline) — for the runtime derive-correlate
# path: a bare key with NO key-name whose DERIVED address is echoed in ANOTHER captured artifact = confirmed.
CTXFREE_KEY = "0x4a7f4a7f4a7f4a7fb91cb91cb91cb91cd3e8d3e8d3e8d3e85f2a5f2a5f2a5f2a"
CTXFREE_ADDR = "0xAe3618dF729b975D92d1752222B20Ec785102D96"
# a random in-range 64-hex (merkle root) whose derived address is NOWHERE in the corpus → must be DROPPED.
RANDOM_HASH = "0x1f9d8c3b6e4a2f70d5c8b1a4e7f0293d6c5b8a1f4e7d0c3b6a9f2e5d8c1b4a7f"


def _jwt(hdr, pl):
    h = base64.urlsafe_b64encode(hdr.encode()).decode().rstrip("=")
    p = base64.urlsafe_b64encode(pl.encode()).decode().rstrip("=")
    return f"{h}.{p}.c2ln"


def run():
    supa_jwt = _jwt('{"alg":"HS256"}', '{"role":"service_role"}')
    none_jwt = _jwt('{"alg":"none"}', '{"user":"admin"}')
    encoded_page = base64.b64encode(f"signerPrivateKey={KEY}".encode()).decode()
    sources = {
        "dom":              f"<script>var signerPrivateKey='{KEY}'</script>",
        "chunk_main.js":    f'const supa="{supa_jwt}";',
        "localStorage.tok": none_jwt,
        "page_encoded":     encoded_page,
        "window.__CONFIG":  {"apiKey": "AKIA1234567890ABCDEF", "env": "prod"},   # non-str → serialized
        "response_body":    "\n".join(f'"email":"user{i}@corp.io"' for i in range(6)),
        "localStorage.walletPrivateKey": KEY,   # BARE value, context ONLY in the key name (label)
        # context-free: nameless key in a response body (field "data" — NO key-name), its derived address
        # echoed in the rendered account view → confirmed via corpus correlation, NO variable name needed.
        "GET /api/relay (_body)": '{"data":"' + CTXFREE_KEY + '","ok":true}',
        "DOM #account-badge":     '<span class="addr">Connected: ' + CTXFREE_ADDR + '</span>',
        # nameless hash whose derived address is NOWHERE in the corpus → dropped (no flood).
        "GET /api/tree (_body)":  '{"root":"' + RANDOM_HASH + '"}',
    }
    findings = rh.capture_exposure(sources)
    kinds = {f["kind"] for f in findings}
    _derive_ok = rh._secrets.derive_evm_address(CTXFREE_KEY)   # None if eth-libs absent → confirm test N/A

    checks = [
        ("evm_privkey in DOM",              "evm_privkey" in kinds),
        ("label-context: bare key under key-named storage slot detected (live-drive fix)",
         any(f["kind"] == "evm_privkey" and f.get("source") == "localStorage.walletPrivateKey"
             for f in findings)),
        ("jwt_service_role (supabase)",     "jwt_service_role" in kinds),
        ("jwt alg:none flagged",            "jwt_issue" in kinds),
        ("aws key from window-global dict", "aws_access_key" in kinds),
        ("decode-layer (encoded page)",     any(f["kind"] == "evm_privkey" and f.get("decoded_via")
                                               and f.get("source") == "page_encoded" for f in findings)),
        ("PII emails detected",             sum(1 for f in findings if f["kind"] == "email") >= 5),
        ("source attributed on all",        all("source" in f for f in findings)),
        ("no-exfil: full key not leaked",   not any(KEY in f["redacted"] for f in findings)),
        # ── context-free (nameless) key via runtime derive-correlate (we look for keys even WITHOUT names) ──
        ("context-free: nameless key in response body CONFIRMED via derived-addr in captured corpus",
         (any(f["kind"] == "evm_privkey" and str(f.get("derived_address", "")).lower() == CTXFREE_ADDR.lower()
              and f.get("source") == "GET /api/relay (_body)" for f in findings))
         if _derive_ok else True),
        ("context-free: random merkle-root (addr not in corpus) → dropped (no flood)",
         not any(f.get("source") == "GET /api/tree (_body)"
                 and f["kind"] in ("evm_privkey", "evm_key_candidate") for f in findings)),
    ]

    passed = failed = 0
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        passed += ok
        failed += (not ok)

    # fail-open contract
    print(f"  [{'PASS' if rh.capture_exposure(None) == [] else 'FAIL'}] fail-open on bad input")
    passed += (rh.capture_exposure(None) == [])

    total = passed + failed
    print(f"\nruntime_exposure_selftest: {passed}/{total} passed")
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
