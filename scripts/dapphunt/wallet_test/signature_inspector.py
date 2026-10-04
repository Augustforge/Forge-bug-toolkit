#!/usr/bin/env python3
"""
signature_inspector.py — Decode and analyze EIP-712 typed data / personal_sign
payloads captured during interactive testing.

Input: paste the JSON params that the wallet shows for `eth_signTypedData_v4`,
or the hex-encoded message for `personal_sign`. Script:

- Parses EIP-712 domain (chainId, verifyingContract, name, version)
- Flags chainId == 1 hardcoded when dApp deploys on L2 (cross-chain replay)
- Flags missing `EIP712Domain` type definition
- Flags SIWE message format and checks for required fields (nonce, expiration_time)
- For personal_sign: decodes the message bytes and shows the user-visible text

Usage:
    # EIP-712 from clipboard
    python3 signature_inspector.py --eip712-stdin
    # SIWE message
    python3 signature_inspector.py --siwe-stdin
    # personal_sign hex
    python3 signature_inspector.py --personal-sign 0xdeadbeef...
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Optional


def _decode_personal_sign(hex_payload: str) -> str:
    s = hex_payload.lower()
    if s.startswith("0x"):
        s = s[2:]
    try:
        decoded = bytes.fromhex(s).decode("utf-8", errors="replace")
    except Exception as exc:
        return f"(could not decode: {exc})"
    return decoded


def _analyze_eip712(data: dict) -> dict:
    """Inspect typed-data structure for known risk patterns."""
    findings = []
    domain = data.get("domain", {}) if isinstance(data, dict) else {}
    types = data.get("types", {}) if isinstance(data, dict) else {}
    primary_type = data.get("primaryType") if isinstance(data, dict) else None
    message = data.get("message", {}) if isinstance(data, dict) else {}

    chain_id = domain.get("chainId")
    verifying_contract = domain.get("verifyingContract")
    domain_name = domain.get("name")
    domain_version = domain.get("version")

    if chain_id == 1 and isinstance(verifying_contract, str):
        findings.append({
            "id": "F1",
            "severity": "medium",
            "issue": "chainId=1 (Ethereum mainnet) in EIP-712 domain. If the dApp also deploys on L2s, this signature is replayable across chains.",
        })
    if not verifying_contract:
        findings.append({
            "id": "F2",
            "severity": "medium",
            "issue": "`domain.verifyingContract` is empty. Signatures not bound to a contract address are theoretically replayable across deployments.",
        })
    if not domain.get("salt") and not (chain_id and verifying_contract):
        findings.append({
            "id": "F3",
            "severity": "low",
            "issue": "Domain has no chainId+verifyingContract combination AND no salt. Bindings are weak.",
        })
    if "EIP712Domain" not in types:
        findings.append({
            "id": "F4",
            "severity": "low",
            "issue": "Types map missing `EIP712Domain` definition — some wallets reject; some accept and may compute hash differently.",
        })

    # If primary type is "Permit" and `deadline` is far-future or zero
    if primary_type == "Permit" or "Permit" in (primary_type or ""):
        deadline = message.get("deadline")
        if deadline is not None:
            try:
                deadline_int = int(str(deadline), 16) if str(deadline).startswith("0x") else int(deadline)
                # 1 year in seconds = 31_536_000; flag if > 1 year from "now-ish"
                if deadline_int > 4_000_000_000:  # year 2096
                    findings.append({
                        "id": "F5",
                        "severity": "high",
                        "issue": f"Permit deadline {deadline_int} is effectively infinite. Signature is permanent.",
                    })
            except Exception:
                pass

    return {
        "domain": domain,
        "primary_type": primary_type,
        "message_keys": list(message.keys()) if isinstance(message, dict) else [],
        "findings": findings,
    }


def _analyze_siwe(message: str) -> dict:
    """Quick SIWE message analysis."""
    findings = []
    has_domain = re.search(r"^([^\s]+) wants you to sign in", message)
    has_nonce = re.search(r"Nonce:\s*([A-Za-z0-9]+)", message)
    has_issued_at = re.search(r"Issued At:\s*(\S+)", message)
    has_expiration = re.search(r"Expiration Time:\s*(\S+)", message)

    if not has_domain:
        findings.append({"id": "S1", "severity": "high", "issue": "Message does not match SIWE format (missing 'wants you to sign in' line)."})
    if not has_nonce:
        findings.append({"id": "S2", "severity": "high", "issue": "No `Nonce:` field — replay attack possible."})
    if not has_issued_at:
        findings.append({"id": "S3", "severity": "medium", "issue": "No `Issued At:` field."})
    if not has_expiration:
        findings.append({"id": "S4", "severity": "medium", "issue": "No `Expiration Time:` field — signature does not expire."})

    return {
        "domain": has_domain.group(1) if has_domain else None,
        "nonce": has_nonce.group(1) if has_nonce else None,
        "issued_at": has_issued_at.group(1) if has_issued_at else None,
        "expiration": has_expiration.group(1) if has_expiration else None,
        "findings": findings,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--eip712-stdin", action="store_true", help="Read EIP-712 typed-data JSON from stdin")
    parser.add_argument("--siwe-stdin", action="store_true", help="Read SIWE message text from stdin")
    parser.add_argument("--personal-sign", type=str, help="Hex bytes of a personal_sign payload to decode")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.eip712_stdin:
        try:
            data = json.loads(sys.stdin.read())
        except json.JSONDecodeError as exc:
            print(f"error: invalid JSON on stdin: {exc}", file=sys.stderr)
            return 2
        analysis = _analyze_eip712(data)
        if args.json:
            print(json.dumps(analysis, ensure_ascii=False, indent=2))
        else:
            print("EIP-712 analysis")
            print(f"  domain: {analysis['domain']}")
            print(f"  primary_type: {analysis['primary_type']}")
            print(f"  message keys: {analysis['message_keys']}")
            for f in analysis["findings"]:
                print(f"  [{f['severity']}] {f['id']}: {f['issue']}")
        return 0 if not analysis["findings"] else 1

    if args.siwe_stdin:
        text = sys.stdin.read()
        analysis = _analyze_siwe(text)
        if args.json:
            print(json.dumps(analysis, ensure_ascii=False, indent=2))
        else:
            print("SIWE analysis")
            print(f"  domain: {analysis['domain']}")
            print(f"  nonce: {analysis['nonce']}")
            print(f"  issued_at: {analysis['issued_at']}")
            print(f"  expiration: {analysis['expiration']}")
            for f in analysis["findings"]:
                print(f"  [{f['severity']}] {f['id']}: {f['issue']}")
        return 0 if not analysis["findings"] else 1

    if args.personal_sign:
        decoded = _decode_personal_sign(args.personal_sign)
        if args.json:
            print(json.dumps({"decoded": decoded}, ensure_ascii=False, indent=2))
        else:
            print("personal_sign decoded message:")
            print(decoded)
        return 0

    parser.error("Choose one mode: --eip712-stdin / --siwe-stdin / --personal-sign HEX")


if __name__ == "__main__":
    sys.exit(main())
