#!/usr/bin/env python3
"""
ERC-404 / DN404 / BT404 hybrid-token dual-accounting scanner (taxonomy Cat 11.7).

NOT a Slither detector — a grep-grade heuristic triage aid. Hybrid ERC20+ERC721
standards (ERC404 / DN404 / DN404Mirror / BT404) keep TWO synchronized
representations (fungible balance + NFT ownership) in gas-packed storage. The
attack surface is the SYNC + the bit-packing. Canonical bug (Flooring/BitmapPunks
2026, ~$900K; Asterix fork next day = protocol-family transfer):

    tokenId stored via `_set(..., uint32(id))`  -> high-bit id >= 2**32 truncates
    -> aliases an existing id -> ghost ownership (owner check passes, bookkeeping
    uses full id) -> transfer/burn hits `balance -= amount` inside a big unchecked{}
    block whose `require(amount <= balance)` sits OUTSIDE it -> uint96 wraparound
    -> near-infinite balance -> mint dust-cost, drain pools/NFTs.

This flags the co-occurring signals and ranks by how many appear together. It does
NOT prove a bug — every hit needs the manual question:

    "Can a crafted high-bit tokenId truncate to alias an existing token, and does
     the balance/ownership check sit OUTSIDE the unchecked transfer block so a
     ghost-ownership state underflows it?"

See: methodology/hypothesis_taxonomy.md Cat 11.7 ; mythos_techniques.md T1 trigger.

Usage:
    py -3 -X utf8 erc404_dual_accounting.py <path-to-sol-src> [--json out.json] [--all]
"""

import argparse
import json
import os
import re
import sys

# (A) Is this even an ERC404-family token? (gate signal)
FAMILY_RE = re.compile(
    r"\b(DN404Mirror|DN404|ERC404|BT404|MERC404)\b"
    r"|\baddressToAlias\b|\baliasToAddress\b|\bnumAliases\b",
    re.IGNORECASE,
)

# (B) Narrowing cast on a tokenId -> silent truncation / aliasing
TRUNCATE_RE = re.compile(
    r"\buint(8|16|32|64)\s*\(\s*\w*(id|tokenId|tokenid)\w*\s*\)"
    r"|_set\s*\([^)]*uint(8|16|32|64)\s*\(",
    re.IGNORECASE,
)

# (C) Packed ownership map (two values per slot) — DN404 `oo`/Uint32Map/LibMap
PACKED_RE = re.compile(
    r"\bUint32Map\b|\bLibMap\b|\bmapping\s*\(\s*uint256\s*=>\s*uint256\s*\)\s*\w*(oo|owned|owner)\w*",
    re.IGNORECASE,
)

# (D) unchecked block in/around transfer (the wraparound site)
UNCHECKED_RE = re.compile(r"\bunchecked\s*\{")
BAL_DEC_RE = re.compile(r"balance\s*(-=|=\s*\w*\s*-)\s*", re.IGNORECASE)
BAL_GUARD_RE = re.compile(r"(require|revert|if)\s*\(?[^;{]*\b(amount|value)\b[^;{]*(>|<=|<|>=)\s*[^;{]*balance", re.IGNORECASE)

# (E) base <-> mirror sync surface
SYNC_RE = re.compile(r"_pullOption|_mirror|mirrorERC721|_DNStorage|skipNFT|_transferFromNFT", re.IGNORECASE)


def iter_sol(path):
    if os.path.isfile(path):
        if path.endswith(".sol"):
            yield path
        return
    for root, _d, files in os.walk(path):
        if any(s in root for s in (os.sep + "node_modules", os.sep + ".git", os.sep + "out")):
            continue
        for f in files:
            if f.endswith(".sol"):
                yield os.path.join(root, f)


def scan_file(fp):
    try:
        text = open(fp, "r", encoding="utf-8", errors="replace").read()
    except OSError:
        return None
    is_family = bool(FAMILY_RE.search(text))
    trunc = TRUNCATE_RE.search(text)
    packed = bool(PACKED_RE.search(text))
    has_unchecked = bool(UNCHECKED_RE.search(text))
    bal_dec = bool(BAL_DEC_RE.search(text))
    bal_guard = bool(BAL_GUARD_RE.search(text))
    sync = bool(SYNC_RE.search(text))

    if not (is_family or trunc or packed):
        return None  # not ERC404-shaped at all

    score = 0
    reasons = []
    if is_family:
        score += 1; reasons.append("ERC404/DN404/BT404 family marker")
    if trunc:
        score += 1; reasons.append("tokenId narrowing cast (truncation/alias risk): %s" % trunc.group(0).strip())
    if packed:
        score += 1; reasons.append("packed ownership map (Uint32Map/LibMap/oo)")
    if has_unchecked and bal_dec:
        score += 1; reasons.append("balance decrement inside unchecked block (wraparound site)")
        if not bal_guard:
            score += 1; reasons.append("NO amount<=balance guard found near the decrement (underflow not bounded)")
    if sync:
        reasons.append("base<->mirror sync surface present (check ownership desync)")
    return {"file": fp, "score": score, "reasons": reasons,
            "family": is_family, "truncation": bool(trunc), "packed": packed,
            "unchecked_balance": has_unchecked and bal_dec, "guard_seen": bal_guard}


def main():
    ap = argparse.ArgumentParser(description="ERC404/DN404/BT404 dual-accounting scanner (Cat 11.7)")
    ap.add_argument("path", help="Solidity source dir (recursed) or single .sol file")
    ap.add_argument("--json", dest="json_out", help="write findings to JSON")
    ap.add_argument("--all", action="store_true", help="show every ERC404-shaped file (default risk>=2)")
    args = ap.parse_args()

    if not os.path.exists(args.path):
        print("path not found: %s" % args.path, file=sys.stderr)
        return 2

    findings = [f for f in (scan_file(p) for p in iter_sol(args.path)) if f]
    flagged = [f for f in findings if f["score"] >= 2]
    shown = findings if args.all else flagged
    shown.sort(key=lambda f: -f["score"])

    print("ERC404/DN404/BT404 scan (Cat 11.7): %d ERC404-shaped file(s), %d flagged (risk>=2)"
          % (len(findings), len(flagged)))
    print("Manual Q per hit: can a high-bit tokenId truncate->alias an existing token, and does the")
    print("balance/owner check sit OUTSIDE the unchecked transfer block so ghost-ownership underflows it?")
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
