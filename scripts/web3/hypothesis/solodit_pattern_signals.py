#!/usr/bin/env python3
"""
solodit_pattern_signals.py — grep-grade triage for code-level bug classes distilled from
the ugwst-sec WEB3-AUDIT-SKILLS corpus (Solodit findings). One scanner, many signals —
each maps to a hypothesis_taxonomy.md category so a hit becomes an H-{NN} candidate.

These are the classes that were ABSENT from our taxonomy until 2026-06-13 (verified by
dedup grep) — NOT a re-implementation of our existing scanners. Each signal is a regex +
a verification_hint (how to confirm it's real, not a false positive) + the taxonomy Cat.

Scope: Solidity (.sol) and Vyper (.vy) source. grep-grade: false positives expected, every
hit needs the manual verification_hint check before it becomes a real hypothesis.

Usage:
    py -3 -X utf8 solodit_pattern_signals.py --target sessions/$T/src [--json out.json]
    py -3 -X utf8 solodit_pattern_signals.py --target <dir> --only gas_1_64,from_to

Categories: gas_1_64 (Cat 13.7) · packed_slot (2.8) · from_to (3.8) · reward_speed (3.9) ·
twap_lazy (5.9) · hook_delta (12.7) · poolmanager_priv (12.7) · rebase_desync (3.10) ·
uncached_balance (9.6 / 8.3) · arbitrary_call (4.8) · approve_caller_supplied (4.8c) · config_disabled_safety (4.9).
rebase_desync/uncached_balance/arbitrary_call distilled from @kankodu (2026-06-13);
config_disabled_safety from H1-2026 hacks (Wasabi/CrossCurve/KelpDAO, 2026-06-14).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import List, Tuple


@dataclass
class Hit:
    signal: str          # signal key
    taxonomy_cat: str    # which Cat in hypothesis_taxonomy.md
    severity_hint: str
    file: str
    line: int
    code: str
    verification_hint: str


# (signal_key, taxonomy_cat, severity_hint, regex, verification_hint)
_SIGNALS: List[Tuple[str, str, str, str, str]] = [
    (
        "gas_1_64", "13.7", "medium",
        r"gasleft\s*\(\s*\)[\s\S]{0,80}?\.call\s*\{[^}]*gas\s*:",
        "Check there is `* 64 / 63` headroom before the gas budget passed to `.call{gas:}`; "
        "and that outer-frame success bookkeeping (processed[id]=true) is NOT set when the "
        "inner call returns false. EIP-150 keeps 1/64 with caller -> callee can OOG silently.",
    ),
    (
        "packed_slot", "2.8", "high",
        r"(insertUint|insertInt|WordCodec|<<\s*\d{1,3}\s*\)?\s*[\|&])[\s\S]{0,40}?(offset|mask|bits)",
        "Confirm multiple fields share one 32-byte slot and a setter writes one field without "
        "preserving neighbours, OR a field's value range can exceed its allotted bit-width. "
        "Balancer WordCodec-style packing is the canonical case (Cat 2.8).",
    ),
    (
        "from_to", "3.8", "high",
        r"balance(s|Of)?\s*\[\s*from\s*\][\s\S]{0,120}?balance(s|Of)?\s*\[\s*to\s*\]",
        "Check for `require(from != to)` (or equivalent). If two balance slots are read into "
        "memory then written back, from==to clobbers the debit -> free mint of `amount` (Cat 3.8).",
    ),
    (
        "reward_speed", "3.9", "high",
        r"(changeRewardSpeed|setRewardRate|setRewardSpeed|updateRewardRate)\s*\(",
        "Confirm this is gated by onlyOwner / a whitelist AND the staking-target address is "
        "locked at deploy. Permissionless attach / settable rate -> attacker drains emissions (Cat 3.9).",
    ),
    (
        "twap_lazy", "5.9", "medium",
        r"(_update(Rate|SPY|Index|Accrual)s?|_accrue|lastUpdate\s*=)\b",
        "Trace WHERE this lazy update fires — if only inside user-facing functions (no keeper, no "
        "per-block clamp) the rate is stale between interactions and the snapshot reads a "
        "manipulable spot/utilization. Manipulate the input immediately before the trigger (Cat 5.9).",
    ),
    (
        "hook_delta", "12.7", "high",
        r"function\s+(before|after)(Swap|AddLiquidity|RemoveLiquidity|Donate)\b[\s\S]{0,200}?returns\s*\([^)]*(int128|BeforeSwapDelta|int256)",
        "A hook returning an int128/BeforeSwapDelta the PoolManager TRUSTS in flash-accounting "
        "settlement. Confirm the returned delta is bounded/validated and the hook makes no external "
        "call before settlement closes (reentrancy into flash accounting) (Cat 12.7).",
    ),
    (
        "poolmanager_priv", "12.7", "medium",
        r"require\s*\(\s*msg\.sender\s*==\s*(address\s*\(\s*)?(poolManager|manager|POOL_MANAGER)",
        "If `msg.sender == poolManager` is the ONLY gate on a state-changing path reachable mid-"
        "callback (during an unlock), a hook can escalate into privileged manager state. Check "
        "the path isn't reachable while the manager is unlocked (Cat 12.7).",
    ),
    (
        "rebase_desync", "3.10", "high",
        r"(repayForAll|settleAll|resetDebt|liquidateAll|repayAll)\b[\s\S]{0,200}?\.(elastic|base|shares|amount|principal)\s*=\s*0\b",
        "A settle-everything function that zeroes ONE field of a Rebase{elastic,base} (or "
        "shares/amount, principal/interest) pair without zeroing the other. Confirm the paired "
        "field is also reset; otherwise the next toBase/toElastic divides by ~0 -> exponential "
        "part accumulation (Abracadabra MIM $6.5M, Cat 3.10).",
    ),
    (
        "uncached_balance", "9.6", "high",
        r"function\s+\w*(burn|withdraw|redeem|remove)\w*\s*\([\s\S]{0,400}?\.balanceOf\s*\(\s*address\s*\(\s*this\s*\)\s*\)",
        "A burn/withdraw/redeem reads token.balanceOf(address(this)) to compute the payout. If "
        "that read happens AFTER any point an attacker can direct-transfer tokens in (or is not "
        "cached before external interaction), it is donation-manipulable -> over-credit. Cache the "
        "balance BEFORE the interaction (Yield Protocol $950K, Cat 9.6 / 8.3 family).",
    ),
    (
        "arbitrary_call", "4.8", "high",
        r"\.(functionCall|call|delegatecall)\s*(\{[^}]*\})?\s*\(\s*\w*[\s\S]{0,40}?(data|payload|callData|_data)\b",
        "An external call whose target and/or calldata trace to function parameters. Confirm there "
        "is NO whitelist of the target and NO selector allow-list on the data — if the attacker "
        "controls either, the contract calls anything AS ITSELF (transferFrom against approvals). "
        "Hot in *Helper/*Wrapper/*Escrow/*Router contracts auditors skim (Sprinter $High, Cat 4.8).",
    ),
    (
        "config_disabled_safety", "4.9", "high",
        r"(delay|minDelay|initialDelay|timelock|gracePeriod|threshold|quorum|confirmations?|requiredSignatures)\s*[:=]\s*(0|1)\b",
        "A safety control (timelock delay, multisig/bridge threshold, confirmations) initialized to a "
        "no-op value (delay=0 / threshold=1). The mechanism is PRESENT in source (passes code review) "
        "but neutralized in config. CRITICAL: verify the LIVE deployed value on-chain, not just this "
        "literal — the deployed instance may differ from repo (deployed != HEAD). Also check supply/"
        "mint caps set to type(uint256).max, and single-verifier / 1-of-1 DVN bridge configs. "
        "Wasabi delay=0 $5.9M, CrossCurve threshold=1 $3M, KelpDAO 1/1-DVN $292M (Cat 4.9).",
    ),
    (
        "approve_caller_supplied", "4.8", "high",
        r"function\s+\w+\s*\([^)]*\baddress\s+(\w+)[^)]*\)(?:(?!\bisActive|\bisPair|\bisRegistered|\bisValidMarket|\bcontains\s*\(|whitelist|allowlist)[\s\S]){0,900}?\.approve\s*\(\s*(?:address\s*\(\s*)?\1\b",
        "A function approves a token over a CALLER-SUPPLIED address (the same `address` parameter is "
        "passed to .approve as spender), then almost always calls into it. If that address is not "
        "checked for registry membership (manager.isActiveMarket / factory.isPair / registry.contains), "
        "an attacker deploys a fake contract that returns Finalized/winner/yesToken=<a token the victim "
        "holds>, gets approved over the full balance, and drains it via transferFrom in its own callback. "
        "nonReentrant is placebo — the theft is in the attacker's contract, not a re-entry. Face-(c) of "
        "Cat 4.8 (True Markets TokenConverter / Trueo H-01, Base 2026, @0x3b33).",
    ),
]

SOURCE_EXTS = {".sol", ".vy"}


def iter_sources(target: Path):
    if target.is_file():
        if target.suffix in SOURCE_EXTS:
            yield target
        return
    for p in target.rglob("*"):
        if p.suffix in SOURCE_EXTS and not any(
            seg in p.parts for seg in ("node_modules", ".git", "lib", "out", "cache", "test", "mock")
        ):
            yield p


def scan(target: Path, only: set[str]) -> List[Hit]:
    compiled = [
        (k, cat, sev, re.compile(rx, re.IGNORECASE), hint)
        for (k, cat, sev, rx, hint) in _SIGNALS
        if not only or k in only
    ]
    hits: List[Hit] = []
    for fp in iter_sources(target):
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for (k, cat, sev, rx, hint) in compiled:
            for m in rx.finditer(text):
                line_no = text.count("\n", 0, m.start()) + 1
                snippet = m.group(0).replace("\n", " ")
                if len(snippet) > 120:
                    snippet = snippet[:117] + "..."
                hits.append(Hit(k, cat, sev, str(fp), line_no, snippet, hint))
    return hits


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Solodit-distilled code-level signal scanner")
    ap.add_argument("--target", required=True, type=Path, help="source dir or file")
    ap.add_argument("--only", default="", help="comma-separated signal keys to run (default: all)")
    ap.add_argument("--json", dest="json_out", type=Path)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    if not args.target.exists():
        ap.error("target not found: %s" % args.target)
    only = {s.strip() for s in args.only.split(",") if s.strip()}

    hits = scan(args.target, only)
    hits.sort(key=lambda h: (h.signal, h.file, h.line))

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps([asdict(h) for h in hits], ensure_ascii=False, indent=2),
                                 encoding="utf-8")

    if not args.quiet:
        print("Solodit pattern signals: %d hits across %d signal classes"
              % (len(hits), len({h.signal for h in hits})))
        print("Each hit = candidate H-{NN}; confirm with verification_hint before treating as real.")
        print("-" * 72)
        for h in hits:
            print("[%s | Cat %s | %s] %s:%d" % (h.signal, h.taxonomy_cat, h.severity_hint, h.file, h.line))
            print("    %s" % h.code)
    return 0 if not hits else 1


if __name__ == "__main__":
    sys.exit(main())
