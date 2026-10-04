#!/usr/bin/env python3
"""
Redemption/burn path skips a peg/solvency check the mint path enforces (Cat 3.16).

NOT a Slither detector — a grep-grade heuristic triage aid. For a stablecoin / pegged
/ collateralized token it looks for the asymmetry where `mint`/`issue` is peg-aware
(reads an oracle / market price / collateral-ratio) but the inverse `burn`/`redeem`
pays out collateral at a HARDCODED / assumed peg (e.g. $1) WITHOUT re-checking that the
token trades at peg. On a downward depeg an attacker buys the token cheap and burns it
for full-value collateral.

This is the Chi Protocol Jul-2026 class ($USC, Ethereum): `ArbitrageV5.burn()` redeemed
weETH/stETH/WETH at a hardcoded $1 peg with no price check, while the mint path was
peg-aware -> flash-loan + depeg + burn near-drained reserves.

Heuristic, per file (contract):
  MINT side  (mint/issue/deposit/expand):  reads a live price  (oracle / getPrice / spot / CR)
  BURN side  (burn/redeem/contract/repay):  pays out using a CONSTANT peg  (`* 1e18`, PEG, 1e8)
                                            and has NO price / oracle / depeg guard
A file where the mint path consults price and the burn path uses a hardcoded peg with no
price guard is the Chi shape.

Anti-FP (Cat 3 applicability gate): a difference is only a finding if the two sides are
MEANT to mirror (both move the same pegged asset). This tool only flags; the reviewer
must confirm intended symmetry before reporting.

See: methodology/hypothesis_taxonomy.md Cat 3.16.

Usage:
    py -3 -X utf8 peg_check_asymmetry.py <path-to-sol-src> [--json out.json] [--all]
"""

import argparse
import json
import os
import re
import sys

MINT_FUNC_RE = re.compile(r"\bfunction\s+(\w*(mint|issue|expand|deposit)\w*)\s*\(", re.IGNORECASE)
BURN_FUNC_RE = re.compile(r"\bfunction\s+(\w*(burn|redeem|contract|withdraw|repay)\w*)\s*\(", re.IGNORECASE)
ANY_FUNC_RE = re.compile(r"\bfunction\s+(\w+)\s*\(")

# reads a live price / oracle / collateral-ratio
PRICE_READ_RE = re.compile(
    r"\b(getPrice|latestAnswer|latestRoundData|consult|getAmountOut|price\s*\(|"
    r"oracle|priceFeed|getUnderlyingPrice|sqrtPrice|getReserves|"
    r"collateralRatio|healthFactor|getRate|exchangeRate|_price\b|marketPrice)\b",
    re.IGNORECASE,
)
# a hardcoded / assumed peg used to size a payout
HARDCODED_PEG_RE = re.compile(
    r"\b(PEG|PEG_PRICE|ONE_DOLLAR|PRECISION\s*\)|1e18|1e8|1e6|10\s*\*\*\s*18)\b"
    r"|\*\s*1e18\b|\*\s*PRECISION\b|/\s*1e18\b",
)
# an explicit depeg / price guard on the burn side (its presence = safe)
DEPEG_GUARD_RE = re.compile(
    r"require\s*\([^;]*(price|peg|oracle|rate|floor|deviation)[^;]*\)"
    r"|if\s*\([^;{]*(price|peg|depeg)[^;{]*\)\s*(revert|return)",
    re.IGNORECASE,
)

SKIP_SEGS = (os.sep + "node_modules", os.sep + ".git", os.sep + "lib" + os.sep, os.sep + "out")


def iter_sol_files(path):
    if os.path.isfile(path):
        if path.endswith(".sol"):
            yield path
        return
    for root, _dirs, files in os.walk(path):
        if any(seg in root for seg in SKIP_SEGS):
            continue
        for f in files:
            if f.endswith(".sol"):
                yield os.path.join(root, f)


def func_spans(lines):
    """Yield (name, start_idx, end_idx) for each function via brace matching."""
    i, n = 0, len(lines)
    while i < n:
        m = ANY_FUNC_RE.search(lines[i])
        if not m:
            i += 1
            continue
        name = m.group(1)
        depth, seen = 0, False
        j = i
        while j < n:
            depth += lines[j].count("{") - lines[j].count("}")
            if "{" in lines[j]:
                seen = True
            if seen and depth <= 0:
                break
            j += 1
        yield name, i, min(j, n - 1)
        i = j + 1


def scan_file(fp):
    try:
        with open(fp, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return []

    mint_price = None   # (name, line) of a mint-side fn that reads price
    burn_pegged = None  # (name, line) of a burn-side fn using hardcoded peg w/o guard

    for name, s, e in func_spans(lines):
        blob = "".join(lines[s:e + 1])
        is_mint = bool(MINT_FUNC_RE.search(lines[s]))
        is_burn = bool(BURN_FUNC_RE.search(lines[s]))
        reads_price = bool(PRICE_READ_RE.search(blob))
        uses_peg = bool(HARDCODED_PEG_RE.search(blob))
        has_guard = bool(DEPEG_GUARD_RE.search(blob))

        if is_mint and reads_price and mint_price is None:
            mint_price = (name, s + 1)
        if is_burn and uses_peg and not reads_price and not has_guard and burn_pegged is None:
            burn_pegged = (name, s + 1)

    if mint_price and burn_pegged:
        return [{
            "file": fp,
            "mint_fn": mint_price[0], "mint_line": mint_price[1],
            "burn_fn": burn_pegged[0], "burn_line": burn_pegged[1],
            "risk": 3,
            "reasons": [
                "mint path %s()@L%d reads a live price/oracle" % (mint_price[0], mint_price[1]),
                "burn path %s()@L%d pays out at a hardcoded peg with NO price/depeg guard" % (burn_pegged[0], burn_pegged[1]),
                "asymmetry = Chi Protocol shape (buy cheap depegged, burn for full-value collateral)",
            ],
        }]
    return []


def main():
    ap = argparse.ArgumentParser(description="mint/burn peg-check asymmetry triage scanner (Cat 3.16)")
    ap.add_argument("path", help="Solidity source dir (recursed) or single .sol file")
    ap.add_argument("--json", dest="json_out", help="write findings to JSON file")
    ap.add_argument("--all", action="store_true", help="(no effect; all findings are risk 3)")
    args = ap.parse_args()

    if not os.path.exists(args.path):
        print("path not found: %s" % args.path, file=sys.stderr)
        return 2

    all_findings = []
    for fp in iter_sol_files(args.path):
        all_findings.extend(scan_file(fp))
    all_findings.sort(key=lambda f: (f["file"],))

    print("peg-check asymmetry scan (Cat 3.16): %d files where mint is peg-aware but burn assumes the peg"
          % len(all_findings))
    print("Anti-FP: confirm the two sides are MEANT to mirror the same pegged asset before reporting.")
    print("-" * 72)
    for f in all_findings:
        print("[risk %d] %s" % (f["risk"], f["file"]))
        for r in f["reasons"]:
            print("    - %s" % r)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(all_findings, fh, indent=2)
        print("-" * 72)
        print("wrote %d findings -> %s" % (len(all_findings), args.json_out))

    return 0


if __name__ == "__main__":
    sys.exit(main())
