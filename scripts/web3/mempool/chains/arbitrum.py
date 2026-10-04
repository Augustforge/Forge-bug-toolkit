"""arbitrum.py — Arbitrum mempool adapter. Sequencer feed."""
import asyncio
import json
import os
import sys
from typing import AsyncIterator

try:
    import websockets
except ImportError:
    websockets = None


CHAIN_ID = "arb"
CHAIN_NAME = "Arbitrum One"


class ArbitrumAdapter:
    """Arbitrum L2 — sequencer feed via wss://arb1.arbitrum.io/feed or RPC WS."""

    def __init__(self, ws_url: str | None = None):
        self.ws_url = ws_url or os.environ.get("ARB_WS_URL")
        if not self.ws_url:
            raise RuntimeError("ARB_WS_URL not set")

    async def iter_pending(self) -> AsyncIterator[dict]:
        if websockets is None:
            raise RuntimeError("pip install websockets")
        # Arbitrum has sequencer feed at wss://arb1.arbitrum.io/feed — alternative path
        # For production: use Alchemy/Infura ARB WS endpoint
        subscribe_req = {
            "jsonrpc": "2.0", "id": 1,
            "method": "eth_subscribe", "params": ["newPendingTransactions"],
        }
        async with websockets.connect(self.ws_url, ping_interval=30) as ws:
            await ws.send(json.dumps(subscribe_req))
            await ws.recv()
            async for msg in ws:
                try:
                    data = json.loads(msg)
                    tx_hash = data.get("params", {}).get("result")
                    if isinstance(tx_hash, str):
                        full = await self._fetch_tx(ws, tx_hash)
                        if full:
                            yield self._normalize(full)
                except Exception as e:
                    print(f"[warn] arb parse: {e}", file=sys.stderr)

    async def _fetch_tx(self, ws, tx_hash: str):
        req = {"jsonrpc": "2.0", "id": 99, "method": "eth_getTransactionByHash", "params": [tx_hash]}
        await ws.send(json.dumps(req))
        return json.loads(await ws.recv()).get("result")

    def _normalize(self, tx: dict) -> dict:
        data = tx.get("input", "")
        return {
            "chain": CHAIN_ID, "tx_hash": tx.get("hash"),
            "from": (tx.get("from") or "").lower(), "to": (tx.get("to") or "").lower(),
            "value": int(tx.get("value", "0x0"), 16) if isinstance(tx.get("value"), str) else tx.get("value", 0),
            "input": data, "selector": data[:10] if len(data) >= 10 else "",
            "gas": int(tx.get("gas", "0x0"), 16) if isinstance(tx.get("gas"), str) else 0,
            "raw": tx,
        }


def mock_iter_pending(n: int = 5):
    import secrets
    for i in range(n):
        yield {
            "chain": CHAIN_ID, "tx_hash": "0x" + secrets.token_hex(32),
            "from": "0x" + secrets.token_hex(20), "to": "0x" + secrets.token_hex(20),
            "value": (i + 1) * 10**18 * 30,
            "input": "0x3ccfd60b", "selector": "0x3ccfd60b", "gas": 100000, "raw": {},
        }
