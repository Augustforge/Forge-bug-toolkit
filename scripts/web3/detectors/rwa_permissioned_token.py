#!/usr/bin/env python3
"""
RWA / permissioned-token compliance & partition scanner (taxonomy Cat 24).

NOT a Slither detector — a grep-grade heuristic triage aid for tokenized
real-world-asset / security-token standards (ERC-1400, ERC-3643 "T-REX",
ERC-1404, ERC-6065, ERC-7943). Source: SlowMist RWA-Security-Practices.

The single highest-value RWA bug class is the COMPLIANCE-HOOK COVERAGE GAP
(Cat 24.3): KYC/whitelist/freeze is enforced in transfer()/transferFrom() but a
sibling value-moving path (mint/burn/forcedTransfer/batchTransfer/operatorRedeem)
skips the check -> a restricted/sanctioned address moves value through the
unguarded door. So this scanner does something the erc404 one doesn't: it finds
every balance-changing function in a file and checks whether a compliance call
appears in the SAME function body, and flags the ones that don't.

It also flags the other Cat 24 surfaces (partition accounting, operatorData
destination, DefaultCompliance stub, forcedTransfer/recovery, claim-expiry).
It does NOT prove a bug — every hit needs the manual question stated per check.

See: methodology/hypothesis_taxonomy.md Cat 24 ; mythos_techniques.md T1 trigger ;
     scripts/web3/threat_models/rwa_permissioned_token.yaml

Usage:
    py -3 -X utf8 rwa_permissioned_token.py <path-to-sol-src> [--json out.json] [--all]
"""

import argparse
import json
import os
import re
import sys

# (gate) is this an RWA / permissioned / security token at all?
FAMILY_RE = re.compile(
    r"\b(ERC1400|IERC1400|ERC3643|T-?REX|IModularCompliance|IIdentityRegistry|"
    r"ERC1404|IERC1404|ERC7943|ERC6065)\b"
    r"|\bbyPartition\b|\bpartitionsOf\b|\bcanTransfer\b|\bisVerified\b|\bcanTransact\b",
    re.IGNORECASE,
)

# compliance enforcement call (presence inside a fn body = path is guarded)
COMPLIANCE_RE = re.compile(
    r"\b(canTransfer|canTransferByPartition|isVerified|canTransact|"
    r"tokensToValidate|_validateCertificate|_canReceive|requireKYC|onlyWhitelisted|"
    r"_beforeTokenTransfer|_callValidateExtension)\b",
    re.IGNORECASE,
)

# balance-changing functions whose definitions we want to inspect for a guard.
# matches a Solidity function signature line; we then scan its body.
BALANCE_FN_RE = re.compile(
    r"function\s+(\w*(transfer|mint|burn|redeem|issue|forcedTransfer|controllerTransfer)\w*)\s*\(",
    re.IGNORECASE,
)

PARTITION_RE = re.compile(
    r"_transferByPartition|_removeTokenFromPartition|totalSupplyByPartition|balanceOfByPartition",
    re.IGNORECASE,
)
OPERATORDATA_RE = re.compile(r"operatorData|_getDestinationPartition", re.IGNORECASE)
DEFAULTCOMPLIANCE_RE = re.compile(r"\bDefaultCompliance\b", re.IGNORECASE)
MODULE_RE = re.compile(r"\bbindModule\b|\baddModule\b|\b_modules\b", re.IGNORECASE)
FORCED_RE = re.compile(r"\bforcedTransfer\b|\bcontrollerTransfer\b|\brecoveryAddress\b|\brecover\s*\(", re.IGNORECASE)
RECOVERY_BYPASS_RE = re.compile(r"keyHasPurpose", re.IGNORECASE)
CLAIM_EXPIRY_RE = re.compile(r"\bvalidTo\b|\bexpir|\bexpiry\b", re.IGNORECASE)
CLAIM_RE = re.compile(r"\bclaimTopics?\b|\bgetClaim\b|\bClaimTopic", re.IGNORECASE)


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


def _fn_body(text, start_idx):
    """Return the brace-matched body of a function starting near start_idx."""
    open_brace = text.find("{", start_idx)
    if open_brace == -1:
        return ""
    depth = 0
    for i in range(open_brace, min(len(text), open_brace + 8000)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace:i + 1]
    return text[open_brace:open_brace + 8000]


def scan_file(fp):
    try:
        text = open(fp, "r", encoding="utf-8", errors="replace").read()
    except OSError:
        return None
    if not FAMILY_RE.search(text):
        return None  # not an RWA/permissioned token

    score = 0
    reasons = []
    score += 1
    reasons.append("RWA/permissioned-token family marker present (Cat 24 gate)")

    # --- 24.3 compliance-hook coverage gap (the high-value check) ---
    unguarded = []
    for m in BALANCE_FN_RE.finditer(text):
        fname = m.group(1)
        body = _fn_body(text, m.end())
        if not body:
            continue
        # skip trivial wrappers that just forward to an internal _ guarded fn
        if COMPLIANCE_RE.search(body):
            continue
        # forwarder heuristic: single internal call to a _-prefixed sibling
        if re.search(r"return\s+_\w+\(", body) or re.search(r"\b_\w*(transfer|mint|burn|redeem)\w*\(", body):
            continue
        unguarded.append(fname)
    if unguarded:
        score += 2
        reasons.append("balance-changing fn(s) with NO inline compliance call (Cat 24.3, verify guard): %s"
                       % ", ".join(sorted(set(unguarded))[:8]))

    # --- 24.1 partition accounting ---
    if PARTITION_RE.search(text):
        score += 1
        reasons.append("partition accounting present — check Σ partitions == total + atomic src/dst (Cat 24.1)")
    # --- 24.2 operatorData destination ---
    if OPERATORDATA_RE.search(text):
        score += 1
        reasons.append("operatorData / _getDestinationPartition — locked->liquid partition bypass (Cat 24.2)")
    # --- 24.4 DefaultCompliance / module poisoning ---
    if DEFAULTCOMPLIANCE_RE.search(text):
        score += 2
        reasons.append("DefaultCompliance referenced — if BOUND, canTransfer()==true unconditionally (Cat 24.4)")
    if MODULE_RE.search(text):
        reasons.append("compliance module wiring (bindModule/_modules) — check authz + array DoS (Cat 24.4)")
    # --- 24.6 forced transfer / recovery ---
    if FORCED_RE.search(text):
        score += 1
        reasons.append("forcedTransfer/controller/recovery — scope + audit-trail hash (Cat 24.6)")
        if not RECOVERY_BYPASS_RE.search(text):
            reasons.append("  · no keyHasPurpose check seen near recovery — possible bypass (Cat 24.6)")
    # --- 24.7 claim expiry ---
    if CLAIM_RE.search(text) and not CLAIM_EXPIRY_RE.search(text):
        score += 1
        reasons.append("ClaimTopics used but NO expiry/validTo comparison seen — stale credential (Cat 24.7)")

    return {"file": fp, "score": score, "reasons": reasons, "unguarded_fns": sorted(set(unguarded))}


def main():
    ap = argparse.ArgumentParser(description="RWA / permissioned-token compliance & partition scanner (Cat 24)")
    ap.add_argument("path", help="Solidity source dir (recursed) or single .sol file")
    ap.add_argument("--json", dest="json_out", help="write findings to JSON")
    ap.add_argument("--all", action="store_true", help="show every RWA-shaped file (default risk>=2)")
    args = ap.parse_args()

    if not os.path.exists(args.path):
        print("path not found: %s" % args.path, file=sys.stderr)
        return 2

    findings = [f for f in (scan_file(p) for p in iter_sol(args.path)) if f]
    flagged = [f for f in findings if f["score"] >= 2]
    shown = findings if args.all else flagged
    shown.sort(key=lambda f: -f["score"])

    print("RWA/permissioned-token scan (Cat 24): %d RWA-shaped file(s), %d flagged (risk>=2)"
          % (len(findings), len(flagged)))
    print("Core manual Q: does EVERY balance-changing path (mint/burn/forced/batch/operatorRedeem)")
    print("call the SAME compliance check transfer() does? Is Σ partitions == total? Is the bound")
    print("compliance NOT DefaultCompliance? Are claim expiry + recovery key-purpose enforced?")
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
