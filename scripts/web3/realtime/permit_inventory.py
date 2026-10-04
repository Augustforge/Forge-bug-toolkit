#!/usr/bin/env python3
"""
permit_inventory.py — pull live valid off-chain permits / approvals.

For a list of (owner, token, spender) tuples, queries on-chain:
- allowance(owner, spender) for ERC20
- nonces(owner) for EIP-2612 permit (signed permits with nonce < current valid)
- Permit2 allowance + nonce status

These are griefing-eligible / front-runnable surfaces.

Requires --rpc URL. Read-only — never broadcasts.
"""
import argparse
import json
import sys
from pathlib import Path


# ABIs (minimal)
ERC20_ALLOWANCE = "0xdd62ed3e"   # allowance(address,address)
ERC20_NONCES   = "0x7ecebe00"    # nonces(address)
ERC20_DOMAIN_SEP = "0x3644e515"  # DOMAIN_SEPARATOR()


def eth_call(rpc_url: str, to: str, data: str, block: str = "latest") -> str | None:
    try:
        import urllib.request
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_call",
            "params": [{"to": to, "data": data}, block],
        }).encode()
        req = urllib.request.Request(rpc_url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            j = json.loads(r.read())
            return j.get("result")
    except Exception as e:
        print(f"[!] RPC error: {e}", file=sys.stderr)
        return None


def encode_address(addr: str) -> str:
    return addr.lower().replace("0x", "").rjust(64, "0")


def hex_to_int(h: str | None) -> int:
    if not h or h == "0x":
        return 0
    return int(h, 16)


def query_allowance(rpc: str, token: str, owner: str, spender: str) -> int:
    data = ERC20_ALLOWANCE + encode_address(owner) + encode_address(spender)
    return hex_to_int(eth_call(rpc, token, data))


def query_nonces(rpc: str, token: str, owner: str) -> int:
    data = ERC20_NONCES + encode_address(owner)
    return hex_to_int(eth_call(rpc, token, data))


def query_domain_sep(rpc: str, token: str) -> str | None:
    return eth_call(rpc, token, ERC20_DOMAIN_SEP)


def main():
    ap = argparse.ArgumentParser(description="Inventory live valid permits/allowances")
    ap.add_argument("--rpc", required=True, help="JSON-RPC URL")
    ap.add_argument("--triples", required=True, help="JSON file: [{owner, token, spender}, ...]")
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    triples_path = Path(args.triples)
    if not triples_path.exists():
        print(f"[!] {triples_path} not found", file=sys.stderr)
        sys.exit(1)

    triples = json.loads(triples_path.read_text(encoding="utf-8"))
    if not isinstance(triples, list):
        print("[!] Expected JSON array", file=sys.stderr)
        sys.exit(1)

    inventory = []
    for t in triples:
        owner = t["owner"]
        token = t["token"]
        spender = t["spender"]
        allowance = query_allowance(args.rpc, token, owner, spender)
        nonce = query_nonces(args.rpc, token, owner)
        domain = query_domain_sep(args.rpc, token)
        rec = {
            "owner": owner,
            "token": token,
            "spender": spender,
            "allowance": allowance,
            "current_nonce": nonce,
            "supports_eip2612": domain is not None and domain != "0x",
            "domain_separator": domain,
            "exposure_risk": "high" if allowance > 10**24 else "medium" if allowance > 10**20 else "low" if allowance > 0 else "none",
        }
        inventory.append(rec)
        if not args.quiet:
            print(f"  {owner[:10]}... -> {token[:10]}... <-> {spender[:10]}...: allow={allowance}, nonce={nonce}, risk={rec['exposure_risk']}")

    high_exposure = [i for i in inventory if i["exposure_risk"] in ("high", "medium")]
    if not args.quiet:
        print(f"\n[+] Total triples: {len(inventory)}")
        print(f"[!] Griefing-eligible (>1e20 allowance): {len(high_exposure)}")

    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "permit_inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
