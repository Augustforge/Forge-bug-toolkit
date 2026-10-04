"""
ethereum.py — ETH mainnet mempool adapter.

Connects via WebSocket (Alchemy / Blocknative / Infura). Yields async pending
tx events.

Env: ETH_WS_URL (e.g., wss://eth-mainnet.g.alchemy.com/v2/<KEY>)
"""
import asyncio
import json
import os
import sys
from typing import AsyncIterator

try:
    import websockets
except ImportError:
    websockets = None


CHAIN_ID = "eth"
CHAIN_NAME = "Ethereum mainnet"


class EthereumAdapter:
    def __init__(self, ws_url: str | None = None):
        self.ws_url = ws_url or os.environ.get("ETH_WS_URL")
        if not self.ws_url:
            raise RuntimeError("ETH_WS_URL not set")

    async def iter_pending(self) -> AsyncIterator[dict]:
        """Async generator yielding pending tx dicts."""
        if websockets is None:
            raise RuntimeError("pip install websockets")

        subscribe_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_subscribe",
            "params": ["alchemy_pendingTransactions"],
        }
        # Fallback: standard pendingTransactions
        fallback_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_subscribe",
            "params": ["newPendingTransactions"],
        }

        async with websockets.connect(self.ws_url, ping_interval=30) as ws:
            await ws.send(json.dumps(subscribe_req))
            resp = json.loads(await ws.recv())
            if resp.get("error"):
                print(f"[warn] alchemy_pendingTransactions unsupported, fallback: {resp['error']}", file=sys.stderr)
                await ws.send(json.dumps(fallback_req))
                resp = json.loads(await ws.recv())
                if resp.get("error"):
                    raise RuntimeError(f"both subs failed: {resp['error']}")

            async for msg in ws:
                try:
                    data = json.loads(msg)
                    params = data.get("params", {})
                    tx = params.get("result")
                    if not tx:
                        continue
                    if isinstance(tx, str):
                        # newPendingTransactions returns hash only — fetch full
                        tx = await self._fetch_tx(ws, tx)
                        if not tx:
                            continue
                    yield self._normalize(tx)
                except Exception as e:
                    print(f"[warn] parse error: {e}", file=sys.stderr)
                    continue

    async def _fetch_tx(self, ws, tx_hash: str) -> dict | None:
        """Fetch full tx by hash via same WS connection."""
        req = {
            "jsonrpc": "2.0",
            "id": 99,
            "method": "eth_getTransactionByHash",
            "params": [tx_hash],
        }
        await ws.send(json.dumps(req))
        resp = json.loads(await ws.recv())
        return resp.get("result")

    def _normalize(self, tx: dict) -> dict:
        """Normalize tx to common schema."""
        data = tx.get("input", "")
        selector = data[:10] if len(data) >= 10 else ""
        return {
            "chain": CHAIN_ID,
            "tx_hash": tx.get("hash"),
            "from": (tx.get("from") or "").lower(),
            "to": (tx.get("to") or "").lower(),
            "value": int(tx.get("value", "0x0"), 16) if isinstance(tx.get("value"), str) else tx.get("value", 0),
            "input": data,
            "selector": selector,
            "gas": int(tx.get("gas", "0x0"), 16) if isinstance(tx.get("gas"), str) else 0,
            "raw": tx,
        }


# Synchronous fallback for testing
def mock_iter_pending(n: int = 5):
    """Generate fake pending txs for tests — varied values to test pattern matching."""
    import secrets
    for i in range(n):
        # Mix: small (1 ETH), medium (10 ETH), large (50 ETH = ~$150k)
        eth_amount = [1, 5, 10, 50, 200][i % 5]
        yield {
            "chain": CHAIN_ID,
            "tx_hash": "0x" + secrets.token_hex(32),
            "from": "0x" + secrets.token_hex(20),
            "to": "0x" + secrets.token_hex(20),
            "value": eth_amount * 10**18,
            "input": "0x2e1a7d4d" + "00" * 32,
            "selector": "0x2e1a7d4d",
            "gas": 100000,
            "raw": {},
        }
