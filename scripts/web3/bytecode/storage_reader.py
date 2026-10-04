#!/usr/bin/env python3
"""
storage_reader.py — Read live contract storage slots via eth_getStorageAt.

Useful for:
- Recovering admin/owner address from unverified proxies
- Reading EIP-1967 implementation slot
- Inspecting storage layout when no source code

Usage:
  python3 storage_reader.py --address 0xABC --slots 0,1,2 --chain monad
  python3 storage_reader.py --address 0xABC --eip1967 --chain ethereum
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

# EIP-1967 standard slots
EIP1967_SLOTS = {
    "implementation": "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc",
    "admin": "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103",
    "beacon": "0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50",
    "rollback": "0x4910fdfa16fed3260ed0e7147f7cc6da11a60208b5b9406d12a635614ffd9143",
}

RPC_URLS = {
    "ethereum": "https://eth.llamarpc.com",
    "arbitrum": "https://arb1.arbitrum.io/rpc",
    "optimism": "https://mainnet.optimism.io",
    "base": "https://mainnet.base.org",
    "polygon": "https://polygon.llamarpc.com",
    "monad": "https://rpc.monad.xyz",
}


def read_slot(address: str, slot: str, rpc: str) -> str | None:
    """Read storage slot via cast."""
    try:
        result = subprocess.run(
            ["cast", "storage", address, slot, "--rpc-url", rpc],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        print(f"cast storage failed: {e}", file=sys.stderr)
    return None


def slot_to_address(slot_value: str) -> str | None:
    """If slot value looks like address, extract it."""
    if not slot_value:
        return None
    val = slot_value.lower().replace("0x", "")
    # Right 40 hex chars = 20 bytes = address
    if len(val) >= 40:
        addr = "0x" + val[-40:]
        if int(addr, 16) != 0:
            return addr
    return None


def main():
    p = argparse.ArgumentParser(description="Read contract storage slots")
    p.add_argument("--address", required=True)
    p.add_argument("--chain", default="ethereum")
    p.add_argument("--slots", help="Comma-separated slot numbers (decimal or 0xhex)")
    p.add_argument("--eip1967", action="store_true", help="Read all EIP-1967 standard slots")
    p.add_argument("--range", help="Read range, e.g., 0-20")
    p.add_argument("--output", default=".")
    args = p.parse_args()

    rpc = RPC_URLS.get(args.chain.lower(), RPC_URLS["ethereum"])
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {}

    if args.eip1967:
        for name, slot in EIP1967_SLOTS.items():
            val = read_slot(args.address, slot, rpc)
            results[f"eip1967.{name}"] = {
                "slot": slot,
                "value": val,
                "as_address": slot_to_address(val) if val else None,
            }

    if args.slots:
        for s in args.slots.split(","):
            s = s.strip()
            slot_hex = s if s.startswith("0x") else hex(int(s))
            val = read_slot(args.address, slot_hex, rpc)
            results[f"slot.{slot_hex}"] = {
                "value": val,
                "as_address": slot_to_address(val) if val else None,
            }

    if args.range:
        start, end = args.range.split("-")
        for i in range(int(start), int(end) + 1):
            slot_hex = hex(i)
            val = read_slot(args.address, slot_hex, rpc)
            results[f"slot.{i}"] = {
                "slot_hex": slot_hex,
                "value": val,
                "as_address": slot_to_address(val) if val else None,
            }

    (output_dir / "storage.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    print(f"=== Storage of {args.address} on {args.chain} ===")
    for key, info in results.items():
        val_short = info["value"][:18] + "..." if info["value"] and len(info["value"]) > 20 else info["value"]
        addr_hint = f" → {info['as_address']}" if info.get("as_address") else ""
        print(f"  {key:30s} = {val_short}{addr_hint}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
