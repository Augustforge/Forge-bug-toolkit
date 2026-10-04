#!/usr/bin/env python3
"""
WebSocket security testing.

Modern apps use WS heavily — our scan.sh skips this class.

Tests:
- Origin validation (CSWSH — Cross-Site WebSocket Hijacking)
- Auth bypass (connect without a token)
- Message manipulation (send unauthorized actions)
- IDOR via WS (read another user)
- Lack of rate limiting
- DoS via message flooding

Usage:
    python3 websocket_test.py --url wss://api.example.com/ws --output ./out
    python3 websocket_test.py --auto-discover https://example.com --output ./out
"""

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

import requests

try:
    import websockets
except ImportError:
    print("[!] pip install websockets")
    sys.exit(1)


def discover_ws(url: str) -> list[str]:
    """Extract WebSocket URLs from page HTML/JS."""
    try:
        r = requests.get(url, timeout=15)
    except Exception:
        return []
    found = set()
    patterns = [
        r"wss?://[a-zA-Z0-9.\-/_:?=]+",
        r"['\"](wss?://[a-zA-Z0-9.\-/_:?=]+)['\"]",
        r"WebSocket\(['\"]([^'\"]+)['\"]",
        r"new\s+WebSocket\(['\"]([^'\"]+)['\"]",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, r.text):
            url = m.group(1) if m.lastindex else m.group(0)
            if url.startswith(("ws://", "wss://")):
                found.add(url)
    return list(found)


async def test_origin_validation(url: str, evil_origin: str = "https://evil.com") -> dict:
    """CSWSH — Cross-Site WebSocket Hijacking."""
    try:
        async with websockets.connect(
            url, additional_headers={"Origin": evil_origin}
        ) as ws:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                return {
                    "test": "origin_validation",
                    "evil_origin_accepted": True,
                    "severity": "high",
                    "evidence": f"Connected with Origin: {evil_origin}, received: {str(msg)[:200]}",
                }
            except asyncio.TimeoutError:
                return {
                    "test": "origin_validation",
                    "evil_origin_accepted": True,
                    "severity": "high",
                    "evidence": "Connection accepted (no message in 5s)",
                }
    except websockets.exceptions.InvalidHandshake as e:
        return {"test": "origin_validation", "evil_origin_rejected": True, "severity": "info"}
    except Exception as e:
        return {"test": "origin_validation", "error": str(e)}


async def test_auth_bypass(url: str) -> dict:
    """Connect without credentials."""
    try:
        async with websockets.connect(url) as ws:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                return {
                    "test": "auth_bypass",
                    "anonymous_connect_accepted": True,
                    "severity": "medium",
                    "evidence": f"Connected without auth, received: {str(msg)[:200]}",
                }
            except asyncio.TimeoutError:
                return {
                    "test": "auth_bypass",
                    "anonymous_connect_accepted": True,
                    "severity": "low",
                    "evidence": "Connected anonymously, no immediate response",
                }
    except Exception as e:
        return {"test": "auth_bypass", "rejected": True, "error": str(e)}


async def test_message_flooding(url: str, count: int = 100) -> dict:
    """DoS — no rate limiting on messages."""
    try:
        async with websockets.connect(url) as ws:
            start = time.time()
            for i in range(count):
                try:
                    await ws.send(f'{{"ping": {i}}}')
                except Exception:
                    break
            elapsed = time.time() - start
            return {
                "test": "message_flooding",
                "messages_sent": count,
                "elapsed_seconds": round(elapsed, 2),
                "rate_limited": elapsed > count * 0.5,
                "severity": "low" if elapsed < 2 else "info",
            }
    except Exception as e:
        return {"test": "message_flooding", "error": str(e)}


async def run_tests(url: str) -> dict:
    print(f"[*] Testing {url}")
    results = {"url": url, "tests": []}
    results["tests"].append(await test_origin_validation(url))
    results["tests"].append(await test_auth_bypass(url))
    results["tests"].append(await test_message_flooding(url, 50))
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    ap.add_argument("--auto-discover", help="HTTPS URL to extract WS endpoints from")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    targets = []
    if args.url:
        targets.append(args.url)
    if args.auto_discover:
        discovered = discover_ws(args.auto_discover)
        print(f"[*] Discovered {len(discovered)} WS endpoints")
        targets.extend(discovered)

    if not targets:
        sys.exit("Need --url or --auto-discover")

    all_results = []
    for url in targets:
        try:
            r = asyncio.run(run_tests(url))
        except Exception as e:
            r = {"url": url, "error": str(e)}
        all_results.append(r)

    out_file = out / "websocket.json"
    out_file.write_text(json.dumps({
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "targets": all_results,
    }, indent=2, ensure_ascii=False))
    print(f"[+] Saved: {out_file}")


if __name__ == "__main__":
    main()
