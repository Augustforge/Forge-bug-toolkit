#!/usr/bin/env python3
"""
liquidity_locker_privilege_scanner.py — Detect privileged-unlock of third-party funds
in liquidity lockers / vesting / escrow (DxSale/DxLock $7.3M class, 28-29.05.2026).

The class: a pooled-custody contract holds MANY users' LP/tokens under a "locked"
promise, but exposes owner-controlled lock parameters (setFee, setLockTime,
emergencyWithdraw) WITHOUT a timelock/multisig → owner can release everyone's funds.
DxSale 2026: setFee(1 wei) + backdated unlock timestamp → drained 1,400 LPs.
Note: Decurity reported this exact class in 2023 ($500 bounty) — it IS reportable.

Two modes (combine):
  --source DIR          → grep owner-mutable lock-param setters + emergency withdraw
  --rpc URL --contract ADDR  → classify owner (EOA/Safe/Timelock); single-owner pooled
                               custody = Nakamoto coefficient 1 (worst case)

Pure-stdlib. Reuses helpers from dapphunt/hypothesis/role_centralization_scanner.py.

Usage:
  py -3 liquidity_locker_privilege_scanner.py --source ./contracts --out report.json
  py -3 liquidity_locker_privilege_scanner.py --rpc https://bsc-dataseed.binance.org \\
        --contract 0xLockerAddress
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_SHARED = Path(__file__).resolve().parents[2] / "dapphunt" / "hypothesis"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))
try:
    from role_centralization_scanner import (  # type: ignore
        eth_call, encode_call, decode_uint, decode_address,
        classify_address, RPCError,
    )
    _HAVE_RPC = True
except Exception:  # pragma: no cover
    _HAVE_RPC = False

    class RPCError(RuntimeError):
        pass


SUGGESTED_TAGS = ["custody", "locker", "liquidity_lock"]

# (id, presence regex, severity, message) — presence of owner-mutable lock params is the risk
SOURCE_RISKS = [
    ("mutable_fee_setter",
     r"function\s+set\w*[Ff]ee\s*\([^)]*\)[^{]*\bonlyOwner\b",
     "critical",
     "owner-only setFee — DxSale 2026 used setFee(1 wei) to neutralize lock cost"),
    ("mutable_unlock_time",
     r"function\s+(set\w*(Lock|Unlock)?Time|extendLock|relock|setUnlock\w*)\s*\([^)]*\)[^{]*\bonlyOwner\b",
     "critical",
     "owner-mutable lock/unlock timestamp — owner can backdate locks to release them"),
    ("emergency_withdraw",
     r"function\s+(emergency\w*[Ww]ithdraw|adminWithdraw|rescue\w*|sweep\w*|migrate\w*)\s*\(",
     "critical",
     "privileged withdraw/migrate path — may move other users' locked assets out of custody"),
    ("owner_mutates_existing_lock",
     r"function\s+\w*[Ll]ock\w*\s*\([^)]*\)[^{]*\bonlyOwner\b",
     "high",
     "owner-callable lock-record mutator — verify it cannot alter OTHER users' locks"),
]

# mitigation patterns that, if present, downgrade confidence
MITIGATIONS = [
    (r"TimelockController|timelock|onlyTimelock", "timelock present on admin ops"),
    (r"renounceOwnership", "ownership renounce path exists (verify actually renounced on-chain)"),
]


def scan_source(source_dir: Path) -> Dict[str, Any]:
    blob = ""
    files = 0
    for f in source_dir.rglob("*"):
        if f.is_file() and f.suffix.lower() == ".sol":
            parts = {p.lower() for p in f.parts}
            if parts & {"node_modules", "lib", "test", "tests", ".git"}:
                continue
            try:
                blob += "\n" + f.read_text(encoding="utf-8", errors="ignore")
                files += 1
            except Exception:
                continue
    findings: List[Dict[str, str]] = []
    for cid, rgx, sev, msg in SOURCE_RISKS:
        if re.search(rgx, blob):
            findings.append({"severity": sev, "id": cid, "message": msg})
    mitig = [note for rgx, note in MITIGATIONS if re.search(rgx, blob)]
    return {"files_scanned": files, "findings": findings, "mitigations_seen": mitig}


def read_owner(rpc_url: str, contract: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"contract": contract}
    if not _HAVE_RPC:
        out["error"] = "RPC helpers unavailable"
        return out
    try:
        owner_raw = eth_call(rpc_url, contract, encode_call("owner()"))
        owner = decode_address(owner_raw)
        out["owner"] = owner
        cls = classify_address(rpc_url, owner)
        out["owner_kind"] = cls.kind
        out["owner_details"] = cls.details
    except RPCError as e:
        out["error"] = str(e)
    return out


def assess(owner_info: Dict[str, Any]) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    kind = owner_info.get("owner_kind")
    if kind == "EOA":
        findings.append({
            "severity": "high",
            "id": "eoa_owner_pooled_custody",
            "message": f"Locker owner is EOA ({owner_info.get('owner')}). Pooled custody = "
                       "Nakamoto coefficient 1: one key compromise drains all locks.",
        })
    elif kind == "GnosisSafe":
        thr = owner_info.get("owner_details", {}).get("safe_threshold", 0)
        if thr and thr <= 2:
            findings.append({
                "severity": "medium",
                "id": "low_threshold_owner",
                "message": f"Locker owner is {thr}-threshold Safe — low Byzantine tolerance over pooled custody.",
            })
    return findings


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--source", help="Source directory")
    ap.add_argument("--rpc", help="JSON-RPC URL")
    ap.add_argument("--contract", help="Locker contract address (with --rpc)")
    ap.add_argument("--out", help="Output JSON path")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    report: Dict[str, Any] = {"suggested_tags": SUGGESTED_TAGS, "findings": []}

    if args.source:
        src = scan_source(Path(args.source))
        report["source"] = {"files_scanned": src["files_scanned"], "mitigations_seen": src["mitigations_seen"]}
        report["findings"].extend(src["findings"])

    if args.rpc and args.contract:
        owner_info = read_owner(args.rpc, args.contract)
        report["onchain"] = owner_info
        report["findings"].extend(assess(owner_info))

    if not (args.source or (args.rpc and args.contract)):
        ap.error("provide --source and/or (--rpc --contract)")

    # crude risk score
    weights = {"critical": 40, "high": 25, "medium": 10}
    report["risk_score"] = min(100, sum(weights.get(f["severity"], 0) for f in report["findings"]))

    if not args.quiet:
        print("=" * 64)
        print(f"Liquidity-locker privilege scanner — risk {report['risk_score']}/100")
        for f in report["findings"]:
            print(f"  [{f['severity'].upper()}] {f['id']}: {f['message']}")
        if not report["findings"]:
            print("  Findings: none")
        if report.get("source", {}).get("mitigations_seen"):
            print(f"  Mitigations seen: {report['source']['mitigations_seen']}")
        print("=" * 64)

    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote {p}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
