#!/usr/bin/env python3
"""
ownership_transfer_monitor.py — Watch custody contracts for ownership/admin changes.

Leading indicator of the DxSale-class drain ($7.3M, 2026): ownership of a legacy locker
was silently transferred ~9 months before the attack. `deploy_listener.py` only catches
NEW deploys — this catches OWNERSHIP/ADMIN events on contracts that already hold funds.

Watches (per contract in contracts.watchlist.json):
  - OwnershipTransferred(address,address)
  - AdminChanged(address,address)               (EIP-1967 proxy admin)
  - RoleGranted(bytes32,address,address)         (AccessControl)
  - RoleRevoked(bytes32,address,address)

Pure-stdlib JSON-RPC (urllib). Outputs ownership.json compatible with aggregator.py
(normalize_ownership). High severity by default — ownership change on a custody contract
is always worth a human look.

Usage:
  py -3 ownership_transfer_monitor.py --output ./out
  py -3 ownership_transfer_monitor.py --watchlist contracts.watchlist.json --lookback 7200
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
DEFAULT_WATCHLIST = ROOT / "contracts.watchlist.json"

# event topic0 (keccak of signature)
TOPICS = {
    "0x8be0079c531659141344cd1fd0a4f28419497f9722a3daafe3b4186f6b6457e0": "OwnershipTransferred",
    "0x7e644d79422f17c01e4894b5f4f588d331ebfa28653d42ae832dc59e38c9798f": "AdminChanged",
    "0x2f8788117e7eff1d82e926ec794901d17c78024a50270940304540a733656f0d": "RoleGranted",
    "0xf6391f5c32d9c69d2a47ea670b442974b53935d1edc7fd64eb21e047a839171b": "RoleRevoked",
}


def rpc(url: str, method: str, params: list, timeout: int = 25) -> Any:
    body = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.loads(r.read().decode())
    except (urllib.error.URLError, ValueError) as e:
        raise RuntimeError(f"RPC failed: {e}") from e
    if "error" in payload:
        raise RuntimeError(f"RPC error: {payload['error']}")
    return payload.get("result")


def _hexint(x: str) -> int:
    return int(x, 16) if isinstance(x, str) and x.startswith("0x") else int(x)


def _addr_from_topic(topic: str) -> str:
    return "0x" + topic[-40:] if topic and len(topic) >= 42 else topic


def scan_contract(rpc_url: str, entry: Dict[str, Any], lookback_blocks: int) -> List[Dict[str, Any]]:
    addr = entry["address"]
    try:
        latest = _hexint(rpc(rpc_url, "eth_blockNumber", []))
    except RuntimeError as e:
        return [{"error": str(e), "contract": addr}]
    from_block = max(0, latest - lookback_blocks)
    try:
        logs = rpc(rpc_url, "eth_getLogs", [{
            "address": addr,
            "fromBlock": hex(from_block),
            "toBlock": "latest",
            "topics": [list(TOPICS.keys())],
        }])
    except RuntimeError as e:
        return [{"error": str(e), "contract": addr}]
    out = []
    for lg in logs or []:
        topics = lg.get("topics", [])
        if not topics:
            continue
        event = TOPICS.get(topics[0], "Unknown")
        detail = ""
        if event in ("OwnershipTransferred", "AdminChanged") and len(topics) >= 3:
            detail = f"{_addr_from_topic(topics[1])} -> {_addr_from_topic(topics[2])}"
        elif event in ("RoleGranted", "RoleRevoked") and len(topics) >= 3:
            detail = f"role {topics[1][:10]}… account {_addr_from_topic(topics[2])}"
        out.append({
            "contract": addr,
            "protocol": entry.get("protocol", "?"),
            "chain": entry.get("chain", "?"),
            "event": event,
            "detail": detail,
            "tx": lg.get("transactionHash"),
            "block": _hexint(lg.get("blockNumber", "0x0")),
        })
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--watchlist", default=str(DEFAULT_WATCHLIST))
    ap.add_argument("--output", default=".")
    ap.add_argument("--lookback", type=int, default=7200, help="blocks to look back (default ~1 day @ 12s)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    wl_path = Path(args.watchlist)
    if not wl_path.exists():
        print(f"[!] watchlist not found: {wl_path} (create it — see contracts.watchlist.json)", file=sys.stderr)
        return 0
    wl = json.loads(wl_path.read_text(encoding="utf-8"))
    rpcs = wl.get("rpc", {})
    contracts = wl.get("contracts", [])

    entries = []
    for c in contracts:
        rpc_url = c.get("rpc") or rpcs.get(c.get("chain", ""))
        if not rpc_url:
            continue
        for hit in scan_contract(rpc_url, c, args.lookback):
            if "error" in hit:
                if not args.quiet:
                    print(f"  [warn] {hit['contract']}: {hit['error']}", file=sys.stderr)
                continue
            entries.append({
                "contract": hit["contract"],
                "protocol": hit["protocol"],
                "chain": hit["chain"],
                "title": f"{hit['event']} on {hit['protocol']} ({hit['chain']}): {hit['detail']}",
                "link": hit.get("tx", ""),
                "date": "",
                "severity": "high",  # ownership change on custody contract = always review
                "matched_keywords": [hit["event"], "custody", "ownership-change"],
                "description": f"block {hit['block']} tx {hit.get('tx')}",
            })

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ownership.json").write_text(
        json.dumps({"entries": entries}, indent=2), encoding="utf-8")
    if not args.quiet:
        print(f"[+] ownership events: {len(entries)} → {out_dir / 'ownership.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
