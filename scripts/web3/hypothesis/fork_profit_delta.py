#!/usr/bin/env python3
"""
fork_profit_delta.py — measured attacker balance-delta on a fork (AOE §3.1 fork-sim profit-oracle).

ROLE (AOE §1 / §3.1, mythos Mandate 0.10): this STRENGTHENS the existing T4 evidence-artifact /
Ehsan counterfactual — it is NOT "the first time we measure". T4 already requires severity numbers
quoted from ACTUAL fork output, not assumed. This adds one specific, testable input to that: the
attacker's ACTUAL balance delta (before/after) on the fork.

    balance-delta = balance_after(attacker) - balance_before(attacker)      # per asset, on a fork

🔴 magnitude = protocol_loss, NOT this number. The attacker balance-delta is the INPUT for the
down-guard / realism check (Mandate 0.10 role 3), NEVER the source of magnitude. The source of
magnitude is the victim-side protocol_loss (measured separately). This module refuses to label its
own output "magnitude".

🔴 Honest marks — the fork is a counterfactual-alone, not reality (Mandate 0.10 ceiling caveat).
These are printed WITH the number so the delta is never passed off as a clean measured fact:
  - competition-dependent value (MEV / backrun / sandwich) → `ceiling-not-measured`: an isolated
    fork has no competing searchers, so it OVER-states this value (real world = priority-fee
    auction + lost races). Flag it; do not bank it as measured.
  - liquidity-dependent value → `stale`: the fork is a single-block snapshot; live liquidity may
    differ, especially under stress (§2.3c). Pin to the fork block + flag "live may differ".
  - the fork does NOT simulate you being front-run / griefed. Always noted.

TWO ways to obtain before/after balances (kept separate so the delta math is unit-testable WITHOUT
a live fork — see `self-test`):
  1. injected maps (unit-test / offline): `delta --before before.json --after after.json`
  2. read from a fork via `cast` (run `onchain_poc_harness.py fork-up` first, do the exploit sends,
     snapshot before & after): `snapshot --rpc http://127.0.0.1:8545 --address 0x.. --token 0x..`

This module composes with `onchain_poc_harness.py` (which spins the fork + signs the exploit txs);
it does NOT duplicate signing/burner logic — it only READS balances and computes the delta. That is
the "raise the profit-delta calc into scripts/web3/" landing of AOE §3.1 [FIX-harness] / §9.6.

A balance map is `{"native": <int wei>, "<token addr>": <int raw units>, ...}`.

Usage:
    py -3 -X utf8 fork_profit_delta.py self-test
    py -3 -X utf8 fork_profit_delta.py snapshot --rpc http://127.0.0.1:8545 \
        --address 0xATTACKER --token 0xTOKEN --label before --out before.json
    py -3 -X utf8 fork_profit_delta.py delta --before before.json --after after.json \
        --competition-dependent --liquidity-dependent --json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional


# ──────────────────────────────────────────────────────────────────────────
# Pure delta math (unit-testable, NO I/O, NO fork required)
# ──────────────────────────────────────────────────────────────────────────

def compute_delta(before: Dict[str, int], after: Dict[str, int]) -> Dict[str, int]:
    """Per-asset attacker balance delta = after - before.

    Assets present in only one map are treated as 0 on the missing side (a token the attacker did
    not hold before but holds after is pure gain, and vice-versa). Values are raw integer balances
    (wei / token base units) — no decimals applied here; USD conversion is a separate opt-in step so
    the raw measurement stays exact.
    """
    assets = set(before) | set(after)
    return {a: int(after.get(a, 0)) - int(before.get(a, 0)) for a in sorted(assets)}


def delta_to_usd(delta: Dict[str, int],
                 prices_usd: Dict[str, float],
                 decimals: Dict[str, int]) -> Optional[float]:
    """Convert a raw per-asset delta to a single USD number.

    Returns None if ANY asset in the delta lacks a price or a decimals entry — an incomplete USD
    total is worse than none (silently dropping an un-priced asset understates or overstates the
    delta). Callers should treat None as "USD total not computable, report raw per-asset instead".
    """
    total = 0.0
    for asset, raw in delta.items():
        if raw == 0:
            continue
        key = asset.lower() if asset != "native" else "native"
        price = _lookup(prices_usd, key)
        dec = _lookup(decimals, key)
        if price is None or dec is None:
            return None
        total += (raw / (10 ** int(dec))) * float(price)
    return total


def _lookup(m: Dict[str, object], key: str):
    """Case-insensitive lookup for address keys (native stays 'native')."""
    if key in m:
        return m[key]
    for k, v in m.items():
        if k.lower() == key:
            return v
    return None


# ──────────────────────────────────────────────────────────────────────────
# Oracle: delta + honest marks (the anti-hidden-inflator layer)
# ──────────────────────────────────────────────────────────────────────────

def profit_oracle(before: Dict[str, int],
                  after: Dict[str, int],
                  *,
                  competition_dependent: bool = False,
                  liquidity_dependent: bool = False,
                  prices_usd: Optional[Dict[str, float]] = None,
                  decimals: Optional[Dict[str, int]] = None) -> Dict:
    """Compute the attacker balance-delta on a fork + attach honest ceiling/stale marks.

    The marks are NOT cosmetic: when `competition_dependent`, the USD total is labelled a CEILING
    (`measurement_status='ceiling-not-measured'`), never `measured` — this is the [FIX-H3] fix so a
    fork MEV/backrun number is not passed off as a real extractable amount.
    """
    delta = compute_delta(before, after)
    usd = None
    if prices_usd is not None and decimals is not None:
        usd = delta_to_usd(delta, prices_usd, decimals)

    marks: List[str] = []
    # Always: the fork cannot model an adversarial mempool around you.
    marks.append("no-frontrun-simulation: fork does NOT simulate you being front-run / griefed")

    if competition_dependent:
        measurement_status = "ceiling-not-measured"
        marks.append(
            "competition-dependent (MEV/backrun/sandwich): CEILING, not measured — an isolated fork "
            "has no competing searchers, so this OVER-states the value (real = priority-fee auction / "
            "lost races). Do NOT bank as measured (Mandate 0.10 ceiling caveat).")
    else:
        measurement_status = "measured"

    if liquidity_dependent:
        liquidity_status = "stale-flag"
        marks.append(
            "liquidity-dependent: STALE — fork is a single-block snapshot; live liquidity may differ, "
            "especially under stress (§2.3c). Pinned to the fork block; live may differ.")
    else:
        liquidity_status = "current-block"

    return {
        "attacker_balance_delta_raw": delta,
        "attacker_balance_delta_usd": usd,
        "usd_computable": usd is not None,
        "measurement_status": measurement_status,      # measured | ceiling-not-measured
        "liquidity_status": liquidity_status,          # current-block | stale-flag
        "marks": marks,
        # 🔴 the two guardrail statements that keep this from being a hidden inflator:
        "role": "down-guard / realism input (Mandate 0.10 role 3) — NOT a magnitude source",
        "magnitude_source": "protocol_loss (victim-side), measured separately — NOT this delta",
    }


# ──────────────────────────────────────────────────────────────────────────
# Fork I/O via cast (read-only; NOT unit-tested — needs a live fork)
# ──────────────────────────────────────────────────────────────────────────

def _cast_bin() -> str:
    env_bin = os.environ.get("CAST_BIN")
    if env_bin and (env_bin == Path(env_bin).name or Path(env_bin).exists()):
        return env_bin
    default = Path.home() / ".foundry" / "bin" / ("cast.exe" if os.name == "nt" else "cast")
    return str(default) if default.exists() else "cast"


def _cast(*args: str, timeout: float = 60.0) -> subprocess.CompletedProcess:
    return subprocess.run([_cast_bin(), *args], capture_output=True, text=True,
                          timeout=timeout, check=False)


def read_balances_via_cast(rpc: str, address: str,
                           tokens: Optional[List[str]] = None) -> Dict[str, int]:
    """Read the attacker's native + ERC-20 balances from a fork RPC. Read-only (no signing).

    Run against a fork spun by `onchain_poc_harness.py fork-up` — before the exploit for the
    `before` snapshot, after it for the `after` snapshot.
    """
    balances: Dict[str, int] = {}
    res = _cast("balance", address, "--rpc-url", rpc)
    if res.returncode != 0:
        raise RuntimeError(f"cast balance failed: {res.stderr.strip()}")
    balances["native"] = int(res.stdout.strip())
    for tok in (tokens or []):
        r = _cast("call", tok, "balanceOf(address)(uint256)", address, "--rpc-url", rpc)
        if r.returncode != 0:
            raise RuntimeError(f"cast call balanceOf({tok}) failed: {r.stderr.strip()}")
        # cast may print "123 [1.23e2]" — take the leading integer token.
        balances[tok] = int(r.stdout.strip().split()[0])
    return balances


# ──────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────

def _load_json(arg: str):
    """Accept an inline JSON object or a path to a JSON file; return parsed (no coercion)."""
    text = arg
    if Path(arg).exists():
        text = Path(arg).read_text(encoding="utf-8")
    return json.loads(text)


def _as_balances(obj) -> Dict[str, int]:
    """Accept a raw balance map OR a wrapped snapshot {'balances': {...}}; return int-coerced map.

    A `snapshot` subcommand writes `{"label":.., "address":.., "balances":{...}}` — unwrap to the
    balances before coercing, so the snapshot→delta workflow does not choke on the string fields.
    """
    if isinstance(obj, dict) and isinstance(obj.get("balances"), dict):
        obj = obj["balances"]
    return {k: int(v) for k, v in obj.items()}


def _load_priced(arg: Optional[str]):
    if not arg:
        return None
    text = arg
    if Path(arg).exists():
        text = Path(arg).read_text(encoding="utf-8")
    return json.loads(text)


def cmd_snapshot(args) -> int:
    balances = read_balances_via_cast(args.rpc, args.address, args.token)
    snap = {"label": args.label, "address": args.address, "balances": balances}
    out = json.dumps(snap, indent=2)
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")
        print(f"wrote {args.label} snapshot -> {args.out}")
    else:
        print(out)
    return 0


def cmd_delta(args) -> int:
    before = _as_balances(_load_json(args.before))
    after = _as_balances(_load_json(args.after))
    r = profit_oracle(
        before, after,
        competition_dependent=args.competition_dependent,
        liquidity_dependent=args.liquidity_dependent,
        prices_usd=_load_priced(args.prices),
        decimals=_load_priced(args.decimals),
    )
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        print("Fork attacker balance-delta (AOE §3.1 — down-guard input, NOT magnitude)")
        print("-" * 66)
        for asset, d in r["attacker_balance_delta_raw"].items():
            print(f"  {asset:<44} {d:+d}")
        if r["usd_computable"]:
            tag = "CEILING" if r["measurement_status"] == "ceiling-not-measured" else "measured"
            print(f"  {'= USD delta':<44} ${r['attacker_balance_delta_usd']:,.2f}  [{tag}]")
        print("-" * 66)
        print(f"  measurement_status : {r['measurement_status']}")
        print(f"  liquidity_status   : {r['liquidity_status']}")
        print(f"  role               : {r['role']}")
        print(f"  magnitude_source   : {r['magnitude_source']}")
        print("  marks:")
        for m in r["marks"]:
            print(f"    - {m}")
    return 0


def cmd_self_test(args) -> int:
    return 0 if _run_self_test() else 1


def _run_self_test() -> bool:
    """Unit-test the delta math + marks logic on injected fixtures (NO fork needed).

    Sim-test per Task 3.5: proves balance-delta is correct on a toy fixture and that the
    ceiling/stale marks fire exactly when the corresponding dependency flag is set.
    """
    results = []

    def check(name, cond):
        ok = bool(cond)
        print("  [%s] %s" % ("PASS" if ok else "FAIL", name))
        results.append(ok)

    NATIVE = "native"
    TOK = "0xToKeN00000000000000000000000000000000dEaD"

    # (1) raw delta: native gain, token gain, and a token spent (negative).
    before = {NATIVE: 1_000_000_000_000_000_000, TOK: 500}          # 1 ETH, 500 TOK
    after = {NATIVE: 3_500_000_000_000_000_000, TOK: 100}           # 3.5 ETH, 100 TOK
    d = compute_delta(before, after)
    check("delta native = +2.5e18", d[NATIVE] == 2_500_000_000_000_000_000)
    check("delta token = -400 (spent)", d[TOK] == -400)

    # (2) asset present only after = pure gain; only before = pure loss.
    d2 = compute_delta({NATIVE: 0}, {NATIVE: 0, TOK: 777})
    check("token appearing only in after = +777", d2[TOK] == 777)
    d3 = compute_delta({TOK: 900}, {TOK: 0})
    check("token draining to 0 = -900", d3[TOK] == -900)

    # (3) USD conversion (opt-in, exact): 2.5 ETH @ $2000 - (400 TOK @ $1, 0 decimals) = 4600.
    usd = delta_to_usd(
        d,
        prices_usd={NATIVE: 2000.0, TOK.lower(): 1.0},
        decimals={NATIVE: 18, TOK.lower(): 0},
    )
    check("USD delta = 2.5*2000 - 400*1 = 4600", usd is not None and abs(usd - 4600.0) < 1e-6)

    # (4) missing price -> None (never a silently-partial USD total).
    usd_missing = delta_to_usd(d, prices_usd={NATIVE: 2000.0}, decimals={NATIVE: 18})
    check("missing token price -> USD None (no silent partial)", usd_missing is None)

    # (5) marks: plain fork = measured / current-block, only the always-note present.
    plain = profit_oracle(before, after)
    check("plain: measurement_status=measured", plain["measurement_status"] == "measured")
    check("plain: liquidity_status=current-block", plain["liquidity_status"] == "current-block")
    check("plain: no-frontrun note always present",
          any("no-frontrun-simulation" in m for m in plain["marks"]))
    check("plain: never labels itself magnitude",
          "NOT this delta" in plain["magnitude_source"] and "NOT a magnitude source" in plain["role"])

    # (6) competition-dependent -> ceiling-not-measured (the [FIX-H3] anti-inflator).
    comp = profit_oracle(before, after, competition_dependent=True)
    check("competition -> measurement_status=ceiling-not-measured",
          comp["measurement_status"] == "ceiling-not-measured")
    check("competition -> ceiling mark present",
          any("CEILING" in m and "MEV/backrun" in m for m in comp["marks"]))

    # (7) liquidity-dependent -> stale-flag.
    liq = profit_oracle(before, after, liquidity_dependent=True)
    check("liquidity -> liquidity_status=stale-flag", liq["liquidity_status"] == "stale-flag")
    check("liquidity -> stale mark present", any("STALE" in m for m in liq["marks"]))

    # (8) both flags compose.
    both = profit_oracle(before, after, competition_dependent=True, liquidity_dependent=True)
    check("both flags compose (ceiling + stale + frontrun = 3 marks)", len(both["marks"]) == 3)

    # (9) snapshot→delta unwrap: a wrapped {"label","address","balances"} snapshot must NOT choke.
    wrapped = {"label": "before", "address": "0xATTACKER", "balances": {NATIVE: 42, TOK: "7"}}
    b = _as_balances(wrapped)
    check("wrapped snapshot unwraps to int balances", b == {NATIVE: 42, TOK: 7})
    raw = _as_balances({NATIVE: 5})
    check("raw balance map passes through _as_balances", raw == {NATIVE: 5})

    n_ok = sum(results)
    print("\n%d/%d fork_profit_delta self-test cases green" % (n_ok, len(results)))
    return n_ok == len(results)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = p.add_subparsers(dest="cmd", required=True)

    p_sn = sub.add_parser("snapshot", help="Read attacker native+ERC20 balances from a fork (cast)")
    p_sn.add_argument("--rpc", required=True, help="Fork RPC (from onchain_poc_harness.py fork-up)")
    p_sn.add_argument("--address", required=True, help="Attacker address to snapshot")
    p_sn.add_argument("--token", action="append", help="ERC-20 token address (repeatable)")
    p_sn.add_argument("--label", default="snapshot", choices=["before", "after", "snapshot"])
    p_sn.add_argument("--out", help="Write snapshot JSON here (else stdout)")
    p_sn.set_defaults(func=cmd_snapshot)

    p_d = sub.add_parser("delta", help="Diff two balance snapshots + attach honest marks")
    p_d.add_argument("--before", required=True, help="before snapshot: JSON file/inline or balance map")
    p_d.add_argument("--after", required=True, help="after snapshot: JSON file/inline or balance map")
    p_d.add_argument("--competition-dependent", action="store_true",
                     help="value depends on MEV/backrun/sandwich -> USD total is a CEILING, not measured")
    p_d.add_argument("--liquidity-dependent", action="store_true",
                     help="value depends on pool liquidity -> stale-flag (fork = single-block snapshot)")
    p_d.add_argument("--prices", help="JSON {asset: usd_price} (native or token addr) for USD total")
    p_d.add_argument("--decimals", help="JSON {asset: decimals} for USD total")
    p_d.add_argument("--json", action="store_true")
    p_d.set_defaults(func=cmd_delta)

    p_st = sub.add_parser("self-test", help="Unit-test delta math + marks (no fork needed)")
    p_st.set_defaults(func=cmd_self_test)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
