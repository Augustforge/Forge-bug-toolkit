#!/usr/bin/env python3
"""
Orphaned-TVL / deprecated-contract enumerator (on-chain surface triage).

An attacker enumerates EVERY contract a protocol ever deployed, not just the
current in-scope ones. A deprecated/legacy contract that STILL holds a residual
balance runs old, pre-audit-era, unpatched code (no inflation guard, old
rounding, no reentrancy lock) on live money nobody watches — the highest-EV
surface for a known-class bug.

    Thetanuts Finance 2026 ($2.1M): a vault "migrated from years ago" still held
    option-token TVL -> totalSupply driven to ~0 -> integer-division mint/redeem
    inflation (taxonomy 8.6 free-mint variant). Whitehat rescued ~$2M off the
    same orphaned surface.

This is the inverse of "deployed != repo HEAD" (Templar): here deprecated != value-free.
See: methodology/mythos_techniques.md T1 (deployment-set / orphaned-TVL lens),
     methodology/hypothesis_taxonomy.md Cat 8.6.

What it does (heuristic, NOT proof of a bug):
  1. Lists every contract a deployer address CREATED (direct txlist + factory
     internal-create via txlistinternal).
  2. For each created contract: native balance + ERC-20 balances (tokens
     discovered from its transfer history).
  3. Flags any contract still holding value = candidate orphaned surface ->
     fetch its (old) source (`fetch_source.py`) and run the full taxonomy
     against THAT version, not HEAD.

Etherscan V2 multichain API. Key from env or .env
(ETHERSCAN_API_KEY). V2 uses a single key across 60+ chains via `chainid`.

Usage:
    py -3 -X utf8 orphaned_tvl_enum.py --deployer 0x... --chain eth
    py -3 -X utf8 orphaned_tvl_enum.py --deployer 0x... --chain eth --json out.json
    py -3 -X utf8 orphaned_tvl_enum.py --deployer 0x... --min-native 0.001

    --deployer   EOA or factory contract that created the protocol's contracts
    --chain      eth|bsc|polygon|arbitrum|optimism|base|avalanche|fantom (default eth)
    --min-native ETH/native threshold to flag a contract on native alone (default 0.005)
    --json       also write structured results to a JSON file
    --all        show every created contract (default: only those holding value)
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

CHAIN_IDS = {
    "eth": 1, "ethereum": 1,
    "bsc": 56, "binance": 56,
    "polygon": 137, "matic": 137,
    "arbitrum": 42161, "arb": 42161,
    "optimism": 10, "op": 10,
    "base": 8453,
    "avalanche": 43114, "avax": 43114,
    "fantom": 250, "ftm": 250,
}

API = "https://api.etherscan.io/v2/api"


def load_key():
    key = os.getenv("ETHERSCAN_API_KEY", "")
    if key:
        return key
    # fall back to .env (this file lives in scripts/web3/detectors/)
    env = Path(__file__).resolve().parents[3] / ".env"
    if env.exists():
        for ln in env.read_text(encoding="utf-8", errors="replace").splitlines():
            if ln.strip().startswith("ETHERSCAN_API_KEY="):
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


KEY = load_key()


def call(chainid, params, tries=3):
    p = {"chainid": chainid, "apikey": KEY, **params}
    for attempt in range(tries):
        try:
            r = requests.get(API, params=p, timeout=30)
            time.sleep(0.22)  # stay under rate limit
            if r.status_code != 200:
                continue
            data = r.json()
            # status "0" with "No transactions found" is a valid empty result
            return data
        except Exception:
            time.sleep(0.5 * (attempt + 1))
    return {"status": "0", "result": []}


def created_contracts(chainid, deployer):
    """Direct creations (txlist, to == '') + factory creations (txlistinternal, type create)."""
    found = {}  # addr -> creation_block
    # direct EOA deployments
    d = call(chainid, {"module": "account", "action": "txlist",
                       "address": deployer, "sort": "asc",
                       "startblock": 0, "endblock": 99999999})
    if isinstance(d.get("result"), list):
        for tx in d["result"]:
            ca = (tx.get("contractAddress") or "").lower()
            if ca and (tx.get("to") in ("", None)):
                found[ca] = tx.get("blockNumber")
    # factory / internal creations (deployer may itself be a factory contract)
    di = call(chainid, {"module": "account", "action": "txlistinternal",
                        "address": deployer, "sort": "asc",
                        "startblock": 0, "endblock": 99999999})
    if isinstance(di.get("result"), list):
        for tx in di["result"]:
            if (tx.get("type") == "create") and tx.get("contractAddress"):
                found[tx["contractAddress"].lower()] = tx.get("blockNumber")
    return found


def native_balance(chainid, addr):
    d = call(chainid, {"module": "account", "action": "balance",
                       "address": addr, "tag": "latest"})
    try:
        return int(d.get("result", 0)) / 1e18
    except (ValueError, TypeError):
        return 0.0


def token_holdings(chainid, addr):
    """Discover ERC-20s the contract touched, then query current balance of each."""
    holdings = {}
    d = call(chainid, {"module": "account", "action": "tokentx",
                       "address": addr, "sort": "asc",
                       "startblock": 0, "endblock": 99999999, "offset": 0, "page": 1})
    if not isinstance(d.get("result"), list):
        return holdings
    seen = {}
    for ev in d["result"]:
        ct = (ev.get("contractAddress") or "").lower()
        if ct and ct not in seen:
            seen[ct] = {
                "symbol": ev.get("tokenSymbol", "?"),
                "decimals": int(ev.get("tokenDecimal") or 18),
            }
    for ct, meta in seen.items():
        b = call(chainid, {"module": "account", "action": "tokenbalance",
                           "contractaddress": ct, "address": addr, "tag": "latest"})
        try:
            raw = int(b.get("result", 0))
        except (ValueError, TypeError):
            raw = 0
        if raw > 0:
            holdings[ct] = {
                "symbol": meta["symbol"],
                "amount": raw / (10 ** meta["decimals"]),
                "raw": raw,
            }
    return holdings


# Generous substring match (compound names: arkPaused, isRetired, strategyDisabled) — bias to
# PRECISION: any pause/exclude-ish token in an aggregate loop → assume it filters → skip (no cry-wolf).
PAUSE_FLAG = re.compile(r"(paused|isactive|deprecat|offboard|retired|disabled|inactive|excluded|capped|whenNotPaused|removed|\bstatus\b|whitelist)", re.I)
NAV_ACCUM = re.compile(r"\b(nav|totalAssets|totalValue|collateralValue|totalManaged|aum|_totalSupply|assetsUnderManagement|totalWeight)\b", re.I)
LOOP = re.compile(r"\b(for|while|forEach|\.iter\(|\.map\()\b")
ACCUM_OP = re.compile(r"(\+=|\.add\(|=\s*\w+\s*\+)")


def scan_paused_in_formula(src):
    """Cat 3.15 source-scan: an aggregate (NAV/totalAssets) loop that sums components
    WITHOUT excluding paused/capped/deprecated ones, in a repo that DOES define such flags
    (Summer.fi Lazy Summer 2026-07-06 $6.04M — capped Ark stayed weighted in NAV)."""
    from _boundary_util import func_spans, iter_source_files
    exts = (".sol", ".rs", ".cairo", ".vy", ".move")
    repo_has_pause = False
    files = list(iter_source_files(src, exts, extra_skip=("test", "mock")))
    for p in files:
        try:
            if PAUSE_FLAG.search(open(p, encoding="utf-8", errors="ignore").read()):
                repo_has_pause = True
                break
        except OSError:
            pass
    findings = []
    for p in files:
        try:
            lines = open(p, encoding="utf-8", errors="ignore").read().splitlines()
        except OSError:
            continue
        for (s, e) in func_spans(lines):
            body = "\n".join(lines[s:e + 1])
            if not (NAV_ACCUM.search(body) and LOOP.search(body) and ACCUM_OP.search(body)):
                continue
            if PAUSE_FLAG.search(body):
                continue  # loop already references a pause/cap flag — likely excludes it
            findings.append({"file": p, "line": s + 1,
                             "code": lines[s].strip()[:160],
                             "why": "aggregate (NAV/totalAssets) loop sums components with NO paused/capped/deprecated filter"
                                    + (" — repo DEFINES pause/cap flags elsewhere (Cat 3.15 Summer.fi)" if repo_has_pause else "")})
    return findings


def main():
    ap = argparse.ArgumentParser(description="orphaned-TVL enumerator (T1 lens, Cat 8.6) + paused-in-formula source scan (Cat 3.15)")
    ap.add_argument("--deployer", help="EOA or factory that created the protocol's contracts (on-chain mode)")
    ap.add_argument("--src", help="source dir/file — run Cat 3.15 paused-but-in-formula source scan instead of on-chain enum")
    ap.add_argument("--chain", default="eth", help="chain alias (default eth)")
    ap.add_argument("--min-native", type=float, default=0.005, help="native threshold to flag (default 0.005)")
    ap.add_argument("--json", dest="json_out", help="write results to JSON")
    ap.add_argument("--all", action="store_true", help="show every created contract, not only funded ones")
    args = ap.parse_args()

    if args.src:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        findings = scan_paused_in_formula(args.src)
        for f in findings:
            print("%s:%d\n    %s\n    [Cat 3.15 · HIGH] %s\n" % (f["file"], f["line"], f["code"], f["why"]))
        print("--- %d aggregate loop(s) flagged (paused-but-in-formula). Depth-trace: does a cap/pause path leave the component in NAV? ---" % len(findings))
        if args.json_out:
            Path(args.json_out).write_text(json.dumps(findings, indent=2), encoding="utf-8")
        return 0

    if not args.deployer:
        print("provide --deployer (on-chain enum) OR --src (Cat 3.15 source scan)", file=sys.stderr)
        return 2

    if not KEY:
        print("ETHERSCAN_API_KEY not set (env or .env)", file=sys.stderr)
        return 2
    chainid = CHAIN_IDS.get(args.chain.lower())
    if not chainid:
        print("unknown chain: %s (have: %s)" % (args.chain, ", ".join(sorted(set(CHAIN_IDS)))), file=sys.stderr)
        return 2

    deployer = args.deployer.lower()
    print("enumerating contracts created by %s on %s (chainid %d)..." % (deployer, args.chain, chainid))
    created = created_contracts(chainid, deployer)
    print("found %d created contract(s); balance-checking each...\n" % len(created))

    results = []
    for addr, blk in created.items():
        nat = native_balance(chainid, addr)
        toks = token_holdings(chainid, addr)
        funded = (nat >= args.min_native) or bool(toks)
        results.append({
            "address": addr, "creation_block": blk,
            "native": nat, "tokens": toks, "funded": funded,
        })

    results.sort(key=lambda r: (not r["funded"], -r["native"]))
    shown = results if args.all else [r for r in results if r["funded"]]

    print("orphaned-TVL scan: %d created, %d still holding value (flagged)" %
          (len(results), sum(r["funded"] for r in results)))
    print("Each flagged contract = fetch its OLD source (fetch_source.py) + run full taxonomy vs THAT version.")
    print("-" * 72)
    for r in shown:
        tag = "[FUNDED]" if r["funded"] else "[empty]"
        print("%s %s  (created block %s)" % (tag, r["address"], r["creation_block"]))
        if r["native"] > 0:
            print("    native: %.6f" % r["native"])
        for ct, t in r["tokens"].items():
            print("    %s: %.6f  (%s)" % (t["symbol"], t["amount"], ct))

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(results, indent=2), encoding="utf-8")
        print("-" * 72)
        print("wrote %d records -> %s" % (len(results), args.json_out))

    return 0


if __name__ == "__main__":
    sys.exit(main())
