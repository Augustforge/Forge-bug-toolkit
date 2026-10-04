#!/usr/bin/env python3
"""
watcher.py — Main mempool watcher loop.

Loads chain adapters + patterns, runs async event loop, dispatches matches
to responders.

Usage:
  python3 watcher.py --chains eth --patterns large_admin_withdrawal --dry-run
  python3 watcher.py --chains eth,arb,base --patterns all
  python3 watcher.py --chains eth --patterns all --mock          # use mock txs (no live mempool)
"""
import argparse
import asyncio
import importlib
import json
import sys
import time
from pathlib import Path

try:
    import yaml
except ImportError:
    print("[err] pyyaml required", file=sys.stderr)
    sys.exit(1)

THIS_DIR = Path(__file__).parent
PATTERNS_DIR = THIS_DIR / "patterns"
CHAINS_DIR = THIS_DIR / "chains"
AUDIT_LOG = Path.home() / ".bbt" / "audit.log"


def load_patterns(names: list[str]) -> list[dict]:
    if not PATTERNS_DIR.is_dir():
        return []
    out = []
    if names == ["all"]:
        files = sorted(PATTERNS_DIR.glob("*.yaml"))
    else:
        files = [PATTERNS_DIR / f"{n}.yaml" for n in names]
    for f in files:
        if not f.exists():
            print(f"[warn] pattern not found: {f}", file=sys.stderr)
            continue
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "id" in data:
                out.append(data)
        except Exception as e:
            print(f"[warn] pattern {f.name} parse error: {e}", file=sys.stderr)
    return out


def load_chain(chain_id: str):
    """Dynamically import chain adapter."""
    name_map = {
        "eth": "ethereum",
        "ethereum": "ethereum",
        "arb": "arbitrum",
        "arbitrum": "arbitrum",
        "base": "base",
        "bsc": "bsc",
        "sol": "solana",
        "solana": "solana",
    }
    mod_name = name_map.get(chain_id, chain_id)
    sys.path.insert(0, str(CHAINS_DIR.parent))
    try:
        mod = importlib.import_module(f"mempool.chains.{mod_name}")
        return mod
    except ImportError as e:
        # Fallback: import via plain path
        try:
            sys.path.insert(0, str(CHAINS_DIR))
            mod = importlib.import_module(mod_name)
            return mod
        except ImportError:
            print(f"[err] chain adapter {chain_id} not loadable: {e}", file=sys.stderr)
            return None


EVM_CHAINS = {"eth", "ethereum", "arb", "arbitrum", "base", "bsc", "optimism", "op", "polygon"}


def match_pattern(tx: dict, pattern: dict) -> tuple[bool, list[str]]:
    """Returns (matched, reasons)."""
    applies = set(pattern.get("applies_to", []))
    chain = tx["chain"]
    # Family expansion: "evm" matches any EVM chain
    chain_family = "evm" if chain in EVM_CHAINS else chain
    if chain not in applies and chain_family not in applies and "any" not in applies:
        return False, [f"chain mismatch: tx.chain={chain}, pattern.applies_to={list(applies)}"]
    m = pattern.get("match", {})
    reasons = []

    # Function selector match
    selectors = m.get("function_selectors") or m.get("function_selector") or []
    if isinstance(selectors, str):
        selectors = [selectors]
    if selectors and tx.get("selector") in [s.lower() for s in selectors]:
        reasons.append(f"selector match: {tx['selector']}")
    elif selectors:
        return False, [f"selector miss: {tx['selector']} not in {selectors}"]

    # Value check (approximation in ETH/native; real conversion need price feed)
    value_min_usd = m.get("value_min_usd")
    if value_min_usd:
        eth_value = tx.get("value", 0) / 1e18
        approx_eth_price_usd = 3000  # placeholder; real-world hook to price feed
        usd_value = eth_value * approx_eth_price_usd
        if usd_value < value_min_usd:
            return False, [f"value below threshold: ${usd_value:.0f} < ${value_min_usd}"]
        reasons.append(f"value ${usd_value:.0f} >= ${value_min_usd}")

    return True, reasons


def write_audit_log(entry: dict):
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def dispatch(tx: dict, pattern: dict, reasons: list[str], dry_run: bool):
    disposition = pattern.get("disposition", "alert_only")
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pattern": pattern["id"],
        "chain": tx["chain"],
        "tx_hash": tx.get("tx_hash"),
        "from": tx.get("from"),
        "to": tx.get("to"),
        "value": tx.get("value"),
        "selector": tx.get("selector"),
        "disposition": disposition,
        "fired": not dry_run,
        "reasons": reasons,
    }
    write_audit_log(entry)
    severity = pattern.get("severity", "?")
    print(f"[{severity.upper()}] {pattern['id']} on {tx['chain']} — "
          f"{tx.get('tx_hash', '?')[:18]} ({disposition}) {'[DRY]' if dry_run else ''}")
    for r in reasons:
        print(f"    · {r}")

    if dry_run:
        return

    try:
        sys.path.insert(0, str(THIS_DIR.parent))
        from mempool.responders import dispatch_disposition
        result = dispatch_disposition(entry, dry_run=False)
        if result.get("status") == "gated":
            print(f"[gate] {disposition}: {result.get('reason', '?')}")
    except ImportError as e:
        print(f"[warn] responders.py not loadable: {e}", file=sys.stderr)


async def run_chain(chain_id: str, patterns: list[dict], dry_run: bool, mock: bool, mock_n: int):
    print(f"[info] starting watcher for {chain_id} with {len(patterns)} pattern(s)")

    adapter_mod = load_chain(chain_id)
    if not adapter_mod:
        return

    if mock and hasattr(adapter_mod, "mock_iter_pending"):
        for tx in adapter_mod.mock_iter_pending(mock_n):
            for p in patterns:
                ok, reasons = match_pattern(tx, p)
                if ok:
                    dispatch(tx, p, reasons, dry_run)
        return

    try:
        adapter_class = getattr(adapter_mod, "EthereumAdapter", None) or \
                        getattr(adapter_mod, f"{chain_id.capitalize()}Adapter", None)
        if not adapter_class:
            print(f"[err] no Adapter class in {chain_id}", file=sys.stderr)
            return
        adapter = adapter_class()
        async for tx in adapter.iter_pending():
            for p in patterns:
                ok, reasons = match_pattern(tx, p)
                if ok:
                    dispatch(tx, p, reasons, dry_run)
    except Exception as e:
        print(f"[err] {chain_id} watcher crashed: {e}", file=sys.stderr)


async def main_async(args):
    patterns = load_patterns(args.patterns.split(","))
    print(f"[info] loaded {len(patterns)} pattern(s): {[p['id'] for p in patterns]}")

    chains = args.chains.split(",")
    tasks = [run_chain(c, patterns, args.dry_run, args.mock, args.mock_n) for c in chains]
    await asyncio.gather(*tasks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chains", required=True, help="Comma-separated chain IDs (eth,arb,base,bsc,sol)")
    ap.add_argument("--patterns", required=True, help="Comma-separated pattern IDs OR 'all'")
    ap.add_argument("--dry-run", action="store_true", help="Don't dispatch; log only")
    ap.add_argument("--mock", action="store_true", help="Use mock_iter_pending (testing)")
    ap.add_argument("--mock-n", type=int, default=5, help="Number of mock txs to generate")
    args = ap.parse_args()

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\n[info] interrupted, exiting")


if __name__ == "__main__":
    main()
