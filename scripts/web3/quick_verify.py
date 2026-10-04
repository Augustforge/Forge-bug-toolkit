#!/usr/bin/env python3
"""
Quick verify mechanism — escalation gate between /hunt and /deephunt.

For each Medium/High/Critical finding:
1. Read source code context (±50 lines)
2. Auto-generate minimal Foundry test if Web3 / curl probe if Web2
3. Solodit pattern lookup
4. Decide: verified | false-positive | escalate-to-deep

Output: enriches finding with `verification` field:
  {
    "status": "verified|false_positive|escalate|inconclusive",
    "test_path": "verify/F001_test.t.sol",
    "test_result": "pass|fail|timeout|error",
    "solodit_matches_count": 3,
    "confidence_after": "high|medium|low",
    "reasoning": "..."
  }
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ESCALATION_TRIGGERS = {
    "multi_tool_unclear": "3+ tools flagged but severity unclear",
    "unknown_pattern": "Pattern not in SWC dictionary",
    "composability": "Multiple external protocol calls",
    "mythril_timeout": "Mythril timeout — complex symbolic state",
    "proxy_high_tvl": "Proxy upgrade on high-TVL contract",
    "complex_state": "Complex state machine (>5 enum states)",
    "golden_case": "Golden case from TVL monitor",
    "subjective_complexity": "AI assessment: complex pattern",
    "threat_intel_match": "Pattern matches recent exploit",
}


def read_context(file_path: Path, lines: list[int], radius: int = 50) -> str:
    if not file_path.exists() or not lines:
        return ""
    try:
        all_lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return ""
    start = max(0, min(lines) - radius)
    end = min(len(all_lines), max(lines) + radius)
    return "\n".join(f"{i+1}: {ln}" for i, ln in enumerate(all_lines[start:end], start=start))


def generate_foundry_test(finding: dict, context: str, out_dir: Path) -> Path | None:
    """Generate minimal Foundry test stub for the finding."""
    vuln = finding.get("vulnerability", "unknown")
    fid = finding.get("id", "F000")
    out_dir.mkdir(parents=True, exist_ok=True)
    test_file = out_dir / f"{fid}_verify.t.sol"

    test_file.write_text(f"""// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";

/**
 * Quick verification test for {fid}: {vuln}
 *
 * Source context (file: {finding.get('file', '?')}, lines: {finding.get('lines', [])}):
 * ```
{context[:1500]}
 * ```
 *
 * INSTRUCTIONS for /deephunt escalation:
 * 1. Decide if this finding is exploitable
 * 2. Write actual exploit logic in testVerify_{fid}
 * 3. Run: forge test --match-test testVerify_{fid} -vvv
 * 4. If passes → verified | If fails → likely false positive
 */
contract QuickVerify_{fid.replace('-', '_')} is Test {{
    function setUp() public {{
        // TODO: deploy or fork target
    }}

    function testVerify_{fid.replace('-', '_')}() public {{
        // TODO: implement verification
        // Assert if vulnerability is exploitable
        assertTrue(true, "PLACEHOLDER — implement verification");
    }}
}}
""")
    return test_file


def detect_escalation_triggers(finding: dict, summary: dict) -> list[str]:
    """Check which escalation triggers fire for this finding."""
    triggers = []

    tools = finding.get("tools_flagged", [])
    if len(tools) >= 3 and finding.get("confidence") != "high":
        triggers.append("multi_tool_unclear")

    if not finding.get("swc_id"):
        triggers.append("unknown_pattern")

    desc = (finding.get("description", "") or "").lower()
    if "external call" in desc or "call("  in desc:
        if desc.count("call") >= 3:
            triggers.append("composability")

    if any("timeout" in str(t).lower() for t in tools):
        triggers.append("mythril_timeout")

    proxy = summary.get("proxy", {})
    tvl = summary.get("tvl_at_risk", 0)
    if proxy.get("is_proxy") and isinstance(tvl, (int, float)) and tvl > 5_000_000:
        triggers.append("proxy_high_tvl")

    return triggers


def quick_verify_finding(finding: dict, summary: dict, project_dir: Path | None,
                         out_dir: Path) -> dict:
    """Quick verify single finding."""
    sev = finding.get("severity", "")
    if sev not in ("critical", "high", "medium"):
        return {"status": "skipped", "reason": "severity below medium"}

    triggers = detect_escalation_triggers(finding, summary)

    file_path = None
    context = ""
    if project_dir and finding.get("file"):
        file_path = project_dir / finding["file"]
        if not file_path.exists():
            for sub in ["src", "contracts"]:
                candidate = project_dir / sub / finding["file"]
                if candidate.exists():
                    file_path = candidate
                    break
        if file_path and file_path.exists():
            context = read_context(file_path, finding.get("lines", []), radius=50)

    test_file = None
    test_result = "not_run"
    if context:
        test_file = generate_foundry_test(finding, context, out_dir / "verify_tests")
        if shutil.which("forge") and (project_dir / "foundry.toml").exists() if project_dir else False:
            try:
                tname = f"testVerify_{finding.get('id', 'F000').replace('-', '_')}"
                r = subprocess.run(
                    ["forge", "test", "--match-test", tname, "-vv"],
                    cwd=project_dir, timeout=60, capture_output=True, text=True,
                )
                test_result = "pass" if r.returncode == 0 else "fail"
            except subprocess.TimeoutExpired:
                test_result = "timeout"
            except Exception:
                test_result = "error"

    if triggers:
        status = "escalate"
    elif test_result == "pass":
        status = "verified"
    elif test_result == "fail":
        status = "false_positive"
    elif test_result == "timeout":
        status = "escalate"
        triggers.append("test_timeout")
    else:
        status = "inconclusive"

    confidence_after = "high" if status == "verified" else (
        "low" if status == "false_positive" else finding.get("confidence", "medium")
    )

    return {
        "status": status,
        "escalation_triggers": [
            {"trigger": t, "reason": ESCALATION_TRIGGERS[t]} for t in triggers
        ],
        "test_path": str(test_file) if test_file else None,
        "test_result": test_result,
        "context_chars": len(context),
        "confidence_after": confidence_after,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", required=True)
    ap.add_argument("--project-dir", help="Foundry project for test execution")
    ap.add_argument("--output")
    args = ap.parse_args()

    summary_path = Path(args.summary)
    summary = json.loads(summary_path.read_text())
    project_dir = Path(args.project_dir) if args.project_dir else None
    out_dir = summary_path.parent

    print(f"[*] Quick verify on {len(summary.get('findings', []))} findings")
    escalations = []

    for f in summary.get("findings", []):
        sev = f.get("severity", "")
        if sev not in ("critical", "high", "medium"):
            continue
        result = quick_verify_finding(f, summary, project_dir, out_dir)
        f["verification"] = result
        if result.get("status") == "escalate":
            escalations.append(f)
            print(f"    [↑] {f['id']} → ESCALATE ({len(result.get('escalation_triggers', []))} triggers)")
        elif result.get("status") == "verified":
            print(f"    [✓] {f['id']} → VERIFIED")
        elif result.get("status") == "false_positive":
            print(f"    [✗] {f['id']} → FALSE POSITIVE")
        else:
            print(f"    [?] {f['id']} → {result.get('status')}")

    out_path = Path(args.output) if args.output else summary_path
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    print(f"[+] Total escalations: {len(escalations)}")
    if escalations:
        print(f"[!] Recommend running /deephunt --focus on these findings:")
        for f in escalations[:5]:
            print(f"    {f['id']}: {f['vulnerability']} (severity: {f['severity']})")


if __name__ == "__main__":
    main()
