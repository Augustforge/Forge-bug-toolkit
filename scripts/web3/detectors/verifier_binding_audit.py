#!/usr/bin/env python3
"""
Verifier-binding audit — the "verifier accepts what it shouldn't" family (Cat 14.12/14.13).

Boundary-centric SELECT sub-lens #2 (methodology/mythos_techniques.md T1). On EVERY
verification call-site the protocol trusts, ask two questions:

  (a) INPUT-validation (Cat 14.12) — are the inputs validated BEFORE the boolean
      result is trusted? A signature/pairing check that trusts its result without
      rejecting degenerate inputs (zero sig, point-at-infinity, identity, off-subgroup)
      is bypassable. For BLS, e(0,X)==e(X,0)==identity==e(g,g)^0, so any message
      "verifies" when sig and/or pubkey are zero.
        Bonzo Lend / Supra 2026-07-11 ($9.05M, Hedera): BLS price-update verifier
        accepted a zeroed signature [0,0]; pairing on precompile 0.0.8 returned true
        for zero inputs -> attacker pushed a SAUCE price inflated ~12 orders of
        magnitude -> borrowed 6.63M USDC + 34.5M WHBAR.

  (b) RECIPIENT/AUTH-binding (Cat 14.13) — is the RESULT bound to the caller/recipient/
      action? A proof that is valid but does not bind the payout recipient can be
      replayed by an attacker who substitutes their own address.
        Aztec Payments 2026-06-17 ($2.16M): escapeHatch() trusted verifier success,
        didn't bind output-note owner. Hinkal 2026-07-02 (~$820K): prooflessDeposit()
        skipped binding entirely. Same class, two protocols, 3 weeks apart.

Heuristic, NOT proof — flags call-sites for a human depth-trace (drive the boundary
down >=5 layers: consumer -> interface -> verifier -> primitive -> INPUTS). Language-
agnostic regex (Solidity / Rust / Cairo / Vyper) so it runs on raw source with no compile.

Usage:
    py -3 -X utf8 verifier_binding_audit.py --src <path-to-repo-or-file>
    py -3 -X utf8 verifier_binding_audit.py --src ./contracts --json out.json
    py -3 -X utf8 verifier_binding_audit.py --src ./contracts --context 12
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _boundary_util import func_spans, enclosing_block, iter_source_files

SRC_EXT = (".sol", ".rs", ".cairo", ".vy", ".move", ".fc", ".func")

# Verification CALLS — matched embedded in camelCase identifiers (verifyUpdate, verifyPrice,
# blsVerify), not just bare words. Trailing "(" anchors it to a call, not a var named "verifier".
VERIFY_CALL = re.compile(
    r"(\b\w*[Vv]erif\w*\s*\(|\becrecover\s*\(|ECDSA\.recover|\btryRecover\s*\(|"
    r"\b_hashTypedDataV4\s*\(|\bisValidSignature\s*\(|\bcheck[_ ]?[Pp]roof\w*\s*\(|"
    r"\b\w*[Aa]ttest\w*\s*\(|\bdcap\w*\s*\(|\bgroth16\w*\s*\(|\bplonk\w*\s*\()",
)

# PAIRING / BLS call-sites (Cat 14.12 sharpest form) — camelCase-aware (blsPairing, ecPairing).
PAIRING = re.compile(
    r"(\b\w*[Pp]airing\s*\(|\b\w*[Bb]ls[_A-Za-z]*(?:Verify|Pairing|Aggregate)\w*\s*\(|"
    r"\bmillerLoop\s*\(|\bfinalExp\w*\s*\(|\bbn256\w*\s*\(|"
    r"staticcall\(\s*0x0?8\b|address\(0x0?8\)|precompile\s*0\.0\.8|\b0\.0\.8\b|"
    # inline-assembly EVM pairing precompile: staticcall(<gas>, 8, ...) — 8 is the 2nd (address) arg.
    r"staticcall\([^,]+,\s*8\b)",
)

# INPUT guards that make a pairing/sig verify safe. Their ABSENCE in the fn = flag (pairing only).
# NOTE: no bare `!= 0` — it false-matches the pairing RESULT check `out[0] != 0` present in every
# BN254 lib, which silenced the detector on real verifiers. Input guards recognized via require/assert
# forms, isZero/subgroup/on-curve helpers, or an explicit validator call.
INPUT_GUARD = re.compile(
    r"(isZero|is_zero|"
    r"point[_ ]?at[_ ]?infinity|isInfinity|is_infinity|"
    r"subgroup|inSubgroup|is_in_group|isOnCurve|is_on_curve|clearCofactor|isValidSignature|"
    r"require\([^)]*!=\s*(?:0|address\(0\)|bytes32\(0\))|assert[!(][^)]*!=\s*0)",
    re.I,
)

# Zero / degenerate literals near a pairing input = strong signal.
ZERO_LIKE = re.compile(r"\[\s*0\s*,\s*0\s*\]|G1\.zero|G2\.zero|point\(0\s*,\s*0\)|\bidentity\b", re.I)

# Recipient/owner token (used to test whether it is a FUNCTION PARAMETER = attacker-supplied).
RECIPIENT = re.compile(r"\b(recipient|receiver|beneficiary|payoutTo|payTo|destination|dest)\b", re.I)

# proofless / legacy bypass path names — the Hinkal shape (a value path with NO proof at all).
BYPASS_NAME = re.compile(r"(proofless|fastDeposit|fastWithdraw|legacyDeposit|legacyWithdraw|legacyClaim)", re.I)

DECL = re.compile(r"\b(function|fn|func|def)\b\s+(\w+)")


def _signature(lines, span_start):
    """The declaration text of a function: from the decl line until the first '{' or ';'."""
    buf = []
    for k in range(span_start, min(span_start + 6, len(lines))):
        buf.append(lines[k])
        if "{" in lines[k] or ";" in lines[k]:
            break
    return " ".join(buf)


def scan_file(path, ctx=8):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return []
    spans = func_spans(lines)
    findings = []

    def code_lines(span):
        s, e = span
        return [(k, lines[k]) for k in range(s, e + 1)
                if not lines[k].lstrip().startswith(("//", "*", "#", "/*"))]

    for (s, e) in spans:
        body = "\n".join(l for _k, l in code_lines((s, e)))
        sig = _signature(lines, s)
        m = DECL.search(lines[s])
        fname = m.group(2) if m else ""
        reasons = []
        anchor = s + 1  # decl line by default

        has_verify = bool(VERIFY_CALL.search(body)) or bool(PAIRING.search(body))
        recipient_is_param = bool(RECIPIENT.search(sig))
        # recipient re-derived locally (bound) — e.g. `address recipient = ...publicInputs...`
        recipient_bound_local = bool(re.search(r"\b(recipient|receiver|owner|beneficiary)\s*=", body, re.I)
                                     and re.search(r"publicInput|public_input|proof|digest|commitment|nullifier", body, re.I))

        # --- Cat 14.12: pairing/sig verify trusted WITHOUT input validation (pairing sites only) ---
        pairing_hit = None
        for k, ln in code_lines((s, e)):
            if PAIRING.search(ln):
                pairing_hit = k
                break
        if pairing_hit is not None and not INPUT_GUARD.search(body):
            anchor = pairing_hit + 1
            reasons.append(("14.12", "HIGH",
                            "pairing/BLS verify trusted with NO input guard in fn "
                            "(!=0 / subgroup / point-at-infinity) — e(0,X)=identity bypass (Bonzo/Supra)"))
        elif pairing_hit is not None and ZERO_LIKE.search(body) and not INPUT_GUARD.search(body):
            anchor = pairing_hit + 1
            reasons.append(("14.12", "HIGH", "zero/identity literal near a pairing input, no guard"))

        # --- Cat 14.13a: proofless/legacy value path with NO verification at all (Hinkal) ---
        if BYPASS_NAME.search(fname) and not has_verify:
            reasons.append(("14.13", "HIGH",
                            "proofless/legacy entrypoint moves value with NO proof/verify in body (Hinkal prooflessDeposit)"))

        # --- Cat 14.13b: verify-gated payout whose recipient is an attacker-supplied PARAM ---
        elif has_verify and recipient_is_param and not recipient_bound_local:
            reasons.append(("14.13", "HIGH",
                            "verify-gated payout: recipient/owner is a caller-supplied PARAMETER, "
                            "not a proven public input — recipient-substitution (Aztec escapeHatch)"))

        if reasons:
            findings.append({
                "file": path, "line": anchor, "code": lines[anchor - 1].strip()[:200],
                "reasons": [{"cat": c, "severity": sv, "why": w} for c, sv, w in reasons],
            })
    return findings


def main():
    ap = argparse.ArgumentParser(description="Verifier-binding audit (Cat 14.12/14.13 boundary sub-lens).")
    ap.add_argument("--src", required=True, help="repo dir or single source file")
    ap.add_argument("--context", type=int, default=8, help="lines of context around each verify call (default 8)")
    ap.add_argument("--json", help="also write structured findings to this JSON file")
    args = ap.parse_args()

    if not os.path.exists(args.src):
        print("src not found: %s" % args.src, file=sys.stderr)
        return 2

    all_findings = []
    for path in iter_source_files(args.src, SRC_EXT, extra_skip=("test", "mock")):
        all_findings.extend(scan_file(path, args.context))

    for f in all_findings:
        print("%s:%d" % (f["file"], f["line"]))
        print("    %s" % f["code"])
        for r in f["reasons"]:
            print("    [Cat %s · %s] %s" % (r["cat"], r["severity"], r["why"]))
        print("")

    highs = sum(1 for f in all_findings for r in f["reasons"] if r["severity"] == "HIGH")
    print("--- %d verify call-site(s) flagged (%d HIGH). Heuristic — depth-trace each boundary >=5 layers. ---"
          % (len(all_findings), highs))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(all_findings, fh, indent=2)
        print("wrote %s" % args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
