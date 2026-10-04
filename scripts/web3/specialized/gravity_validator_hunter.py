#!/usr/bin/env python3
"""
gravity_validator_hunter.py — M-of-N bridge validator-set concentration + quorum-logic hunter.

Mission: surface the FINDABLE side of the Gravity Bridge class (Gravity $5.4M, 30.05.2026).
The key-theft itself (≥2/3 ETH signing keys) is the declared trust model — NOT a bug.
What IS findable:
  (a) Concentration — how few validators control the 2/3 quorum (Nakamoto coefficient).
      Low coefficient = severity amplifier for ANY other finding + a centralization claim
      on programs that pay for it.
  (b) Quorum-LOGIC source heuristics — updateValset cumulative-power re-check, signer
      dedup, nonce/checkpoint binding. (Confirm manually; this only flags candidates.)

Three modes (combine freely):
  --valset-json FILE   {"validators":[...], "powers":[...]} → Nakamoto coefficient + risk
  --rpc URL --contract ADDR  → read on-chain quorum constants (powerThreshold, nonces) +
                               classify the bridge contract address
  --source DIR         → grep Gravity-class quorum-logic patterns in source

Pure-stdlib. Reuses helpers from dapphunt/hypothesis/role_centralization_scanner.py.

Usage:
  py -3 gravity_validator_hunter.py --valset-json valset.json --out report.json
  py -3 gravity_validator_hunter.py --rpc https://eth.llamarpc.com \\
        --contract 0xa4108aA1Ec4967F8b52220a4f7e94A8201F2D906
  py -3 gravity_validator_hunter.py --source ./contracts
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── reuse shared RPC/classify helpers from role_centralization_scanner ──
_SHARED = Path(__file__).resolve().parents[2] / "dapphunt" / "hypothesis"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))
try:
    from role_centralization_scanner import (  # type: ignore
        rpc_call, eth_call, encode_call, decode_uint, decode_address,
        classify_address, RPCError,
    )
    _HAVE_RPC = True
except Exception:  # pragma: no cover — source/json modes still work
    _HAVE_RPC = False

    class RPCError(RuntimeError):
        pass


SUGGESTED_TAGS = ["custody", "bridge", "validator-set", "gravity"]

# Gravity.sol well-known view selectors (no array on-chain; checkpoint + constants only)
GRAVITY_VIEWS = {
    "state_powerThreshold()": "0xe5a2b5d2",   # may differ per fork; best-effort
    "state_lastValsetNonce()": "0xf2b53307",
    "state_lastEventNonce()": "0x73b20547",
}


# ──────────────── Concentration / Nakamoto ────────────────

def nakamoto_coefficient(powers: List[int], frac_num: int = 2, frac_den: int = 3) -> Dict[str, Any]:
    """Min number of top validators whose cumulative power reaches the quorum fraction."""
    total = sum(powers)
    if total <= 0:
        return {"error": "zero total power", "total_power": 0}
    threshold = (total * frac_num + frac_den - 1) // frac_den  # ceil(frac * total)
    ordered = sorted(powers, reverse=True)
    acc = 0
    k = 0
    for p in ordered:
        acc += p
        k += 1
        if acc >= threshold:
            break
    top_share = ordered[0] / total if ordered else 0
    return {
        "validator_count": len(powers),
        "total_power": total,
        "quorum_fraction": f"{frac_num}/{frac_den}",
        "quorum_threshold": threshold,
        "nakamoto_coefficient": k,        # compromise k keys → control the bridge
        "top_validator_share": round(top_share, 4),
    }


def assess_concentration(naka: Dict[str, Any]) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    k = naka.get("nakamoto_coefficient")
    n = naka.get("validator_count", 0)
    if k is None:
        return findings
    if k <= 3:
        findings.append({
            "severity": "high",
            "id": "extreme_quorum_concentration",
            "message": f"Nakamoto coefficient = {k} (of {n}): compromising {k} key(s) "
                       "controls the 2/3 quorum. Severity amplifier + centralization claim.",
        })
    elif k <= 5:
        findings.append({
            "severity": "medium",
            "id": "low_quorum_diversity",
            "message": f"Nakamoto coefficient = {k} (of {n}): low Byzantine diversity for a bridge.",
        })
    if naka.get("top_validator_share", 0) >= 0.34:
        findings.append({
            "severity": "medium",
            "id": "dominant_validator",
            "message": f"Single validator holds {naka['top_validator_share']*100:.1f}% power "
                       "(≥1/3 → can block quorum / veto).",
        })
    return findings


# ──────────────── Source heuristics (candidate-only) ────────────────

SOURCE_PATTERNS = [
    ("updateValset_no_power_recheck",
     r"function\s+updateValset",
     r"(sum|cumulative|total)\w*[pP]ower.*(>=|>).*(threshold|powerThreshold)",
     "updateValset present — verify NEW set's cumulative power is re-checked >= threshold"),
    ("signer_dedup",
     r"checkValidatorSignatures|function\s+\w*[sS]ignatures",
     r"(>\s*\w*[lL]ast)|(strictly|increasing)|(seen\[)|(used\[)|(require\(\s*\w+\s*>\s*\w+)",
     "signature loop present — verify signers are deduplicated (strictly-increasing addrs)"),
    ("nonce_binding",
     r"makeCheckpoint|_makeCheckpoint",
     r"[vV]alsetNonce|[bB]atchNonce|[eE]ventNonce",
     "checkpoint present — verify valset & batch nonces are inside the hash"),
    ("malleability_hardening",
     r"ecrecover|ECDSA\.recover",
     r"(s\s*<=|s\s*<).*(0x7FFF|N\s*/\s*2|HALF)|v\s*==\s*27|v\s*==\s*28",
     "ecrecover present — verify s-value/v malleability hardening (EVM vs native asymmetry)"),
]


def scan_source(source_dir: Path) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    exts = {".sol", ".go", ".rs"}
    blob = ""
    for f in source_dir.rglob("*"):
        if f.is_file() and f.suffix.lower() in exts:
            parts = {p.lower() for p in f.parts}
            if parts & {"node_modules", "lib", "test", "tests", ".git"}:
                continue
            try:
                blob += "\n" + f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
    for cid, presence, mitigation, note in SOURCE_PATTERNS:
        if re.search(presence, blob):
            if not re.search(mitigation, blob):
                findings.append({
                    "severity": "medium",
                    "id": cid,
                    "message": f"CANDIDATE: {note} (mitigation pattern NOT found — confirm manually)",
                })
    return findings


# ──────────────── On-chain constants ────────────────

def read_onchain(rpc_url: str, contract: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"contract": contract}
    if not _HAVE_RPC:
        out["error"] = "RPC helpers unavailable (role_centralization_scanner import failed)"
        return out
    for sig, selector in GRAVITY_VIEWS.items():
        try:
            raw = eth_call(rpc_url, contract, selector)
            out[sig] = decode_uint(raw)
        except RPCError:
            out[sig] = None
    try:
        out["address_classification"] = classify_address(rpc_url, contract).kind
    except RPCError:
        pass
    out["note"] = ("Validator array is NOT stored on-chain in Gravity.sol (calldata only). "
                   "Supply the latest valset via --valset-json for Nakamoto analysis.")
    return out


# ──────────────── Main ────────────────

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--valset-json", help='JSON {"validators":[...],"powers":[...]}')
    ap.add_argument("--rpc", help="JSON-RPC URL")
    ap.add_argument("--contract", help="Bridge contract address (with --rpc)")
    ap.add_argument("--source", help="Source directory for quorum-logic heuristics")
    ap.add_argument("--out", help="Output JSON path")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    report: Dict[str, Any] = {"suggested_tags": SUGGESTED_TAGS, "findings": []}

    if args.valset_json:
        data = json.loads(Path(args.valset_json).read_text(encoding="utf-8"))
        powers = data.get("powers") or []
        if not powers and data.get("validators"):
            powers = [1] * len(data["validators"])  # equal-weight fallback
        naka = nakamoto_coefficient([int(p) for p in powers])
        report["concentration"] = naka
        report["findings"].extend(assess_concentration(naka))

    if args.rpc and args.contract:
        report["onchain"] = read_onchain(args.rpc, args.contract)

    if args.source:
        report["findings"].extend(scan_source(Path(args.source)))

    if not (args.valset_json or (args.rpc and args.contract) or args.source):
        ap.error("provide at least one of --valset-json / (--rpc --contract) / --source")

    if not args.quiet:
        print("=" * 64)
        print("Gravity / M-of-N validator-set hunter")
        if "concentration" in report:
            c = report["concentration"]
            print(f"  validators={c.get('validator_count')} "
                  f"nakamoto={c.get('nakamoto_coefficient')} "
                  f"top_share={c.get('top_validator_share')}")
        if "onchain" in report:
            print(f"  onchain: {report['onchain']}")
        for f in report["findings"]:
            print(f"  [{f['severity'].upper()}] {f['id']}: {f['message']}")
        if not report["findings"]:
            print("  Findings: none")
        print("=" * 64)

    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote {p}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
