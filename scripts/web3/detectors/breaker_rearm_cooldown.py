#!/usr/bin/env python3
"""
Circuit-breaker / pause re-arm cooldown weaponized detector (Cat 9.7).

NOT a Slither detector — a grep-grade heuristic triage aid. It surfaces the two
composable ingredients of the ArcadiaFi Jul-2026 class ($3.6M, Base):

  (A) RE-ARM COOLDOWN: a pause / circuit-breaker whose re-enable is time-gated after an
      unpause / reset (`lastUnpause + cooldown > block.timestamp` blocks `pause()`), so
      an attacker can trip it with a benign bait, wait for the team to unpause, and act
      inside the window where the protocol CANNOT re-pause.
  (B) UNCHECKED ROUTER CALL: an external `router.call(data)` / low-level call whose target
      address and calldata come from user input with no validation — the drain primitive.
  (C) DUAL-ROLE REGISTRY: the same address registrable in TWO registries assumed disjoint
      (router-list AND account/whitelist) — "designed for role A, exploited via role B."

The kill in ArcadiaFi was the COMPOSITION (A)x(B)x(C), so this detector reports each
signal independently per file and highlights files carrying more than one — those are the
cross-thread-synthesis candidates.

See: methodology/hypothesis_taxonomy.md Cat 9.7.

Usage:
    py -3 -X utf8 breaker_rearm_cooldown.py <path-to-sol-src> [--json out.json] [--all]
"""

import argparse
import json
import os
import re
import sys

# (A) re-arm cooldown on a pause/breaker: an unpause/reset timestamp + a cooldown compared
#     before allowing pause again.
UNPAUSE_TS_RE = re.compile(
    r"\b(lastUnpause|unpausedAt|lastReset|breakerResetAt|lastResume|cooldownStart|"
    r"lastPauseReset|reArmAt|reactivateAfter)\b",
    re.IGNORECASE,
)
PAUSE_FN_RE = re.compile(
    r"\bfunction\s+(\w*(pause|trip|breaker|halt|freeze|arm)\w*)\s*\(", re.IGNORECASE)
COOLDOWN_CMP_RE = re.compile(
    r"(cooldown|coolDown|delay|reArm|rearm|minInterval)\b[^;]{0,60}block\.timestamp"
    r"|block\.timestamp[^;]{0,60}\b(cooldown|coolDown|delay|reArm|rearm|minInterval)\b",
    re.IGNORECASE,
)

# (B) unchecked external low-level call to a user-supplied router/target
ROUTER_CALL_RE = re.compile(
    r"\b(\w*router\w*|\w*target\w*|to|dest|swapTarget)\s*\.\s*call\s*[\({]",
    re.IGNORECASE,
)
SWAP_VIA_RE = re.compile(r"_swapViaRouter|executeAction|flashAction|_swap\b|externalCall", re.IGNORECASE)

# (C) dual-registry role: whitelisting/registration setters for BOTH a router and an account
ROUTER_REG_RE = re.compile(
    r"\b(setRouter|addRouter|allowRouter|whitelistRouter|isRouter|routers\s*\[|approvedRouter)\b",
    re.IGNORECASE,
)
ACCOUNT_REG_RE = re.compile(
    r"\b(isAccount|whitelistAccount|addAccount|registerAccount|accounts\s*\[|isWhitelisted|"
    r"approvedAccount|createAccount)\b",
    re.IGNORECASE,
)
# a target-validation guard on the call (presence weakens the (B) flag)
TARGET_GUARD_RE = re.compile(
    r"require\s*\([^;]*(isRouter|allowed|whitelist|approvedRouter|trusted)[^;]*\)"
    r"|if\s*\([^;{]*(isRouter|allowed|whitelist)[^;{]*\)",
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


def line_of(pattern, lines):
    for i, ln in enumerate(lines):
        if pattern.search(ln):
            return i + 1
    return None


def scan_file(fp):
    try:
        with open(fp, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return []
    blob = "".join(lines)

    signals = []
    reasons = []

    # (A) re-arm cooldown gating a pause/breaker
    has_pause_fn = bool(PAUSE_FN_RE.search(blob))
    has_unpause_ts = bool(UNPAUSE_TS_RE.search(blob))
    has_cooldown_cmp = bool(COOLDOWN_CMP_RE.search(blob))
    if has_pause_fn and (has_unpause_ts or has_cooldown_cmp):
        signals.append("A")
        reasons.append("(A) breaker/pause with a re-arm cooldown/unpause-timestamp @L%s -- can it be forced open then held?"
                       % (line_of(UNPAUSE_TS_RE, lines) or line_of(COOLDOWN_CMP_RE, lines)))

    # (B) unchecked router/target low-level call
    has_router_call = bool(ROUTER_CALL_RE.search(blob)) or bool(SWAP_VIA_RE.search(blob))
    has_target_guard = bool(TARGET_GUARD_RE.search(blob))
    if has_router_call and not has_target_guard:
        signals.append("B")
        reasons.append("(B) external router/target .call with NO target-validation guard @L%s"
                       % (line_of(ROUTER_CALL_RE, lines) or line_of(SWAP_VIA_RE, lines)))

    # (C) dual-role registry (router AND account/whitelist setters in same file)
    if ROUTER_REG_RE.search(blob) and ACCOUNT_REG_RE.search(blob):
        signals.append("C")
        reasons.append("(C) both router-registry and account/whitelist registry present -- can ONE address hold both roles?")

    if not signals:
        return []

    return [{
        "file": fp,
        "signals": signals,
        "risk": len(signals),
        "reasons": reasons,
    }]


def main():
    ap = argparse.ArgumentParser(description="breaker re-arm cooldown weaponization triage scanner (Cat 9.7)")
    ap.add_argument("path", help="Solidity source dir (recursed) or single .sol file")
    ap.add_argument("--json", dest="json_out", help="write findings to JSON file")
    ap.add_argument("--all", action="store_true", help="list single-signal files too (default: risk>=1)")
    args = ap.parse_args()

    if not os.path.exists(args.path):
        print("path not found: %s" % args.path, file=sys.stderr)
        return 2

    all_findings = []
    for fp in iter_sol_files(args.path):
        all_findings.extend(scan_file(fp))
    all_findings.sort(key=lambda f: (-f["risk"], f["file"]))

    multi = [f for f in all_findings if f["risk"] >= 2]
    print("breaker re-arm cooldown scan (Cat 9.7): %d files with >=1 signal, %d with the composite (>=2)"
          % (len(all_findings), len(multi)))
    print("ArcadiaFi kill = (A) forced-open breaker x (B) unchecked router call x (C) dual-role address.")
    print("Files with >=2 signals are the cross-thread-synthesis candidates.")
    print("-" * 72)
    for f in all_findings:
        print("[risk %d | %s] %s" % (f["risk"], "+".join(f["signals"]), f["file"]))
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
