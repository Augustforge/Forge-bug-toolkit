#!/usr/bin/env python3
"""
selector_enum.py — Enumerate function selectors from bytecode.

Finds all 4-byte selectors hardcoded in bytecode (function dispatcher).
Then attempts to resolve names via 4byte directory / Openchain.

Useful to find HIDDEN admin functions in unverified contracts.

Usage:
  python3 selector_enum.py --bytecode-file path/to/bytecode.hex --output sessions/X/
  python3 selector_enum.py --address 0xABC --chain monad --output ...
"""

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# EVM dispatcher pattern: PUSH4 <selector> EQ
SELECTOR_RE = re.compile(r"63([0-9a-fA-F]{8})14")
# Alternative: PUSH4 <selector> ... EQ patterns
SELECTOR_RE_ALT = re.compile(r"63([0-9a-fA-F]{8})(?:1614|14|81)")


def extract_selectors(bytecode_hex: str) -> set[str]:
    """Extract candidate 4-byte selectors from bytecode."""
    bc = bytecode_hex.lower().replace("0x", "")
    selectors = set()
    for m in SELECTOR_RE.finditer(bc):
        selectors.add("0x" + m.group(1))
    for m in SELECTOR_RE_ALT.finditer(bc):
        selectors.add("0x" + m.group(1))
    return selectors


def resolve_selector_4byte(selector: str) -> list[str]:
    """Query 4byte.directory (rate-limited) for selector → name."""
    url = f"https://www.4byte.directory/api/v1/signatures/?hex_signature={selector}"
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read())
            return [item["text_signature"] for item in data.get("results", [])]
    except Exception:
        return []


def resolve_selector_openchain(selector: str) -> list[str]:
    """Query Openchain (no rate limit, more entries)."""
    url = f"https://api.openchain.xyz/signature-database/v1/lookup?function={selector}"
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read())
            results = data.get("result", {}).get("function", {}).get(selector, [])
            return [item["name"] for item in results]
    except Exception:
        return []


def fetch_bytecode_cast(address: str, chain: str) -> str | None:
    rpc_urls = {
        "ethereum": "https://eth.llamarpc.com",
        "arbitrum": "https://arb1.arbitrum.io/rpc",
        "optimism": "https://mainnet.optimism.io",
        "base": "https://mainnet.base.org",
        "monad": "https://rpc.monad.xyz",
    }
    rpc = rpc_urls.get(chain.lower(), rpc_urls["ethereum"])
    try:
        result = subprocess.run(
            ["cast", "code", address, "--rpc-url", rpc],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip() != "0x":
            return result.stdout.strip()
    except Exception:
        return None
    return None


# Admin/dangerous function patterns to flag
ADMIN_PATTERNS = re.compile(
    r"^(setOwner|transferOwnership|upgradeToAndCall|_authorizeUpgrade|"
    r"withdraw|emergency|pause|unpause|setFee|setRouter|"
    r"addMinter|removeMinter|mint|burn|migrate|init|"
    r"setAdmin|grantRole|revokeRole)\b",
    re.IGNORECASE,
)


def classify_function(name: str) -> str:
    """Classify a function name."""
    if ADMIN_PATTERNS.search(name):
        return "ADMIN/DANGER"
    if name.startswith(("view", "get", "is")) or name in ("name", "symbol", "decimals", "totalSupply"):
        return "view"
    return "normal"


def main():
    p = argparse.ArgumentParser(description="Enumerate selectors from bytecode")
    p.add_argument("--bytecode-file")
    p.add_argument("--address")
    p.add_argument("--chain", default="ethereum")
    p.add_argument("--output", required=True)
    p.add_argument("--resolve", action="store_true", help="Query openchain for names (network)")
    args = p.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.bytecode_file:
        bc = Path(args.bytecode_file).read_text(encoding="utf-8").strip()
    elif args.address:
        bc = fetch_bytecode_cast(args.address, args.chain)
        if not bc:
            print("ERROR: bytecode fetch failed")
            return 1
    else:
        print("ERROR: provide --bytecode-file or --address")
        return 1

    selectors = extract_selectors(bc)
    print(f"[*] Found {len(selectors)} candidate selectors in bytecode")

    resolved = {}
    if args.resolve:
        print("[*] Resolving via Openchain...")
        for sel in sorted(selectors):
            names = resolve_selector_openchain(sel)
            if not names:
                names = resolve_selector_4byte(sel)
            resolved[sel] = {
                "names": names,
                "classification": classify_function(names[0]) if names else "unknown",
            }
    else:
        resolved = {sel: {"names": [], "classification": "unknown"} for sel in sorted(selectors)}

    (output_dir / "selectors.json").write_text(json.dumps(resolved, indent=2), encoding="utf-8")

    # Markdown report
    md = ["# Function Selector Enumeration", "", f"Total selectors: {len(resolved)}", ""]
    admin_found = []
    for sel, info in resolved.items():
        if info["classification"] == "ADMIN/DANGER":
            admin_found.append((sel, info["names"]))
    if admin_found:
        md.append("## 🚨 Admin/Dangerous Functions")
        for sel, names in admin_found:
            md.append(f"- `{sel}` — {', '.join(names) if names else 'unresolved'}")
        md.append("")
    md.append("## All Selectors")
    for sel in sorted(resolved.keys()):
        names_str = ", ".join(resolved[sel]["names"][:3]) if resolved[sel]["names"] else "(unresolved)"
        md.append(f"- `{sel}` — {names_str}")
    (output_dir / "selectors.md").write_text("\n".join(md), encoding="utf-8")

    print(f"[+] Output: {output_dir}/selectors.{{json,md}}")
    if admin_found:
        print(f"[!] {len(admin_found)} ADMIN/DANGER selectors found")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
