#!/usr/bin/env python3
"""
decompile.py — Decompile EVM bytecode to pseudo-Solidity.

Orchestrates external decompilers: Heimdall-rs (primary) → Panoramix (fallback).
Used when target contract is NOT verified on Etherscan/Sourcify.

Usage:
  python3 decompile.py --bytecode-file path/to/bytecode.hex --output sessions/X/
  python3 decompile.py --address 0xABC... --chain monad --output ...

Requires:
  - heimdall CLI installed (curl https://get.heimdall.rs | bash)
  - panoramix as fallback (pip install panoramix-decompiler)
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def check_tool(tool: str) -> bool:
    return shutil.which(tool) is not None


def fetch_bytecode(address: str, chain: str = "ethereum") -> str | None:
    """Fetch bytecode via cast (Foundry) or explorer API."""
    if not check_tool("cast"):
        return None
    rpc_urls = {
        "ethereum": "https://eth.llamarpc.com",
        "arbitrum": "https://arb1.arbitrum.io/rpc",
        "optimism": "https://mainnet.optimism.io",
        "base": "https://mainnet.base.org",
        "polygon": "https://polygon.llamarpc.com",
        "monad": "https://rpc.monad.xyz",
    }
    rpc = rpc_urls.get(chain.lower(), rpc_urls["ethereum"])
    try:
        result = subprocess.run(
            ["cast", "code", address, "--rpc-url", rpc],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip() != "0x":
            return result.stdout.strip()
    except Exception as e:
        print(f"cast failed: {e}", file=sys.stderr)
    return None


def decompile_heimdall(bytecode_path: Path, output_dir: Path) -> bool:
    """Run heimdall decompile."""
    if not check_tool("heimdall"):
        return False
    try:
        result = subprocess.run(
            ["heimdall", "decompile", str(bytecode_path), "-o", str(output_dir / "heimdall"), "--include-solidity"],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            return True
        print(f"heimdall stderr: {result.stderr[:500]}", file=sys.stderr)
    except Exception as e:
        print(f"heimdall failed: {e}", file=sys.stderr)
    return False


def decompile_panoramix(bytecode_path: Path, output_dir: Path) -> bool:
    """Run panoramix (fallback)."""
    if not check_tool("panoramix"):
        return False
    try:
        bytecode = bytecode_path.read_text().strip()
        if bytecode.startswith("0x"):
            bytecode = bytecode[2:]
        result = subprocess.run(
            ["panoramix", bytecode],
            capture_output=True, text=True, timeout=300,
        )
        if result.stdout:
            (output_dir / "panoramix.txt").write_text(result.stdout, encoding="utf-8")
            return True
    except Exception as e:
        print(f"panoramix failed: {e}", file=sys.stderr)
    return False


def main():
    p = argparse.ArgumentParser(description="Decompile EVM bytecode (Heimdall + Panoramix fallback)")
    p.add_argument("--bytecode-file", help="Path to file containing hex bytecode")
    p.add_argument("--address", help="Contract address (fetched via cast)")
    p.add_argument("--chain", default="ethereum", help="Chain for --address fetch")
    p.add_argument("--output", required=True)
    args = p.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get bytecode
    bytecode_path: Path
    if args.bytecode_file:
        bytecode_path = Path(args.bytecode_file)
        if not bytecode_path.exists():
            print(f"ERROR: {bytecode_path} not found")
            return 1
    elif args.address:
        bc = fetch_bytecode(args.address, args.chain)
        if not bc:
            print(f"ERROR: failed to fetch bytecode for {args.address}")
            return 1
        bytecode_path = output_dir / "bytecode.hex"
        bytecode_path.write_text(bc, encoding="utf-8")
    else:
        print("ERROR: provide --bytecode-file or --address")
        return 1

    # Try Heimdall first
    print("[*] Trying Heimdall...")
    if decompile_heimdall(bytecode_path, output_dir):
        print(f"[+] Heimdall output: {output_dir}/heimdall/")
        return 0

    # Fallback Panoramix
    print("[*] Heimdall failed/missing, trying Panoramix...")
    if decompile_panoramix(bytecode_path, output_dir):
        print(f"[+] Panoramix output: {output_dir}/panoramix.txt")
        return 0

    print("[!] Both decompilers failed/missing. Install:")
    print("    Heimdall: curl https://get.heimdall.rs | bash && heimdall update")
    print("    Panoramix: pip install panoramix-decompiler")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
