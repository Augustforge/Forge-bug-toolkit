#!/usr/bin/env python3
"""
Real-time contract deploy listener.

Listens to mempool / new pending transactions via WebSocket RPC.
Detects new contract deployments (to: null) → automatically fetches source
and runs quick scan. Goal: be FIRST to scan freshly deployed contracts
before other hunters spot them.

Triggers full pipeline only for "interesting" deploys:
- Deployer in watchlist OR
- Code size > 50KB (significant contract)
- AND verified within N minutes

Usage:
    python3 deploy_listener.py --rpc wss://eth-mainnet.g.alchemy.com/v2/KEY \\
        --watchlist watchlist.txt --output sessions/_deploys
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

try:
    import websockets
except ImportError:
    print("[!] pip install websockets")
    sys.exit(1)

import requests

ETHERSCAN_KEY = os.getenv("ETHERSCAN_API_KEY", "")
SCRIPT_DIR = Path(__file__).resolve().parent
NOTIFY = SCRIPT_DIR.parent / "monitors" / "notify.py"

CHAIN_ID_BY_RPC_HOST = {
    "eth-mainnet": 1, "ethereum": 1, "mainnet": 1,
    "bsc": 56, "polygon": 137, "arbitrum": 42161,
    "optimism": 10, "base": 8453, "avalanche": 43114,
}


def detect_chainid(rpc: str) -> int:
    for k, v in CHAIN_ID_BY_RPC_HOST.items():
        if k in rpc.lower():
            return v
    return 1


def is_verified(chainid: int, address: str) -> bool:
    if not ETHERSCAN_KEY:
        return False
    try:
        r = requests.get(
            "https://api.etherscan.io/v2/api",
            params={"chainid": chainid, "module": "contract", "action": "getsourcecode",
                    "address": address, "apikey": ETHERSCAN_KEY},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("status") == "1":
                result = data.get("result", [])
                if result and result[0].get("SourceCode"):
                    return True
    except Exception:
        pass
    return False


def alert(message: str):
    if NOTIFY.exists():
        try:
            subprocess.run(
                [sys.executable, str(NOTIFY), "--message", f"🚀 NEW DEPLOY: {message}"],
                timeout=15,
            )
        except Exception:
            pass


def trigger_scan(chainid: int, address: str, output_root: Path):
    chain_name = next((k.split("-")[0] for k, v in CHAIN_ID_BY_RPC_HOST.items()
                       if v == chainid), "eth")
    target = f"{chain_name}:{address}"
    target_dir = output_root / address.lower()
    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"[+] Triggering scan for {target}")
    try:
        subprocess.Popen(
            ["bash", str(SCRIPT_DIR / "scan.sh"),
             "--onchain", target, "--output", str(target_dir), "--mode", "quick"],
            stdout=open(target_dir / "scan.log", "w"),
            stderr=subprocess.STDOUT,
        )
    except Exception as e:
        print(f"[!] Scan trigger failed: {e}")


async def watch(rpc: str, watchlist: set[str], output: Path,
                wait_minutes: int, code_size_threshold: int):
    chainid = detect_chainid(rpc)
    print(f"[*] Connecting to {rpc} (chainid={chainid})...")

    async with websockets.connect(rpc) as ws:
        await ws.send(json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "eth_subscribe",
            "params": ["newPendingTransactions"],
        }))
        sub_resp = await ws.recv()
        print(f"[*] Subscribed: {sub_resp}")

        seen_deploys = set()
        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=120)
            except asyncio.TimeoutError:
                print("[*] No messages in 120s — keep alive")
                continue
            try:
                data = json.loads(msg)
            except Exception:
                continue

            if "params" not in data:
                continue
            tx_hash = data["params"].get("result")
            if not tx_hash:
                continue

            await asyncio.sleep(0.1)
            tx_resp = requests.post(rpc.replace("wss://", "https://").replace("ws://", "http://"),
                                     json={"jsonrpc": "2.0", "id": 2,
                                           "method": "eth_getTransactionByHash",
                                           "params": [tx_hash]}, timeout=10)
            try:
                tx = tx_resp.json().get("result")
            except Exception:
                continue
            if not tx:
                continue

            if tx.get("to") is not None:
                continue  # not a deploy

            input_data = tx.get("input", "")
            code_size = len(input_data) // 2  # hex
            from_addr = (tx.get("from") or "").lower()
            interesting = (
                from_addr in watchlist or code_size > code_size_threshold
            )
            if not interesting:
                continue

            print(f"[*] Deploy from {from_addr[:10]}... size={code_size}B")

            await asyncio.sleep(wait_minutes * 60)

            receipt = requests.post(rpc.replace("wss://", "https://").replace("ws://", "http://"),
                                     json={"jsonrpc": "2.0", "id": 3,
                                           "method": "eth_getTransactionReceipt",
                                           "params": [tx_hash]}, timeout=10).json().get("result")
            if not receipt:
                continue
            address = receipt.get("contractAddress")
            if not address or address.lower() in seen_deploys:
                continue
            seen_deploys.add(address.lower())

            verified = is_verified(chainid, address)
            note = "verified" if verified else "unverified (bytecode-only)"
            alert(f"{address} on chain {chainid} — {note}, deployer {from_addr[:10]}")
            print(f"[+] {address} ({note})")

            if verified:
                trigger_scan(chainid, address, output)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rpc", required=True, help="WebSocket RPC URL (wss://...)")
    ap.add_argument("--watchlist", help="File with deployer addresses")
    ap.add_argument("--output", required=True)
    ap.add_argument("--wait-minutes", type=int, default=5,
                    help="Wait N min after deploy before scan (let verify happen)")
    ap.add_argument("--code-size-threshold", type=int, default=50_000,
                    help="Min deploy bytecode size for auto-trigger")
    args = ap.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    watchlist = set()
    if args.watchlist and Path(args.watchlist).exists():
        watchlist = {line.strip().lower() for line in Path(args.watchlist).read_text().splitlines()
                     if line.strip() and not line.startswith("#")}
        print(f"[*] Watchlist: {len(watchlist)} addresses")

    print(f"[*] Listening for deploys (size threshold: {args.code_size_threshold}B)...")
    asyncio.run(watch(args.rpc, watchlist, out,
                       args.wait_minutes, args.code_size_threshold))


if __name__ == "__main__":
    main()
