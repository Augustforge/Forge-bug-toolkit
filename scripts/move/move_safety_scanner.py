#!/usr/bin/env python3
"""
Move / Sui safety scanner (taxonomy Cat 15.15-15.20).

NOT a verifier — a grep-grade heuristic triage aid for Move (Sui/Aptos) source.
Fills a real coverage gap: before this, the toolkit had Solana + EVM + TON
engines but NO Move detector (only taxonomy 15.8/15.14). Source of the signal
set: forefy/.context move-checks.md + Move reference (real bugs: KriyaDEX
transposed returns, Hop Aggregator tautological assert).

Move's resource/ability model and Sui's object/PTB model create bugs with no EVM
analogue that the type-checker happily accepts. This flags the co-occurring
textual signals; every hit needs the manual question stated per class.

Checks:
  15.15 generic type confusion  — public fun <T> whose body never type-checks T
  15.16 ability misuse          — receipt/loan/obligation struct with `drop`
  15.17 return-value integrity  — tautological assert!(x == x); tuple getters; Coin/Balance
  15.19 collection-abort DoS    — table::add without a preceding table::contains
  15.20 sender spoofing         — fun(... sender: address ...) used in an assert

See: methodology/hypothesis_taxonomy.md Cat 15.15-15.20 ; mythos T1 trigger.

Usage:
    py -3 -X utf8 move_safety_scanner.py <path-to-move-src> [--json out.json] [--all]
"""

import argparse
import json
import os
import re
import sys

GENERIC_FN_RE = re.compile(r"\bpublic(?:\s*\(\s*\w+\s*\))?\s+(?:entry\s+)?fun\s+(\w+)\s*<([^>]*\bT\b[^>]*)>\s*\(", re.IGNORECASE)
TYPECHECK_RE = re.compile(r"type_name::get|type_info::type_of|type_of<|TypeName", re.IGNORECASE)

RECEIPT_DROP_RE = re.compile(
    r"struct\s+(\w*(Receipt|Loan|Obligation|Potato|Debt|FlashLoan)\w*)\b[^{]*\bhas\b[^{]*\bdrop\b",
    re.IGNORECASE,
)
TAUTOLOGY_RE = re.compile(r"assert!\(\s*([A-Za-z_][\w\.\:]*)\s*==\s*\1\s*[,)]")
TUPLE_GETTER_RE = re.compile(r"\bfun\s+(get_\w+|reserves|amounts?)\s*\([^)]*\)\s*:\s*\(\s*\w+\s*,\s*\w+", re.IGNORECASE)
COIN_BALANCE_RE = re.compile(r"coin::into_balance|coin::from_balance|balance::(increase|decrease)_supply", re.IGNORECASE)

TABLE_ADD_RE = re.compile(r"table::add\s*\(")
TABLE_CONTAINS_RE = re.compile(r"table::contains\s*\(")

SENDER_PARAM_RE = re.compile(r"\bfun\s+\w+\s*\([^)]*\bsender\s*:\s*address\b", re.IGNORECASE)
SENDER_AUTH_RE = re.compile(r"assert!\([^)]*\bsender\b[^)]*==", re.IGNORECASE)
TXCTX_SENDER_RE = re.compile(r"tx_context::sender")


def iter_move(path):
    if os.path.isfile(path):
        if path.endswith(".move"):
            yield path
        return
    for root, _d, files in os.walk(path):
        if any(s in root for s in (os.sep + "build", os.sep + ".git")):
            continue
        for f in files:
            if f.endswith(".move"):
                yield os.path.join(root, f)


def _fn_body(text, start_idx):
    open_brace = text.find("{", start_idx)
    if open_brace == -1:
        return ""
    depth = 0
    for i in range(open_brace, min(len(text), open_brace + 6000)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace:i + 1]
    return text[open_brace:open_brace + 6000]


def scan_file(fp):
    try:
        text = open(fp, "r", encoding="utf-8", errors="replace").read()
    except OSError:
        return None

    score = 0
    reasons = []

    # 15.15 generic type confusion
    bad_generics = []
    for m in GENERIC_FN_RE.finditer(text):
        body = _fn_body(text, m.end())
        if body and not TYPECHECK_RE.search(body):
            bad_generics.append(m.group(1))
    if bad_generics:
        score += 2
        reasons.append("generic fn<T> with NO type_name::get/type_of<T> check (Cat 15.15, type confusion): %s"
                       % ", ".join(sorted(set(bad_generics))[:6]))

    # 15.16 ability misuse — drop on a debt/receipt struct
    dropped = [m.group(1) for m in RECEIPT_DROP_RE.finditer(text)]
    if dropped:
        score += 2
        reasons.append("receipt/loan/obligation struct has `drop` (Cat 15.16, hot-potato debt-destruction): %s"
                       % ", ".join(sorted(set(dropped))[:6]))

    # 15.17 return-value integrity
    if TAUTOLOGY_RE.search(text):
        score += 2
        reasons.append("tautological assert!(x == x) — masks intended validation (Cat 15.17, Hop Aggregator class)")
    if TUPLE_GETTER_RE.search(text):
        reasons.append("tuple-returning getter (get_reserves/amounts) — check call-site binding order (Cat 15.17, KriyaDEX)")
    if COIN_BALANCE_RE.search(text):
        reasons.append("Coin<->Balance conversion / supply mutation — check conservation (Cat 15.17 ghost balance)")

    # 15.19 collection-abort DoS
    if TABLE_ADD_RE.search(text) and not TABLE_CONTAINS_RE.search(text):
        score += 1
        reasons.append("table::add without any table::contains guard — permissionless-key insert = permanent DoS (Cat 15.19)")

    # 15.20 sender spoofing
    if SENDER_PARAM_RE.search(text) and SENDER_AUTH_RE.search(text) and not TXCTX_SENDER_RE.search(text):
        score += 2
        reasons.append("auth on a `sender: address` PARAMETER, no tx_context::sender(ctx) — impersonation (Cat 15.20)")

    if score == 0 and not reasons:
        return None
    return {"file": fp, "score": score, "reasons": reasons}


def main():
    ap = argparse.ArgumentParser(description="Move/Sui safety scanner (Cat 15.15-15.20)")
    ap.add_argument("path", help="Move source dir (recursed) or single .move file")
    ap.add_argument("--json", dest="json_out", help="write findings to JSON")
    ap.add_argument("--all", action="store_true", help="show every file with any signal (default risk>=2)")
    args = ap.parse_args()

    if not os.path.exists(args.path):
        print("path not found: %s" % args.path, file=sys.stderr)
        return 2

    findings = [f for f in (scan_file(p) for p in iter_move(args.path)) if f]
    flagged = [f for f in findings if f["score"] >= 2]
    shown = findings if args.all else flagged
    shown.sort(key=lambda f: -f["score"])

    print("Move/Sui scan (Cat 15.15-15.20): %d file(s) with signals, %d flagged (risk>=2)"
          % (len(findings), len(flagged)))
    print("Manual Qs: does each generic fn assert T's type? are debt receipts drop-LESS hot potatoes?")
    print("is any assert!(x==x) hiding a real check? is table::add guarded? is auth on tx_context::sender?")
    print("-" * 72)
    for f in shown:
        print("[risk %d] %s" % (f["score"], f["file"]))
        for r in f["reasons"]:
            print("    - %s" % r)

    if args.json_out:
        json.dump(findings, open(args.json_out, "w", encoding="utf-8"), indent=2)
        print("-" * 72)
        print("wrote %d findings -> %s" % (len(findings), args.json_out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
