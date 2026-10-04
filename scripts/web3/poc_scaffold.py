#!/usr/bin/env python3
"""
Generate Foundry test stubs for high/critical findings.

Reads web3_summary.json, generates one .t.sol file per finding under poc/,
ready for the operator to fill in the actual exploit.

Usage:
    python3 poc_scaffold.py --summary web3_summary.json --output ./poc
"""

import argparse
import json
import re
from pathlib import Path

TEMPLATE = """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
// TODO: import target contract
// import "{import_path}";

/**
 * PoC for finding {finding_id}: {vulnerability}
 *
 * Severity   : {severity}
 * Confidence : {confidence}
 * File       : {file}
 * Function   : {function}
 * Lines      : {lines}
 * Tools      : {tools}
 *
 * Description:
 * {description}
 *
 * Estimated bounty: {bounty}
 *
 * ─────────────────────────────────────────────────────────────────────
 * INSTRUCTIONS:
 * 1. Update the import to point to the target contract
 * 2. Replace TARGET_ADDRESS with the actual address (or deploy in setUp)
 * 3. Implement testExploit_* — show full impact, with funds movement
 * 4. Use console.log to print before/after balances
 * 5. Run locally:
 *      forge test --match-test testExploit_{finding_id} -vvv
 * 6. Verify on mainnet fork via Tenderly (no gas, real state):
 *      tenderly login            # one-time
 *      tenderly fork --network mainnet --block latest
 *      forge test --match-test testExploit_{finding_id} \\
 *        --rpc-url $TENDERLY_FORK_RPC -vvv
 * ─────────────────────────────────────────────────────────────────────
 */
contract Exploit_{finding_id} is Test {{
    address constant TARGET = address(0x0); // TODO
    address attacker;
    address victim;

    function setUp() public {{
        attacker = makeAddr("attacker");
        victim = makeAddr("victim");
        vm.deal(attacker, 100 ether);
        vm.deal(victim, 100 ether);
        // TODO: fork mainnet if needed:
        // vm.createSelectFork("https://eth.llamarpc.com");
    }}

    function testExploit_{finding_id}() public {{
        // ── BEFORE ───────────────────────────────────────────────────
        uint256 attackerBefore = attacker.balance;
        uint256 victimBefore   = victim.balance;
        console.log("Attacker before:", attackerBefore);
        console.log("Victim   before:", victimBefore);

        // ── EXPLOIT ──────────────────────────────────────────────────
        vm.startPrank(attacker);
        // TODO: write the exploit here
        // For {vulnerability}, the typical pattern is:
        // {pattern_hint}
        vm.stopPrank();

        // ── AFTER ────────────────────────────────────────────────────
        uint256 attackerAfter = attacker.balance;
        uint256 victimAfter   = victim.balance;
        console.log("Attacker after :", attackerAfter);
        console.log("Victim   after :", victimAfter);

        // ── ASSERTIONS ───────────────────────────────────────────────
        // TODO: prove the exploit succeeded
        // assertGt(attackerAfter, attackerBefore + 1 ether, "attacker did not profit");
    }}
}}
"""

PATTERN_HINTS = {
    "reentrancy-eth": "// 1. Deploy attacker contract with malicious receive()\n        // 2. Deposit small amount\n        // 3. Call withdraw() — receive() re-enters before state update\n        // 4. Drain repeatedly",
    "reentrancy-balance": "// Read-only reentrancy: re-enter view function\n        // during external call to read inconsistent state",
    "arbitrary-send-eth": "// Call vulnerable function passing attacker as recipient\n        // Show direct ETH transfer with no validation",
    "controlled-delegatecall": "// Deploy malicious contract with selfdestruct or storage write\n        // Trigger delegatecall — attacker code runs in target's context",
    "unprotected-upgrade": "// Call upgrade() / upgradeTo() as attacker\n        // Replace implementation with malicious one\n        // Drain via new logic",
    "suicidal": "// Call selfdestruct-triggering function as attacker\n        // Show destruction of contract",
    "uninitialized-state": "// Front-run initialize() with attacker params\n        // Take ownership / set malicious config",
    "access-control": "// Call privileged function as non-owner\n        // Show missing modifier allows attacker action",
    "integer-overflow": "// Trigger arithmetic that wraps\n        // Show resulting wrong balance / mint",
    "leaked-secret": "// Direct extraction — secret found in repo\n        // Use leaked key to sign tx / access protected resource",
}


def safe_id(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", s or "F000")


def make_import_path(file: str) -> str:
    if not file:
        return "../src/Contract.sol"
    return f"../src/{file.lstrip('./')}"


def generate(finding: dict) -> str:
    vuln = finding.get("vulnerability", "unknown")
    pattern_hint = PATTERN_HINTS.get(vuln, "// TODO: write exploit logic specific to this vulnerability")
    return TEMPLATE.format(
        finding_id=safe_id(finding.get("id", "F000")),
        vulnerability=vuln,
        severity=finding.get("severity", ""),
        confidence=finding.get("confidence", ""),
        file=finding.get("file", ""),
        function=finding.get("function", "") or "(unknown)",
        lines=", ".join(str(l) for l in finding.get("lines", []) or []),
        tools=", ".join(finding.get("tools_flagged", []) or []),
        description=(finding.get("description", "") or "")[:300].replace("*/", "* /"),
        bounty=finding.get("estimated_bounty", "unknown"),
        import_path=make_import_path(finding.get("file", "")),
        pattern_hint=pattern_hint,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--severities", nargs="+",
                    default=["critical", "high"],
                    help="Severities to scaffold (default: critical, high)")
    args = ap.parse_args()

    summary = json.loads(Path(args.summary).read_text())
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    generated = []
    for f in summary.get("findings", []):
        if f.get("severity") not in args.severities:
            continue
        fid = safe_id(f.get("id", "F000"))
        fname = f"{fid}_{safe_id(f.get('vulnerability', 'unknown'))[:30]}.t.sol"
        target = out / fname
        target.write_text(generate(f))
        generated.append({"id": fid, "file": str(target)})
        print(f"[+] {target}")

    summary_path = out / "scaffolds.json"
    summary_path.write_text(json.dumps(generated, indent=2))
    print(f"[+] Generated {len(generated)} PoC stubs → {summary_path}")


if __name__ == "__main__":
    main()
