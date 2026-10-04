"""solana.py — Solana mempool / pending tx adapter.

Solana doesn't have a public mempool the way EVM does. Alternatives:
- Helius Geyser plugin (private, paid) — gives shred-level access
- Jito Block Engine — sees bundles before submission
- Public WS subscription to pending tx via RPC

For initial version: WS subscription to programNotifications + signature stream.
Real production needs Helius/Jito access.
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


CHAIN_ID = "sol"
CHAIN_NAME = "Solana mainnet"


class SolanaAdapter:
    def __init__(self, ws_url: str | None = None):
        self.ws_url = ws_url or os.environ.get("SOL_WS_URL")
        if not self.ws_url:
            raise RuntimeError("SOL_WS_URL not set (try Helius / Triton / Jito endpoint)")

    async def iter_pending(self) -> AsyncIterator[dict]:
        if websockets is None:
            raise RuntimeError("pip install websockets")

        # Solana RPC subscribe: subscribes to signatures (post-broadcast — not true mempool)
        # For pre-broadcast: need Helius Geyser plugin (commercial)
        subscribe_req = {
            "jsonrpc": "2.0", "id": 1,
            "method": "signatureSubscribe",
            "params": ["*", {"commitment": "processed"}],
        }
        async with websockets.connect(self.ws_url, ping_interval=30) as ws:
            await ws.send(json.dumps(subscribe_req))
            await ws.recv()
            async for msg in ws:
                try:
                    data = json.loads(msg)
                    result = data.get("params", {}).get("result", {})
                    sig = result.get("signature")
                    if sig:
                        yield self._normalize({"signature": sig, "slot": result.get("slot")})
                except Exception as e:
                    print(f"[warn] sol parse: {e}", file=sys.stderr)

    def _normalize(self, tx: dict) -> dict:
        # Solana tx schema different — keep what's available
        return {
            "chain": CHAIN_ID,
            "tx_hash": tx.get("signature"),
            "from": None,
            "to": None,
            "value": None,
            "input": None,
            "selector": None,
            "slot": tx.get("slot"),
            "raw": tx,
        }


def mock_iter_pending(n: int = 5):
    import secrets
    for i in range(n):
        yield {
            "chain": CHAIN_ID,
            "tx_hash": secrets.token_hex(32),
            "from": None, "to": None, "value": None,
            "input": None, "selector": None,
            "slot": 280000000 + i,
            "raw": {},
        }
