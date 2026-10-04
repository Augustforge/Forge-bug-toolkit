#!/usr/bin/env python3
"""slot_leader_monitor.py — track sandwich risk per slot leader."""
import argparse, json, sys
import urllib.request
from collections import defaultdict
from pathlib import Path


def rpc_call(rpc_url: str, method: str, params: list) -> dict | None:
    try:
        payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        req = urllib.request.Request(rpc_url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"[!] RPC: {e}", file=sys.stderr)
        return None


def get_leader_schedule(rpc_url: str, epoch: int | None) -> dict | None:
    params = [epoch] if epoch is not None else []
    r = rpc_call(rpc_url, "getLeaderSchedule", params)
    return r.get("result") if r else None


def main():
    ap = argparse.ArgumentParser(description="Slot leader schedule analyzer (sandwich risk)")
    ap.add_argument("--rpc", default="https://api.mainnet-beta.solana.com")
    ap.add_argument("--epoch", type=int, default=None)
    ap.add_argument("--flag-known-malicious", action="append", default=[], help="Validator pubkey to flag")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    schedule = get_leader_schedule(args.rpc, args.epoch)
    if not schedule:
        print(f"[!] Could not fetch leader schedule", file=sys.stderr)
        sys.exit(1)

    flagged_slots = []
    for validator, slots in schedule.items():
        if validator in args.flag_known_malicious:
            for s in slots:
                flagged_slots.append({"validator": validator, "slot": s, "risk": "known_malicious_sandwicher"})

    result = {
        "total_validators": len(schedule),
        "total_slots": sum(len(s) for s in schedule.values()),
        "flagged_slots_count": len(flagged_slots),
        "flagged_slots_sample": flagged_slots[:50],
        "advice": "Across-slot sandwich = 93% of Solana sandwiches. Submit txs via Jito + Paladin + bloXroute multi-path for protection.",
    }
    print(json.dumps({"summary": {k: v for k, v in result.items() if k != "flagged_slots_sample"}}, indent=2))
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "leader_schedule.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
