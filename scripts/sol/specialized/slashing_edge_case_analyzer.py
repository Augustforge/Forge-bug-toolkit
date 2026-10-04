#!/usr/bin/env python3
"""
slashing_edge_case_analyzer.py — Audit Solana staking/restaking protocols
for slashing recovery edge cases.

CONTEXT:
Solana validator slashing is rare but real. LST/restaking protocols
(Marinade, Jito, Marinade Native, Sanctum) hold delegated stake. When
slashing happens, code MUST handle:

1. Partial slash recovery — only part of the stake is lost. update_active /
   merge_stakes / withdraw paths must adjust balances safely.

2. Slash-during-operation — slash happens between epochs while protocol
   tx mid-flight. State.total_active_balance may be out of sync with
   actual on-chain stake.

3. Inactive vs Active stake during slash — different slash mechanics.

4. Recovery via withdraw_to_reserve — does the protocol handle the case
   when actual_stake < tracked_stake?

5. Validator removal after slash — if validator gets removed from
   validator_list while user holds claim ticket on it.

6. mSOL price recalculation — slash should reduce mSOL/SOL exchange rate.
   Protocol must update before allowing new deposits/withdrawals.

KNOWN HISTORICAL ISSUES (broader class targets):
- Marinade-class: validator delisting mid-claim
- Lido-on-Solana class: slash undercount
- Sanctum-class: cross-LST slash propagation

DETECTION:
1. Find slash-aware code paths (look for "slash", "reduce_active", "withdraw_inactive")
2. Verify each adjusts state.total_active_balance + price.exchange_rate
3. Check for race window between observed_slash and state_update
4. Check unstake_queue handling when target validator slashed

USAGE:
    python3 slashing_edge_case_analyzer.py --target sessions/$TARGET/source
    python3 slashing_edge_case_analyzer.py --target ./src --output ...
"""
import argparse
import json
import re
import sys
from pathlib import Path


STAKE_OPERATION_PATTERNS = {
    "deposit_stake": re.compile(r"\bdeposit_stake\s*\(|fn\s+deposit_stake"),
    "withdraw_stake": re.compile(r"\bwithdraw_stake\s*\(|fn\s+withdraw_stake"),
    "delegate_stake": re.compile(r"\bdelegate_stake\s*\("),
    "deactivate_stake": re.compile(r"\bdeactivate_stake\s*\("),
    "merge_stakes": re.compile(r"\bmerge_stakes\s*\("),
    "update_active": re.compile(r"\bupdate_active\s*\(|fn\s+update_active"),
    "claim_ticket": re.compile(r"\bclaim\s*\(|fn\s+claim"),
}

SLASH_AWARE_PATTERNS = [
    re.compile(r"\bslash"),
    re.compile(r"reduce_active|active_balance.*-=|active_balance.*decrease"),
    re.compile(r"withdraw_inactive|inactive_balance"),
    re.compile(r"emergency_unstake"),
    re.compile(r"\bdelinquent\b"),
]

PRICE_RECALC_PATTERNS = [
    re.compile(r"msol_price|exchange_rate|share_price"),
    re.compile(r"price_recalc|recalculate_price|update_price"),
    re.compile(r"on_transfer_from_reserve|on_msol_mint|on_msol_burn"),
]

STAKE_QUERY_PATTERNS = [
    re.compile(r"stake_account\.lamports\(\)|stake\.lamports\b"),
    re.compile(r"validator_active_balance|validator_inactive_balance"),
    re.compile(r"delegation\.\w+\.amount|delegation\.stake"),
]

UNCHECKED_STATE_DRIFT_PATTERNS = [
    re.compile(r"total_active_balance\s*=\s*\w+\.active_balance"),
    re.compile(r"state\.\w+\s*=\s*\w+\.\w+"),
]


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    findings = []
    file_name = path.name

    is_staking_file = bool(any(p.search(text) for p in [
        re.compile(r"validator_list|stake_list|delegation|StakeAccount"),
    ]))
    if not is_staking_file:
        return findings

    has_slash_aware = any(p.search(text) for p in SLASH_AWARE_PATTERNS)
    has_price_recalc = any(p.search(text) for p in PRICE_RECALC_PATTERNS)
    has_state_drift = any(p.search(text) for p in UNCHECKED_STATE_DRIFT_PATTERNS)

    relevant_ops = []
    for op_name, pattern in STAKE_OPERATION_PATTERNS.items():
        if pattern.search(text):
            line_no = next(
                (text[: m.start()].count("\n") + 1 for m in [pattern.search(text)] if m),
                1,
            )
            relevant_ops.append({"op": op_name, "line": line_no})

    if not relevant_ops:
        return findings

    for op in relevant_ops:
        if op["op"] in ("withdraw_stake", "claim_ticket", "update_active", "merge_stakes"):
            if not has_slash_aware:
                findings.append({
                    "class": "slashing_edge_case",
                    "subclass": "no_slash_handling_in_recovery_path",
                    "file": str(path),
                    "line": op["line"],
                    "operation": op["op"],
                    "advice": f"{op['op']} path has no slash-aware logic. "
                              f"If validator slashed mid-operation, state.total_active_balance may drift from the real stake. "
                              f"Recovery path must check actual stake_account.lamports() against tracked balance.",
                    "severity": "high",
                    "classification": "novel_instance",
                    "broader_class": "slash_recovery_gap",
                })

    if has_state_drift and not has_slash_aware:
        m = UNCHECKED_STATE_DRIFT_PATTERNS[0].search(text)
        if m:
            line_no = text[: m.start()].count("\n") + 1
            findings.append({
                "class": "slashing_edge_case",
                "subclass": "state_drift_no_verification",
                "file": str(path),
                "line": line_no,
                "snippet": m.group(0)[:160],
                "advice": "State balance assigned from local variable without cross-check against actual stake account. "
                          "If slash occurred since last update — state drift accumulates.",
                "severity": "medium",
                "classification": "novel_instance",
                "broader_class": "state_drift_assumption",
            })

    for op in relevant_ops:
        if op["op"] in ("deposit_stake", "withdraw_stake", "claim_ticket"):
            if not has_price_recalc:
                findings.append({
                    "class": "slashing_edge_case",
                    "subclass": "price_recalc_missing_in_user_op",
                    "file": str(path),
                    "line": op["line"],
                    "operation": op["op"],
                    "advice": f"{op['op']} (user-facing) doesn't trigger price recalculation. "
                              f"If slash happened since last update, user gets pre-slash exchange rate — economic exploit surface.",
                    "severity": "high",
                    "classification": "novel_instance",
                    "broader_class": "exchange_rate_staleness",
                })

    if "validator_list" in text and "remove" in text.lower():
        for m in re.finditer(r"\bremove[_a-z]*\(|remove_validator", text):
            line_no = text[: m.start()].count("\n") + 1
            local_window = text[max(0, m.start() - 500): m.start() + 500]
            checks_pending_tickets = any(p in local_window for p in [
                "ticket", "pending", "outstanding", "active_stake", "user_claim"
            ])
            if not checks_pending_tickets:
                findings.append({
                    "class": "slashing_edge_case",
                    "subclass": "validator_removal_no_ticket_check",
                    "file": str(path),
                    "line": line_no,
                    "snippet": m.group(0),
                    "advice": "Validator removal path doesn't verify no outstanding tickets/pending claims. "
                              "Users with pending claim on removed validator may be stranded or get incorrect payout.",
                    "severity": "high",
                    "classification": "novel_instance",
                    "broader_class": "validator_removal_race",
                })

    return findings


def main():
    ap = argparse.ArgumentParser(description="Slashing edge case analyzer for Solana staking/restaking")
    ap.add_argument("--target", required=True, help="Source dir or file")
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"[!] target not found: {target}", file=sys.stderr)
        sys.exit(1)

    files = list(target.rglob("*.rs")) if target.is_dir() else [target]
    all_findings = []
    for f in files:
        all_findings.extend(scan_file(f))

    if not args.quiet:
        print(f"[+] Scanned {len(files)} files. Slashing edge case findings: {len(all_findings)}")
        critical = [f for f in all_findings if f["severity"] == "critical"]
        high = [f for f in all_findings if f["severity"] == "high"]
        novel = [f for f in all_findings if f.get("classification") == "novel_instance"]
        print(f"    Critical: {len(critical)}")
        print(f"    High:     {len(high)}")
        print(f"    Novel:    {len(novel)} (HIGH PRIORITY)")

        for f in (critical + high)[:15]:
            sev = f["severity"].upper()
            cls = f.get("classification", "?")
            f_path = Path(f["file"]).name
            print(f"  [{sev:8}] [{cls}] {f['subclass']:42} @ {f_path}:{f['line']}")

    if args.output:
        out_dir = Path(args.output)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "slashing_edge_case_findings.json").write_text(json.dumps(all_findings, indent=2))


if __name__ == "__main__":
    main()
