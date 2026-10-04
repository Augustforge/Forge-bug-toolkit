#!/usr/bin/env python3
"""
fork_runner.py — Submit transaction to forked validator + diff state.

Loads `fork_state.json` from spawn_validator.sh, reads target accounts state
BEFORE tx, submits the tx, reads state AFTER, diffs:
  - lamport balance changes per account
  - data hash changes (proof of mutation)
  - tx success/failure + logs

Usage:
    python3 fork_runner.py --fork ./fork_state.json --tx-base64 BASE64_TX \\
        --watch-account PUBKEY1 --watch-account PUBKEY2 \\
        --output sessions/$TARGET/poc/run1/

    python3 fork_runner.py --fork ./fork_state.json --tx-file tx.bin \\
        --watch-accounts-file accounts.txt --output ...

Output:
    state_before.json + state_after.json + diff.json + verdict.json
"""
import argparse
import base64
import hashlib
import json
import sys
import urllib.request
from pathlib import Path


def rpc(rpc_url: str, method: str, params: list) -> dict:
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(rpc_url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": {"message": str(e)}}


def get_account_state(rpc_url: str, pubkey: str) -> dict:
    r = rpc(rpc_url, "getAccountInfo", [pubkey, {"encoding": "base64", "commitment": "processed"}])
    val = (r.get("result") or {}).get("value")
    if not val:
        return {"exists": False}
    data_b64 = val.get("data", ["", ""])[0]
    data_bytes = base64.b64decode(data_b64) if data_b64 else b""
    return {
        "exists": True,
        "lamports": val.get("lamports", 0),
        "owner": val.get("owner"),
        "executable": val.get("executable", False),
        "data_len": len(data_bytes),
        "data_hash": hashlib.sha256(data_bytes).hexdigest(),
        "data_b64_first128": data_b64[:128],
    }


def diff_state(before: dict, after: dict) -> dict:
    if not before.get("exists") and after.get("exists"):
        return {"change_type": "account_created", "after": after}
    if before.get("exists") and not after.get("exists"):
        return {"change_type": "account_closed", "before": before}
    if not before.get("exists") and not after.get("exists"):
        return {"change_type": "no_account"}

    diffs = {}
    if before.get("lamports") != after.get("lamports"):
        delta = after["lamports"] - before["lamports"]
        diffs["lamport_delta"] = delta
        diffs["lamport_delta_sol"] = delta / 1_000_000_000
    if before.get("data_hash") != after.get("data_hash"):
        diffs["data_mutated"] = True
        diffs["data_len_before"] = before["data_len"]
        diffs["data_len_after"] = after["data_len"]
    if before.get("owner") != after.get("owner"):
        diffs["owner_changed"] = {"before": before["owner"], "after": after["owner"]}

    return diffs or {"change_type": "no_change"}


def submit_tx(rpc_url: str, tx_base64: str) -> dict:
    r = rpc(rpc_url, "sendTransaction", [
        tx_base64,
        {"encoding": "base64", "skipPreflight": False, "preflightCommitment": "processed"}
    ])
    if "error" in r:
        return {"submitted": False, "error": r["error"]}
    sig = r.get("result")

    confirm = rpc(rpc_url, "confirmTransaction", [sig, "processed"])
    return {"submitted": True, "signature": sig, "confirm": confirm.get("result")}


def get_tx_meta(rpc_url: str, signature: str) -> dict:
    r = rpc(rpc_url, "getTransaction", [
        signature,
        {"encoding": "json", "maxSupportedTransactionVersion": 0, "commitment": "processed"}
    ])
    res = r.get("result")
    if not res:
        return {"available": False}
    meta = res.get("meta", {}) or {}
    return {
        "available": True,
        "success": meta.get("err") is None,
        "err": meta.get("err"),
        "fee": meta.get("fee"),
        "compute_units_consumed": meta.get("computeUnitsConsumed"),
        "log_messages": meta.get("logMessages", [])[:30],
        "pre_balances": meta.get("preBalances", []),
        "post_balances": meta.get("postBalances", []),
    }


def verdict(diffs: dict, tx_meta: dict, success_invariants: list) -> dict:
    has_state_mutation = any(
        d.get("change_type") == "account_created"
        or d.get("change_type") == "account_closed"
        or d.get("data_mutated")
        or d.get("lamport_delta", 0) != 0
        or d.get("owner_changed")
        for d in diffs.values()
    )

    invariants_broken = []
    for inv in success_invariants:
        watch = inv.get("account")
        require = inv.get("require")
        d = diffs.get(watch, {})
        if require == "data_mutated" and not d.get("data_mutated"):
            invariants_broken.append({"invariant": inv, "actual": d, "broken": "expected data mutation"})
        elif require == "lamport_increase":
            expected = inv.get("min_delta", 1)
            if d.get("lamport_delta", 0) < expected:
                invariants_broken.append({"invariant": inv, "actual": d, "broken": f"expected lamport_delta >= {expected}"})
        elif require == "lamport_decrease":
            expected = inv.get("max_delta", -1)
            if d.get("lamport_delta", 0) > expected:
                invariants_broken.append({"invariant": inv, "actual": d, "broken": f"expected lamport_delta <= {expected}"})

    if not tx_meta.get("success"):
        return {"status": "TX_FAILED", "details": tx_meta.get("err"), "exploit": "unverified"}

    if invariants_broken:
        return {
            "status": "INVARIANT_BROKEN",
            "exploit": "CONFIRMED",
            "invariants_broken": invariants_broken,
            "state_mutation_observed": has_state_mutation,
        }

    if not success_invariants and has_state_mutation:
        return {
            "status": "STATE_MUTATED",
            "exploit": "needs_review",
            "diffs": {k: v for k, v in diffs.items() if v.get("change_type") != "no_change"},
        }

    return {"status": "NO_EXPLOIT", "exploit": "rejected_by_protocol"}


def main():
    ap = argparse.ArgumentParser(description="Submit tx to fork + diff state")
    ap.add_argument("--fork", required=True, help="fork_state.json from spawn_validator.sh")
    ap.add_argument("--tx-base64", help="Base64-encoded signed transaction")
    ap.add_argument("--tx-file", help="File with binary signed transaction (alternative to --tx-base64)")
    ap.add_argument("--watch-account", action="append", default=[], help="Account to monitor (repeatable)")
    ap.add_argument("--watch-accounts-file", help="File with one pubkey per line")
    ap.add_argument("--invariants", help="JSON file with success invariants list")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    fork = json.loads(Path(args.fork).read_text())
    rpc_url = fork["rpc"]

    watch_accounts = list(args.watch_account)
    if args.watch_accounts_file:
        watch_accounts.extend([
            line.strip() for line in Path(args.watch_accounts_file).read_text().splitlines()
            if line.strip()
        ])
    if not watch_accounts:
        print("[!] No --watch-account provided", file=sys.stderr)
        sys.exit(1)

    tx_b64 = args.tx_base64
    if args.tx_file:
        tx_b64 = base64.b64encode(Path(args.tx_file).read_bytes()).decode()
    if not tx_b64:
        print("[!] Provide --tx-base64 OR --tx-file", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Reading state BEFORE for {len(watch_accounts)} accounts...")
    state_before = {a: get_account_state(rpc_url, a) for a in watch_accounts}
    (out_dir / "state_before.json").write_text(json.dumps(state_before, indent=2))

    print(f"[*] Submitting transaction ({len(tx_b64)} chars base64)...")
    submit_result = submit_tx(rpc_url, tx_b64)
    if not submit_result.get("submitted"):
        print(f"[!] Tx submission failed: {submit_result.get('error')}")
        (out_dir / "verdict.json").write_text(json.dumps({
            "status": "SUBMIT_FAILED",
            "error": submit_result.get("error"),
        }, indent=2))
        sys.exit(2)

    signature = submit_result["signature"]
    print(f"[+] Tx submitted: {signature[:16]}...")

    print(f"[*] Reading state AFTER...")
    state_after = {a: get_account_state(rpc_url, a) for a in watch_accounts}
    (out_dir / "state_after.json").write_text(json.dumps(state_after, indent=2))

    print(f"[*] Diffing...")
    diffs = {a: diff_state(state_before[a], state_after[a]) for a in watch_accounts}
    (out_dir / "diff.json").write_text(json.dumps(diffs, indent=2))

    print(f"[*] Fetching tx meta + logs...")
    tx_meta = get_tx_meta(rpc_url, signature)
    (out_dir / "tx_meta.json").write_text(json.dumps(tx_meta, indent=2))

    invariants = []
    if args.invariants:
        invariants = json.loads(Path(args.invariants).read_text())

    final = verdict(diffs, tx_meta, invariants)
    final["signature"] = signature
    final["tx_compute_units"] = tx_meta.get("compute_units_consumed")
    (out_dir / "verdict.json").write_text(json.dumps(final, indent=2))

    print(f"\n[+] VERDICT: {final['status']}")
    print(f"    Exploit: {final.get('exploit', 'unknown')}")
    if final.get("invariants_broken"):
        for ib in final["invariants_broken"]:
            print(f"    BROKEN: {ib['broken']}")
    if final.get("diffs"):
        for acc, d in final["diffs"].items():
            print(f"    {acc[:16]}... -> {d}")

    print(f"\n[+] Saved to {out_dir}/")
    return 0 if final.get("exploit") == "CONFIRMED" else 1


if __name__ == "__main__":
    sys.exit(main())
