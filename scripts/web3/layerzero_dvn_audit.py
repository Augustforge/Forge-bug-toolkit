#!/usr/bin/env python3
"""
LayerZero v2 onchain DVN audit.

Reads UlnConfig from Endpoint contract for given OApp on a specific chain.
Flags requiredDVNCount < 2.

Pattern from KelpDAO ($292M, April 2026): single DVN = single point of failure.

Usage:
    python3 layerzero_dvn_audit.py --oapp 0xOApp --chain ethereum --output ./out
    python3 layerzero_dvn_audit.py --oapp 0xOApp --chain ethereum --remote arbitrum

Endpoint addresses: https://docs.layerzero.network/v2/developers/evm/technical-reference/deployed-contracts
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests


# LayerZero v2 Endpoint addresses (top chains)
ENDPOINTS = {
    "ethereum": "0x1a44076050125825900e736c501f859c50fE728c",
    "arbitrum": "0x1a44076050125825900e736c501f859c50fE728c",
    "optimism": "0x1a44076050125825900e736c501f859c50fE728c",
    "base": "0x1a44076050125825900e736c501f859c50fE728c",
    "polygon": "0x1a44076050125825900e736c501f859c50fE728c",
    "bsc": "0x1a44076050125825900e736c501f859c50fE728c",
    "avalanche": "0x1a44076050125825900e736c501f859c50fE728c",
}

# LayerZero v2 EIDs
EIDS = {
    "ethereum": 30101, "arbitrum": 30110, "optimism": 30111,
    "base": 30184, "polygon": 30109, "bsc": 30102,
    "avalanche": 30106, "fantom": 30112,
}

CHAIN_IDS = {
    "ethereum": 1, "arbitrum": 42161, "optimism": 10,
    "base": 8453, "polygon": 137, "bsc": 56,
    "avalanche": 43114, "fantom": 250,
}

ADDR_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


def validate_addr(addr: str) -> bool:
    return bool(ADDR_RE.match(addr))


def eth_call(rpc_url: str, to: str, data: str) -> str | None:
    payload = {
        "jsonrpc": "2.0", "method": "eth_call", "id": 1,
        "params": [{"to": to, "data": data}, "latest"],
    }
    try:
        r = requests.post(rpc_url, json=payload, timeout=20)
        if r.status_code != 200:
            return None
        result = r.json()
        if "error" in result:
            return None
        return result.get("result")
    except Exception:
        return None


def get_send_library(rpc_url: str, endpoint: str, oapp: str, remote_eid: int) -> str | None:
    """getSendLibrary(address _sender, uint32 _dstEid) -> (address)"""
    selector = "0x9c6d7340"  # keccak256("getSendLibrary(address,uint32)")[:4]
    data = (
        selector
        + oapp[2:].lower().rjust(64, "0")
        + hex(remote_eid)[2:].rjust(64, "0")
    )
    result = eth_call(rpc_url, endpoint, data)
    if not result or len(result) < 66:
        return None
    return "0x" + result[-40:]


def get_uln_config(rpc_url: str, lib: str, oapp: str, remote_eid: int) -> dict | None:
    """
    getUlnConfig(address _oapp, uint32 _remoteEid) -> UlnConfig
    UlnConfig: (uint64 confirmations, uint8 requiredDVNCount, uint8 optionalDVNCount,
                uint8 optionalDVNThreshold, address[] requiredDVNs, address[] optionalDVNs)
    """
    selector = "0xc1574d2c"
    data = (
        selector
        + oapp[2:].lower().rjust(64, "0")
        + hex(remote_eid)[2:].rjust(64, "0")
    )
    result = eth_call(rpc_url, lib, data)
    if not result:
        return None

    try:
        hex_data = result[2:]
        confirmations = int(hex_data[0:64], 16)
        required_dvn_count = int(hex_data[64:128], 16)
        optional_dvn_count = int(hex_data[128:192], 16)
        optional_dvn_threshold = int(hex_data[192:256], 16)
        return {
            "confirmations": confirmations,
            "requiredDVNCount": required_dvn_count,
            "optionalDVNCount": optional_dvn_count,
            "optionalDVNThreshold": optional_dvn_threshold,
        }
    except Exception:
        return None


def audit(oapp: str, chain: str, remote: str | None) -> dict:
    rpc = os.getenv(f"{chain.upper()}_RPC_URL") or os.getenv("RPC_URL")
    if not rpc:
        return {"error": f"Set {chain.upper()}_RPC_URL or RPC_URL env var"}

    if chain not in ENDPOINTS:
        return {"error": f"Unsupported chain: {chain}"}

    endpoint = ENDPOINTS[chain]
    remotes = [remote] if remote else [r for r in EIDS if r != chain]

    audit_results = []
    for remote_chain in remotes:
        if remote_chain not in EIDS:
            continue
        remote_eid = EIDS[remote_chain]
        send_lib = get_send_library(rpc, endpoint, oapp, remote_eid)
        if not send_lib or send_lib == "0x" + "0" * 40:
            audit_results.append({
                "remote": remote_chain,
                "remote_eid": remote_eid,
                "status": "no_send_library_set",
            })
            continue

        config = get_uln_config(rpc, send_lib, oapp, remote_eid)
        if not config:
            audit_results.append({
                "remote": remote_chain,
                "send_library": send_lib,
                "status": "config_read_failed",
            })
            continue

        required = config["requiredDVNCount"]
        optional = config["optionalDVNCount"]
        opt_threshold = config["optionalDVNThreshold"]

        severity = "info"
        verdict = "ok"
        if required < 2 and (optional == 0 or opt_threshold == 0):
            severity = "high"
            verdict = "INSUFFICIENT_DVN_COUNT (KelpDAO pattern — single point of failure)"
        elif required < 2:
            severity = "medium"
            verdict = "low requiredDVNCount, partially mitigated by optionalDVNs"

        audit_results.append({
            "remote": remote_chain,
            "remote_eid": remote_eid,
            "send_library": send_lib,
            "uln_config": config,
            "verdict": verdict,
            "severity": severity,
        })
        time.sleep(0.2)

    return {
        "oapp": oapp,
        "chain": chain,
        "endpoint": endpoint,
        "audited_paths": audit_results,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--oapp", required=True, help="OApp contract address")
    ap.add_argument("--chain", required=True, choices=list(ENDPOINTS.keys()))
    ap.add_argument("--remote", help="Specific remote chain (default: scan all)")
    ap.add_argument("--output", help="Output dir")
    args = ap.parse_args()

    if not validate_addr(args.oapp):
        sys.exit("Invalid OApp address")

    result = audit(args.oapp, args.chain, args.remote)
    print(json.dumps(result, indent=2))

    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        f = out / f"layerzero_dvn_{args.oapp[:10]}_{args.chain}.json"
        f.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        print(f"\n[+] Saved: {f}", file=sys.stderr)

    high = [p for p in result.get("audited_paths", []) if p.get("severity") == "high"]
    if high:
        print(f"\n[!] {len(high)} HIGH severity findings — KelpDAO pattern", file=sys.stderr)


if __name__ == "__main__":
    main()
