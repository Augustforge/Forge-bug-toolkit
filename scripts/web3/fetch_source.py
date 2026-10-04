#!/usr/bin/env python3
"""
Fetch verified contract source code via Etherscan API V2 (multichain).

V1 was deprecated 2025-05-31. V2 uses single API key for 60+ EVM chains
through `chainid` parameter.

Features:
- Multi-file source code parsing (Etherscan returns either single file or JSON)
- EIP-1967 proxy detection + recursive implementation fetch
- Sourcify.dev fallback if Etherscan has no source
- Local cache (~/.bbt/cache/etherscan/{chainid}/{address}.json), 24h TTL

Usage:
    python3 fetch_source.py --target eth:0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D \\
                            --output ./out
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

ETHERSCAN_KEY = os.getenv("ETHERSCAN_API_KEY", "")
CACHE_DIR = Path.home() / ".bbt" / "cache" / "etherscan"
CACHE_TTL = 24 * 3600

CHAIN_IDS = {
    "eth": 1, "ethereum": 1,
    "bsc": 56, "binance": 56,
    "polygon": 137, "matic": 137,
    "arbitrum": 42161, "arb": 42161,
    "optimism": 10, "op": 10,
    "base": 8453,
    "avalanche": 43114, "avax": 43114,
    "fantom": 250, "ftm": 250,
}

# EIP-1967 storage slots
PROXY_SLOTS = {
    "EIP1967_implementation": "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc",
    "EIP1967_admin": "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103",
    "EIP1967_beacon": "0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50",
    "OpenZeppelin_implementation": "0x7050c9e0f4ca769c69bd3a8ef740bc37934f8e2c036e5a723fd8ee048ed3f8c3",
}

ADDR_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


def is_valid_address(addr: str) -> bool:
    return bool(ADDR_RE.match(addr))


def cache_path(chainid: int, address: str) -> Path:
    p = CACHE_DIR / str(chainid)
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{address.lower()}.json"


def cache_read(chainid: int, address: str):
    p = cache_path(chainid, address)
    if not p.exists():
        return None
    try:
        if time.time() - p.stat().st_mtime > CACHE_TTL:
            return None
        return json.loads(p.read_text())
    except Exception:
        return None


def cache_write(chainid: int, address: str, data: dict):
    cache_path(chainid, address).write_text(json.dumps(data))


def etherscan_v2(chainid: int, address: str) -> dict:
    """Etherscan V2 multichain API getsourcecode."""
    if not ETHERSCAN_KEY:
        return {"error": "ETHERSCAN_API_KEY not set"}
    cached = cache_read(chainid, address)
    if cached:
        return cached
    try:
        r = requests.get(
            "https://api.etherscan.io/v2/api",
            params={
                "chainid": chainid,
                "module": "contract",
                "action": "getsourcecode",
                "address": address,
                "apikey": ETHERSCAN_KEY,
            },
            timeout=30,
        )
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}"}
        data = r.json()
        if data.get("status") != "1":
            return {"error": data.get("message", "unknown"), "result": data.get("result")}
        cache_write(chainid, address, data)
        time.sleep(0.25)
        return data
    except Exception as e:
        return {"error": str(e)}


def sourcify_fallback(chainid: int, address: str) -> dict:
    """Fallback to Sourcify decentralized verifier."""
    try:
        r = requests.get(
            f"https://sourcify.dev/server/files/any/{chainid}/{address}",
            timeout=30,
        )
        if r.status_code == 200:
            return {"status": "1", "source": "sourcify", "data": r.json()}
        return {"error": f"sourcify HTTP {r.status_code}"}
    except Exception as e:
        return {"error": str(e)}


def parse_etherscan_source(source_code: str) -> dict[str, str]:
    """
    Etherscan returns SourceCode in 3 forms:
    1. Single file: raw Solidity source
    2. Multi-file (single brace): {sources: {file: {content}}, ...}
    3. Multi-file (DOUBLE BRACE): {{sources: {file: {content}}, ...}}
    """
    s = source_code.strip()
    if s.startswith("{{") and s.endswith("}}"):
        try:
            obj = json.loads(s[1:-1])
            sources = obj.get("sources", {})
            return {fname: data.get("content", "") for fname, data in sources.items()}
        except Exception:
            return {"Contract.sol": source_code}
    if s.startswith("{") and s.endswith("}"):
        try:
            obj = json.loads(s)
            if "sources" in obj:
                return {fname: data.get("content", "") for fname, data in obj["sources"].items()}
            return {fname: data.get("content", "") for fname, data in obj.items()
                    if isinstance(data, dict) and "content" in data}
        except Exception:
            return {"Contract.sol": source_code}
    return {"Contract.sol": source_code}


def detect_proxy(chainid: int, address: str) -> dict:
    """EIP-1967 storage slots via Etherscan eth_getStorageAt."""
    if not ETHERSCAN_KEY:
        return {"is_proxy": False, "implementation": None, "type": "unknown"}
    for slot_name, slot in PROXY_SLOTS.items():
        try:
            r = requests.get(
                "https://api.etherscan.io/v2/api",
                params={
                    "chainid": chainid,
                    "module": "proxy",
                    "action": "eth_getStorageAt",
                    "address": address,
                    "position": slot,
                    "tag": "latest",
                    "apikey": ETHERSCAN_KEY,
                },
                timeout=15,
            )
            time.sleep(0.25)
            if r.status_code != 200:
                continue
            data = r.json()
            value = data.get("result", "0x0")
            if value and value != "0x" and int(value, 16) != 0:
                impl = "0x" + value[-40:]
                return {
                    "is_proxy": True,
                    "implementation": impl,
                    "type": slot_name.split("_")[0],
                }
        except Exception:
            continue
    return {"is_proxy": False, "implementation": None, "type": "none"}


def write_foundry_project(out_dir: Path, files: dict[str, str], compiler: str):
    src = out_dir / "src"
    src.mkdir(parents=True, exist_ok=True)
    for fname, content in files.items():
        clean = fname.replace("..", "_").lstrip("/")
        target = src / clean
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    solc_ver = re.search(r"v?(\d+\.\d+\.\d+)", compiler or "")
    solc = solc_ver.group(1) if solc_ver else "0.8.20"
    (out_dir / "foundry.toml").write_text(
        f"[profile.default]\nsrc = \"src\"\nout = \"out\"\nsolc = \"{solc}\"\n"
    )


def fetch_recursive(target: str, output_dir: Path, depth: int = 0) -> bool:
    """Recursively fetch implementation. Validate inputs strictly."""
    if depth > 3:
        return False
    if ":" not in target:
        return False
    chain_str, address = target.split(":", 1)
    if chain_str.lower() not in CHAIN_IDS or not is_valid_address(address):
        return False
    try:
        result = subprocess.run(
            [sys.executable, __file__, "--target", target, "--output", str(output_dir)],
            capture_output=True, text=True, timeout=120,
        )
        return result.returncode == 0
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True,
                    help="<chain>:<address> e.g. eth:0x7a25...")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    if ":" not in args.target:
        sys.exit("Target must be <chain>:<address>")
    chain_str, address = args.target.split(":", 1)
    chainid = CHAIN_IDS.get(chain_str.lower())
    if not chainid:
        sys.exit(f"Unknown chain: {chain_str}. Supported: {list(CHAIN_IDS)}")
    if not is_valid_address(address):
        sys.exit(f"Invalid address format: {address}")

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    print(f"[*] Target: {chain_str} (chainid={chainid}) / {address}")

    print("[*] Fetching via Etherscan V2...")
    data = etherscan_v2(chainid, address)
    is_verified = False
    files = {}
    compiler = ""
    contract_name = ""

    if data.get("status") == "1" and isinstance(data.get("result"), list):
        result = data["result"][0]
        source = result.get("SourceCode", "")
        if source:
            is_verified = True
            files = parse_etherscan_source(source)
            compiler = result.get("CompilerVersion", "")
            contract_name = result.get("ContractName", "")

    if not is_verified:
        print("[*] No Etherscan source. Trying Sourcify...")
        sf = sourcify_fallback(chainid, address)
        if sf.get("status") == "1":
            is_verified = True
            print("[+] Source found on Sourcify")

    print("[*] Checking for proxy pattern (EIP-1967)...")
    proxy_info = detect_proxy(chainid, address)
    if proxy_info["is_proxy"]:
        print(f"[!] Proxy detected ({proxy_info['type']}) → impl: {proxy_info['implementation']}")

    if is_verified and files:
        proj_dir = out / "foundry-project"
        write_foundry_project(proj_dir, files, compiler)
        print(f"[+] Wrote {len(files)} files to {proj_dir}/src/")

    impl_fetched = False
    if proxy_info["is_proxy"] and proxy_info["implementation"]:
        impl_dir = out / "implementation"
        impl_dir.mkdir(parents=True, exist_ok=True)
        print("[*] Recursively fetching implementation...")
        impl_target = f"{chain_str}:{proxy_info['implementation']}"
        impl_fetched = fetch_recursive(impl_target, impl_dir, depth=1)

    summary = {
        "target": args.target,
        "chainid": chainid,
        "address": address,
        "is_verified": is_verified,
        "compiler_version": compiler,
        "contract_name": contract_name,
        "files_count": len(files),
        "proxy": proxy_info,
        "implementation_fetched": impl_fetched,
    }
    (out / "fetch_summary.json").write_text(json.dumps(summary, indent=2))

    print(f"[+] Verified: {is_verified} | Compiler: {compiler} | Files: {len(files)}")
    print(f"[+] Saved to {out / 'fetch_summary.json'}")


if __name__ == "__main__":
    main()
