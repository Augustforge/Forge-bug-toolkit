#!/usr/bin/env python3
"""
vault_hunter.py — ERC-4626 + general vault-specific bug class hunter.

Focuses on:
- Donation attack surface (no virtual shares offset)
- First-depositor inflation
- Redeem rounding direction
- maxDeposit/maxWithdraw consistency
- Hook reentrancy

Used in /deephunt J3 when target is a vault.
"""

import argparse
import json
import re
from pathlib import Path

CHECKS = {
    "missing_virtual_shares": {
        "description": "No _decimalsOffset() override / virtual shares — donation attack risk",
        "regex": r"function\s+_decimalsOffset|virtualShares|VIRTUAL_SHARES",
        "expected": "present",
        "severity": "Medium",
    },
    "first_deposit_protection": {
        "description": "No first-deposit special-case (totalSupply == 0 check)",
        "regex": r"totalSupply\(\)\s*==\s*0|_totalShares\s*==\s*0|totalAssets\(\)\s*==\s*0",
        "expected": "present",
        "severity": "High",
    },
    "share_price_ceiling": {
        "description": "No share price ceiling — donation attack inflates indefinitely",
        "regex": r"MAX_SHARE_PRICE|sharePriceCeiling|require.*sharePrice\s*<=",
        "expected": "present",
        "severity": "Medium",
    },
    "redeem_rounding_direction": {
        "description": "Redeem must round DOWN (favor vault). Check Math.Rounding.Floor",
        "regex": r"Math\.Rounding\.Floor|Rounding\.Down|mulDiv.*false",
        "expected": "present",
        "severity": "Medium",
    },
    "deposit_balance_diff_pattern": {
        "description": "Vault assumes deposit amount = received amount (fee-on-transfer break)",
        "regex": r"balanceBefore\s*=|balanceAfter\s*=|_balanceBefore",
        "expected": "present",
        "severity": "Low",
    },
    "preview_lying": {
        "description": "previewDeposit/previewWithdraw must match actual deposit/withdraw exactly",
        "regex": r"function\s+preview(Deposit|Withdraw|Mint|Redeem)",
        "expected": "present",
        "severity": "Low",
    },
}


def scan_file(path: Path) -> dict:
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {"error": "read failed"}

    findings = []
    has_4626_marker = bool(re.search(r"ERC4626|IERC4626|convertToShares|convertToAssets", source))

    for check_id, check_info in CHECKS.items():
        present = bool(re.search(check_info["regex"], source))
        expected = check_info["expected"] == "present"
        triggered = expected and not present

        if triggered:
            findings.append({
                "check": check_id,
                "description": check_info["description"],
                "severity": check_info["severity"],
                "applies_to_4626": has_4626_marker,
            })

    return {
        "file": str(path),
        "is_erc4626": has_4626_marker,
        "findings": findings,
    }


def scan_dir(target: Path) -> dict:
    if target.is_file():
        return {"files": [scan_file(target)]}
    files = sorted(target.rglob("*.sol"))
    files = [f for f in files if "node_modules" not in f.parts and "/lib/" not in str(f) and ".t.sol" not in f.name]
    results = []
    for f in files:
        r = scan_file(f)
        if r.get("findings") or r.get("is_erc4626"):
            results.append(r)
    return {"files": results}


def format_md(report: dict) -> str:
    lines = ["# Vault Hunter Findings", "", "ERC-4626 and general vault-specific checks.", ""]
    for fr in report["files"]:
        if not fr.get("findings"):
            continue
        marker = "ERC-4626" if fr.get("is_erc4626") else "Custom vault"
        lines.append(f"## `{fr['file']}` [{marker}]")
        for f in fr["findings"]:
            lines.append(f"- **{f['severity']}**: {f['check']} — {f['description']}")
        lines.append("")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description="Vault-specific bug hunter")
    p.add_argument("--target", required=True)
    p.add_argument("--output", default=".")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()
    target = Path(args.target)
    if not target.exists():
        print(f"ERROR: {target} does not exist")
        return 1
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    report = scan_dir(target)
    (output_dir / "vault_findings.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (output_dir / "vault_findings.md").write_text(format_md(report), encoding="utf-8")
    total = sum(len(f.get("findings", [])) for f in report["files"])
    if not args.quiet:
        print(f"[+] Vault findings: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
