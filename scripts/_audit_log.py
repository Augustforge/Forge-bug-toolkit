#!/usr/bin/env python3
"""
Audit log — tracks every scan/action for legal protection and debugging.

Logs to ~/.bbt/audit.log (JSONL format, one entry per line).

Usage (from other scripts):
    from _audit_log import log_action
    log_action(target="example.com", mode="passive", tools=["subfinder"],
               authorization="bug-bounty-program: hackerone:example",
               result_summary="found 50 subdomains")

Or CLI:
    python3 _audit_log.py --target example.com --mode passive \\
        --tools subfinder,httpx --authorization "hackerone:example"
"""

import argparse
import json
import os
import socket
import sys
import time
from pathlib import Path

LOG_FILE = Path.home() / ".bbt" / "audit.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def log_action(target: str, mode: str, tools: list, authorization: str,
               result_summary: str = "", **kwargs):
    """Append one audit entry to the log."""
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target": target,
        "mode": mode,  # passive | active | web3 | proactive
        "tools": tools if isinstance(tools, list) else tools.split(","),
        "authorization": authorization,
        "result_summary": result_summary,
        "operator": os.getenv("USER") or os.getenv("USERNAME") or "unknown",
        "host": socket.gethostname(),
        **kwargs,
    }
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def tail(n: int = 20):
    """Return last N entries."""
    if not LOG_FILE.exists():
        return []
    lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
    return [json.loads(l) for l in lines[-n:] if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=False)
    ap.add_argument("--mode", required=False,
                    choices=["passive", "active", "web3", "proactive", "report"])
    ap.add_argument("--tools", required=False, default="")
    ap.add_argument("--authorization", required=False, default="unspecified",
                    help='e.g. "hackerone:company", "explicit-permission",'
                         ' "coordinated-disclosure", "out-of-scope-passive"')
    ap.add_argument("--result-summary", required=False, default="")
    ap.add_argument("--tail", type=int, default=0,
                    help="Show last N entries instead of writing")
    args = ap.parse_args()

    if args.tail:
        for entry in tail(args.tail):
            print(json.dumps(entry, ensure_ascii=False, indent=2))
        return

    if not args.target or not args.mode:
        sys.exit("Need --target and --mode (or --tail N)")

    entry = log_action(
        target=args.target,
        mode=args.mode,
        tools=args.tools.split(",") if args.tools else [],
        authorization=args.authorization,
        result_summary=args.result_summary,
    )
    print(f"[+] Logged: {entry['timestamp']} {args.target} ({args.mode})")
    print(f"[+] File: {LOG_FILE}")


if __name__ == "__main__":
    main()
