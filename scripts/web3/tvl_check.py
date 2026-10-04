#!/usr/bin/env python3
"""
TVL check via DeFiLlama API.
Used for severity calc: Critical = >$1M at risk.

Usage:
    python3 tvl_check.py --protocol uniswap
    python3 tvl_check.py --address 0x...        (lookup by contract)
"""

import argparse
import json
import sys

import requests


def get_protocol_tvl(slug: str, chain_filter: str | None = None) -> dict:
    try:
        r = requests.get(f"https://api.llama.fi/protocol/{slug}", timeout=30)
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}"}
        d = r.json()
        chain_tvls = d.get("currentChainTvls", {}) or {}
        chains = d.get("chains", []) or []

        primary_chain = None
        primary_tvl = 0
        if chain_tvls:
            primary_chain = max(chain_tvls, key=chain_tvls.get)
            primary_tvl = chain_tvls.get(primary_chain, 0)

        if chain_filter:
            chain_filter_norm = chain_filter.lower()
            for key in chain_tvls:
                if key.lower() == chain_filter_norm:
                    primary_tvl = chain_tvls[key]
                    primary_chain = key
                    break

        is_solana = (
            "Solana" in chain_tvls
            or "solana" in [c.lower() for c in chains]
            or (primary_chain and primary_chain.lower() == "solana")
        )
        chain_type = "solana" if is_solana else "evm"

        return {
            "name": d.get("name"),
            "category": d.get("category"),
            "tvl_usd": primary_tvl or sum(chain_tvls.values() or [0]),
            "primary_chain": primary_chain,
            "chain_type": chain_type,
            "chain_tvls": chain_tvls,
            "chains": chains,
            "audits": d.get("audits", "0"),
            "audit_links": d.get("audit_links", []),
            "url": d.get("url"),
        }
    except Exception as e:
        return {"error": str(e)}


def get_solana_chain_tvl() -> dict:
    """Return overall Solana chain TVL from DeFiLlama."""
    try:
        r = requests.get("https://api.llama.fi/v2/chains", timeout=30)
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}"}
        for c in r.json():
            if c.get("name", "").lower() == "solana":
                return {
                    "chain": "Solana",
                    "tvl_usd": c.get("tvl", 0),
                    "tokenSymbol": c.get("tokenSymbol"),
                    "gecko_id": c.get("gecko_id"),
                }
        return {"error": "Solana not found in chains list"}
    except Exception as e:
        return {"error": str(e)}


def find_protocol_by_address(address: str) -> dict:
    """Search DeFiLlama protocols list for matching contract."""
    try:
        r = requests.get("https://api.llama.fi/protocols", timeout=30)
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}"}
        addr_lower = address.lower()
        for p in r.json():
            ct = p.get("address", "")
            if ct and addr_lower in ct.lower():
                return {
                    "name": p.get("name"),
                    "slug": p.get("slug"),
                    "category": p.get("category"),
                    "tvl_usd": p.get("tvl", 0),
                    "chains": p.get("chains", []),
                    "url": p.get("url"),
                }
        return {"error": "address not found in DeFiLlama protocols index"}
    except Exception as e:
        return {"error": str(e)}


def severity_from_tvl(tvl: float) -> str:
    if tvl >= 1_000_000:
        return "critical-eligible"
    if tvl >= 100_000:
        return "high-eligible"
    if tvl >= 10_000:
        return "medium-eligible"
    return "low-eligible"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol", help="DeFiLlama slug e.g. uniswap")
    ap.add_argument("--address", help="Contract address")
    ap.add_argument("--chain", help="Filter to specific chain (e.g. Ethereum, Solana, Arbitrum)")
    ap.add_argument("--solana-overall", action="store_true", help="Get total Solana chain TVL")
    ap.add_argument("--output", help="Save JSON to file")
    args = ap.parse_args()

    if args.solana_overall:
        result = get_solana_chain_tvl()
    elif args.protocol:
        result = get_protocol_tvl(args.protocol, chain_filter=args.chain)
    elif args.address:
        result = find_protocol_by_address(args.address)
    else:
        sys.exit("Need --protocol, --address, or --solana-overall")

    if "tvl_usd" in result:
        result["severity_eligibility"] = severity_from_tvl(result["tvl_usd"])

    out = json.dumps(result, indent=2, default=str)
    if args.output:
        with open(args.output, "w") as f:
            f.write(out)
    print(out)


if __name__ == "__main__":
    main()
