#!/usr/bin/env python3
"""
prover.py — Generate Foundry composability test files, optionally invoke forge test.

For each (dep × edge_state):
- Emit `ComposeTest_<dep>_<state>.t.sol` that:
  - Sets dep mock in edge state
  - Runs target protocol's normal entry points
  - Asserts target's invariants
- Optionally invoke `forge test --match-contract ComposeTest`

Output: composability_breaks.json + .t.sol files

Usage:
  python3 prover.py --target /path/to/target \\
      --deps sessions/$T/composability/deps.json \\
      --invariants sessions/$T/deep/invariants.md \\
      --output sessions/$T/composability/ \\
      [--run-forge]                                  # auto-run if forge available
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

EDGE_STATES_BY_KIND = {
    "lending": [
        ("paused", "mock.setPaused(true);"),
        ("liquidity_drained", "mock.setLiquidity(0);"),
        ("oracle_stale", "mock.setOracleStale(true);"),
    ],
    "amm": [
        ("paused", "mock.setPaused(true);"),
        ("drained", "mock.setReserves(0, 0);"),
        ("price_extreme", "mock.setSqrtPrice(type(uint160).max);"),
    ],
    "oracle": [
        ("returns_zero", "mock.setReturnZero(true);"),
        ("returns_max", "mock.setReturnMax(true);"),
        ("returns_stale", "mock.setReturnStale(true);"),
    ],
    "bridge": [
        ("paused", "mock.setPaused(true);"),
        ("revert_send", "mock.setRevertOnSend(true);"),
        ("replayable", "mock.setMessageReplayable(true);"),
    ],
    "restaking": [
        ("operator_slashed", "mock.setOperatorSlashed(true);"),
        ("queue_full", "mock.setQueueFull(true);"),
    ],
    "lst": [
        ("negative_yield", "mock.setNegativeYield(true);"),
        ("paused", "mock.setPaused(true);"),
    ],
    "approval": [
        ("deny_all", "mock.setDenyAll(true);"),
    ],
}


def pascal_case(name: str) -> str:
    return "".join(part.capitalize() for part in name.replace("_", "-").split("-"))


def parse_invariants(invariants_md: Path) -> list[str]:
    """Extract invariant statements from markdown."""
    if not invariants_md.exists():
        return []
    text = invariants_md.read_text(encoding="utf-8", errors="ignore")
    invariants = []
    # Crude: lines containing "MUST" or starting with "- "
    for line in text.splitlines():
        if "MUST" in line or "should never" in line.lower() or "shall" in line.lower():
            line = line.lstrip("-* ").strip()
            if len(line) > 10:
                invariants.append(line[:200])
    return invariants[:10]


def gen_test(dep: dict, edge_name: str, edge_setup: str, target_name: str, invariants: list[str]) -> str:
    pascal = pascal_case(dep["name"])
    test_name = f"ComposeTest_{dep['name']}_{edge_name}".replace("-", "_")
    inv_block = "\n".join(f"        // INVARIANT: {inv}" for inv in invariants[:5])
    if not inv_block:
        inv_block = "        // INVARIANT: <none extracted from invariants.md — add manually>"

    return f"""\
// SPDX-License-Identifier: MIT
// Auto-generated composability test
// Dep: {dep['name']} ({dep['kind']}) — edge: {edge_name}
pragma solidity ^0.8.20;

import {{Test}} from "forge-std/Test.sol";
import {{Mock{pascal}}} from "./Mocks/Mock{pascal}.sol";

interface I{pascal_case(target_name)} {{
    // TODO: paste target's actual entry-point signatures here
    function deposit(uint256) external;
    function withdraw(uint256) external;
}}

contract {test_name} is Test {{
    Mock{pascal} mock;
    I{pascal_case(target_name)} target;
    address user = address(0xBEEF);

    function setUp() public {{
        mock = new Mock{pascal}();
        // TODO: deploy target and wire mock as its {dep['name']} dep
        // target = new YourTarget(address(mock));
    }}

    function test_invariant_under_{edge_name}() public {{
        // Apply edge state
        {edge_setup}

        // Run normal flow
        vm.prank(user);
        // target.deposit(1e18);
        // target.withdraw(1e18);

{inv_block}

        // ASSERT: replace with actual invariant check
        // assertEq(target.totalSupply(), expectedSupply, "invariant broken");
        revert("MANUAL TODO: fill setUp + flow + assert; then comment-out this revert");
    }}
}}
"""


def is_forge_available() -> bool:
    try:
        r = subprocess.run(["forge", "--version"], capture_output=True, timeout=5)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def run_forge(project_dir: Path) -> dict:
    """Try `forge test --match-contract ComposeTest`. Returns parsed output."""
    print(f"[info] running forge test in {project_dir}", file=sys.stderr)
    try:
        result = subprocess.run(
            ["forge", "test", "--match-contract", "ComposeTest", "-vv"],
            capture_output=True, text=True, timeout=300, cwd=project_dir,
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout[-5000:],
            "stderr": result.stderr[-2000:],
        }
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "stdout": "", "stderr": "timeout after 300s"}
    except FileNotFoundError:
        return {"exit_code": -1, "stdout": "", "stderr": "forge not found"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, help="Path to target Foundry project (or just metadata)")
    ap.add_argument("--deps", required=True, help="deps.json")
    ap.add_argument("--invariants", help="invariants.md (optional — manual list otherwise)")
    ap.add_argument("--output", required=True, help="Output dir for test files")
    ap.add_argument("--target-name", default="Target",
                    help="Target contract name for interface generation")
    ap.add_argument("--run-forge", action="store_true",
                    help="Auto-invoke `forge test` if forge available")
    args = ap.parse_args()

    deps = json.loads(Path(args.deps).read_text(encoding="utf-8"))
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    invariants = parse_invariants(Path(args.invariants)) if args.invariants else []
    print(f"[info] extracted {len(invariants)} invariants", file=sys.stderr)

    generated_tests = []
    for dep in deps:
        if dep.get("confidence") == "low":
            continue
        kind = dep.get("kind", "")
        edges = EDGE_STATES_BY_KIND.get(kind, [])
        if not edges:
            print(f"[warn] no edge states for kind={kind}, skipping {dep['name']}", file=sys.stderr)
            continue
        for edge_name, edge_setup in edges:
            test_src = gen_test(dep, edge_name, edge_setup, args.target_name, invariants)
            fname = f"ComposeTest_{dep['name']}_{edge_name}.t.sol".replace("-", "_")
            (out_dir / fname).write_text(test_src, encoding="utf-8")
            generated_tests.append({
                "dep": dep["name"], "kind": kind,
                "edge_state": edge_name, "file": fname,
                "invariants_count": len(invariants),
            })

    breaks_path = out_dir / "composability_breaks.json"
    forge_result = None
    if args.run_forge:
        if is_forge_available():
            target_path = Path(args.target)
            if target_path.is_dir():
                forge_result = run_forge(target_path)
        else:
            forge_result = {"exit_code": -1, "stderr": "forge not in PATH — skipping"}

    breaks = {
        "generated_tests": generated_tests,
        "tests_count": len(generated_tests),
        "invariants_used": invariants,
        "forge_result": forge_result,
        "manual_workflow": [
            f"1. cd {args.target}",
            f"2. cp -r {out_dir}/Mocks test/composability/",
            f"3. cp {out_dir}/ComposeTest_*.t.sol test/composability/",
            "4. Edit each ComposeTest_*.t.sol — fill setUp(), wire target with mock, write actual invariant assert",
            "5. forge test --match-contract ComposeTest -vv",
            "6. Failing test = broken invariant under edge state = candidate finding",
        ],
    }
    breaks_path.write_text(json.dumps(breaks, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[ok] {len(generated_tests)} composability test(s) generated")
    print(f"[ok] manifest: {breaks_path}")
    if forge_result:
        print(f"[info] forge result: exit={forge_result.get('exit_code')}")


if __name__ == "__main__":
    main()
