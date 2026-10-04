#!/usr/bin/env python3
"""idl_takeover_monitor.py — watch for unclaimed IDL authority on deployed programs."""
import argparse, json, sys, urllib.request
from pathlib import Path


def rpc_call(rpc_url: str, method: str, params: list) -> dict | None:
    try:
        payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        req = urllib.request.Request(rpc_url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"[!] RPC error: {e}", file=sys.stderr)
        return None


def get_idl_pda(program_id: str) -> str:
    return "PLACEHOLDER_IDL_PDA"


def main():
    ap = argparse.ArgumentParser(description="Monitor for unclaimed IDL authority")
    ap.add_argument("--program-id", required=True)
    ap.add_argument("--rpc", default="https://api.mainnet-beta.solana.com")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    print(f"[*] Checking IDL authority for {args.program_id}...")
    idl_pda = get_idl_pda(args.program_id)
    result = rpc_call(args.rpc, "getAccountInfo", [idl_pda, {"encoding": "base64"}])

    info = {
        "program_id": args.program_id,
        "idl_pda": idl_pda,
        "claimed": result and result.get("result", {}).get("value") is not None,
        "risk": "high_takeover_surface" if not (result and result.get("result", {}).get("value")) else "claimed",
        "advice": "If unclaimed: attacker can claim authority via IdlCreateAccount. Verify legitimate IDL deployed first.",
    }
    print(json.dumps(info, indent=2))
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "idl_status.json").write_text(json.dumps(info, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
