#!/usr/bin/env python3
"""
symbolic_exec.py — Wrapper for symbolic execution on bytecode.

Tries Manticore (if installed) then Mythril (bytecode mode).
Used for unverified contracts where Slither/source analysis impossible.

Usage:
  python3 symbolic_exec.py --bytecode-file path/to/bc.hex --output sessions/X/
  python3 symbolic_exec.py --address 0xABC --chain monad --output ...
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def check_tool(t: str) -> bool:
    return shutil.which(t) is not None


def run_mythril_bytecode(bytecode_path: Path, output_dir: Path) -> bool:
    """Mythril supports bytecode-only mode via -c flag."""
    if not check_tool("myth"):
        return False
    try:
        bytecode = bytecode_path.read_text().strip()
        if not bytecode.startswith("0x"):
            bytecode = "0x" + bytecode
        result = subprocess.run(
            ["myth", "analyze", "-c", bytecode, "-o", "json", "--max-depth", "30", "--execution-timeout", "300"],
            capture_output=True, text=True, timeout=400,
        )
        out_file = output_dir / "mythril_bytecode.json"
        out_file.write_text(result.stdout, encoding="utf-8")
        return result.returncode == 0
    except Exception as e:
        print(f"mythril failed: {e}", file=sys.stderr)
        return False


def run_manticore(bytecode_path: Path, output_dir: Path) -> bool:
    if not check_tool("manticore"):
        return False
    try:
        result = subprocess.run(
            ["manticore", str(bytecode_path), "--workspace", str(output_dir / "manticore_workspace")],
            capture_output=True, text=True, timeout=600,
        )
        (output_dir / "manticore.txt").write_text(result.stdout + "\n---STDERR---\n" + result.stderr, encoding="utf-8")
        return True
    except Exception as e:
        print(f"manticore failed: {e}", file=sys.stderr)
        return False


def fetch_bytecode_cast(address: str, chain: str) -> str | None:
    rpc_urls = {
        "ethereum": "https://eth.llamarpc.com",
        "arbitrum": "https://arb1.arbitrum.io/rpc",
        "monad": "https://rpc.monad.xyz",
    }
    rpc = rpc_urls.get(chain.lower(), rpc_urls["ethereum"])
    try:
        result = subprocess.run(["cast", "code", address, "--rpc-url", rpc], capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and result.stdout.strip() != "0x":
            return result.stdout.strip()
    except Exception:
        pass
    return None


def main():
    p = argparse.ArgumentParser(description="Symbolic execution on bytecode")
    p.add_argument("--bytecode-file")
    p.add_argument("--address")
    p.add_argument("--chain", default="ethereum")
    p.add_argument("--output", required=True)
    args = p.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.bytecode_file:
        bytecode_path = Path(args.bytecode_file)
    elif args.address:
        bc = fetch_bytecode_cast(args.address, args.chain)
        if not bc:
            print("ERROR: bytecode fetch failed")
            return 1
        bytecode_path = output_dir / "bytecode.hex"
        bytecode_path.write_text(bc, encoding="utf-8")
    else:
        print("ERROR: provide --bytecode-file or --address")
        return 1

    print("[*] Trying Mythril (bytecode mode)...")
    if run_mythril_bytecode(bytecode_path, output_dir):
        print(f"[+] Mythril output: {output_dir}/mythril_bytecode.json")

    print("[*] Trying Manticore...")
    if run_manticore(bytecode_path, output_dir):
        print(f"[+] Manticore output: {output_dir}/manticore.txt")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
