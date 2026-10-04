#!/usr/bin/env python3
"""
audit_rebuttal_analyzer.py — Challenge code that "passed audit" from a fresh angle.

Pattern: code has been reviewed multiple times. Auditors trusted it. But new
attack classes emerged AFTER the audit, or auditors had blind spots.

This script identifies code that fits "trust traps":
1. Functions with comments like "audited", "reviewed", "safe"
2. Code patterns auditors commonly miss (read-only reentrancy, EIP-1271 lying,
   storage collision, etc.)
3. Code older than 2 years (newer attack classes may not have existed)

Used in /deephunt J0 for protocols with strong audit history.

Usage:
  python3 audit_rebuttal_analyzer.py --target path/to/Contract.sol --output sessions/X/

Output: audit_rebuttal.json + audit_rebuttal.md
"""

import argparse
import json
import re
from pathlib import Path

# Trust-trap markers
AUDIT_MARKERS = re.compile(
    r"\b(audited|reviewed|secure|safe|verified|approved|hardened|battle.tested)\b",
    re.IGNORECASE,
)

# Newer attack class patterns (post-audit-date discoveries)
NEW_ATTACK_SIGNATURES = {
    "readonly_reentrancy": {
        "discovered": "2022 (Curve)",
        "patterns": [
            r"get_virtual_price\s*\(",
            r"getRate\s*\(",
            r"\.previewWithdraw\s*\(",
            r"convertToAssets\s*\(",
        ],
        "rationale": "Read-only reentrancy was popularized post-2022. Older code likely unprotected.",
    },
    "eip1271_lying": {
        "discovered": "2022+",
        "patterns": [
            r"IERC1271\s*\(",
            r"isValidSignature\s*\(",
            r"isValidSig\s*\(",
        ],
        "rationale": "Smart-contract wallets can lie about signature validity. Check if code trusts return.",
    },
    "permit2_phishing": {
        "discovered": "2023+",
        "patterns": [
            r"permitTransferFrom\s*\(",
            r"permitWitnessTransferFrom\s*\(",
            r"Permit2",
            r"ISignatureTransfer",
        ],
        "rationale": "Permit2 witness binding has subtle bugs. Type strings, nonce handling.",
    },
    "sequencer_downtime": {
        "discovered": "2022+ (L2 specific)",
        "patterns": [
            r"AggregatorV3",
            r"Chainlink",
        ],
        "rationale": "L2 contracts must check sequencer uptime feed. Often missed in pre-2023 deploys.",
    },
    "first_depositor_inflation": {
        "discovered": "2022 (Cream)",
        "patterns": [
            r"convertToShares\s*\(",
            r"_convertToShares",
            r"previewDeposit",
            r"totalSupply\(\)\s*==\s*0",
        ],
        "rationale": "ERC-4626 first-depositor share inflation. OZ added virtual shares offset in 2023.",
    },
    "intent_filler_gaming": {
        "discovered": "2024+",
        "patterns": [
            r"settleIntent",
            r"fillIntent",
            r"intentHash",
        ],
        "rationale": "Intent-based protocols have filler-side gaming. New class.",
    },
    "withdrawal_queue_griefing": {
        "discovered": "2023+",
        "patterns": [
            r"queueWithdrawal",
            r"cancelWithdrawal",
            r"withdrawalQueue",
        ],
        "rationale": "Cancel cascades can grief honest users. Post-EigenLayer architectural pattern.",
    },
    "cross_chain_replay": {
        "discovered": "2022+",
        "patterns": [
            r"DOMAIN_SEPARATOR",
            r"_TYPE_HASH",
        ],
        "rationale": "Check if domain separator includes chainId, rebuilt per-call (vs constructor-only).",
    },
    "storage_collision_proxy": {
        "discovered": "Persistent class",
        "patterns": [
            r"_authorizeUpgrade",
            r"upgradeToAndCall",
            r"ERC1967",
        ],
        "rationale": "Storage layout drift between implementations. Check for __gap reserves.",
    },
    "block_timestamp_manipulation": {
        "discovered": "Persistent",
        "patterns": [
            r"block\.timestamp\s*%",
            r"keccak256\(.*block\.timestamp",
        ],
        "rationale": "Miner can manipulate timestamp ±15s. Used for randomness = bug.",
    },
}


def find_comments_near(source: str, line_no: int, radius: int = 5) -> list[str]:
    """Get comments within ±radius lines of given line."""
    source_lines = source.splitlines()
    start = max(0, line_no - radius)
    end = min(len(source_lines), line_no + radius)
    found = []
    for i, ln in enumerate(source_lines[start:end], start=start):
        if "//" in ln or "/*" in ln or "*/" in ln or "@dev" in ln or "@notice" in ln:
            found.append(f"L{i+1}: {ln.strip()}")
    return found


def find_audit_marked_functions(source: str) -> list[dict]:
    """Find functions whose nearby comments contain audit-trust markers."""
    func_re = re.compile(r"function\s+(\w+)\s*\(", re.MULTILINE)
    findings = []
    for m in func_re.finditer(source):
        name = m.group(1)
        line = source[: m.start()].count("\n") + 1
        # Look at 10 lines before for trust markers
        before_start = source.rfind("\n", 0, max(0, m.start() - 500))
        before = source[before_start : m.start()]
        if AUDIT_MARKERS.search(before):
            findings.append({
                "function": name,
                "line": line,
                "trust_markers_in_comments": True,
            })
    return findings


def find_attack_class_signals(source: str) -> list[dict]:
    """Match newer attack class patterns."""
    findings = []
    for attack_id, info in NEW_ATTACK_SIGNATURES.items():
        for pattern_re in info["patterns"]:
            for m in re.finditer(pattern_re, source):
                line = source[: m.start()].count("\n") + 1
                findings.append({
                    "attack_class": attack_id,
                    "pattern_match": m.group(0),
                    "line": line,
                    "discovered": info["discovered"],
                    "rationale": info["rationale"],
                })
    return findings


def scan_file(path: Path) -> dict:
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {"error": "read failed"}

    audit_marked = find_audit_marked_functions(source)
    attack_signals = find_attack_class_signals(source)

    # For each attack signal in an audit-marked function area = double trust trap
    trust_traps = []
    for sig in attack_signals:
        for func in audit_marked:
            if abs(sig["line"] - func["line"]) < 50:
                trust_traps.append({
                    "function": func["function"],
                    "attack_class": sig["attack_class"],
                    "pattern_line": sig["line"],
                    "rationale": f"Audit-marked code containing {sig['attack_class']} pattern — auditors may not have known about this class",
                })
                break

    return {
        "file": str(path),
        "audit_marked_functions": audit_marked,
        "attack_class_signals": attack_signals,
        "trust_traps": trust_traps,
    }


def scan_dir(target: Path) -> dict:
    if target.is_file():
        return {"files": [scan_file(target)]}
    files = sorted(target.rglob("*.sol"))
    files = [
        f for f in files
        if "node_modules" not in f.parts
        and "/lib/" not in str(f)
        and ".t.sol" not in f.name
        and "/test/" not in str(f)
    ]
    results = []
    for f in files:
        r = scan_file(f)
        if r.get("attack_class_signals") or r.get("trust_traps"):
            results.append(r)
    return {"files": results}


def format_md(report: dict) -> str:
    lines = [
        "# Audit Rebuttal Analyzer",
        "",
        "Identifies code that may have passed audit but is vulnerable to newer attack classes.",
        "",
        "## Logic",
        "Audits done in 2021-2022 didn't cover:",
        "- Read-only reentrancy (Curve, 2023)",
        "- Storage collision proxy patterns (ongoing)",
        "- L2 sequencer downtime checks",
        "- ERC-4626 first-depositor inflation (Cream pattern)",
        "- Permit2 witness binding edge cases",
        "- Intent-based filler gaming",
        "- Cross-chain replay (chainId omission)",
        "",
        "If your target code has these patterns AND \"audited\" trust signals → high-value hypothesis.",
        "",
        "---",
        "",
    ]
    for fr in report["files"]:
        if "error" in fr:
            continue
        if not fr.get("attack_class_signals"):
            continue
        lines.append(f"## `{fr['file']}`")
        lines.append("")
        # Trust traps first (highest priority)
        if fr.get("trust_traps"):
            lines.append("### 🚨 Trust Traps (audited + new attack class)")
            for tt in fr["trust_traps"]:
                lines.append(f"- Function `{tt['function']}` at line {tt['pattern_line']}: contains `{tt['attack_class']}` pattern")
                lines.append(f"  > {tt['rationale']}")
            lines.append("")

        # All attack signals
        lines.append("### Attack class patterns found")
        by_class: dict[str, list] = {}
        for sig in fr["attack_class_signals"]:
            by_class.setdefault(sig["attack_class"], []).append(sig)
        for attack_class, signals in by_class.items():
            info = NEW_ATTACK_SIGNATURES.get(attack_class, {})
            lines.append(f"#### `{attack_class}` ({info.get('discovered', '?')})")
            lines.append(f"_{info.get('rationale', '')}_")
            for s in signals[:5]:
                lines.append(f"  - L{s['line']}: `{s['pattern_match']}`")
            lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description="Challenge audited code from fresh attack angles")
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

    if not args.quiet:
        print(f"[*] Running audit rebuttal analysis on {target}...")

    report = scan_dir(target)
    (output_dir / "audit_rebuttal.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (output_dir / "audit_rebuttal.md").write_text(format_md(report), encoding="utf-8")

    total_traps = sum(len(f.get("trust_traps", [])) for f in report["files"])
    total_signals = sum(len(f.get("attack_class_signals", [])) for f in report["files"])
    if not args.quiet:
        print(f"[+] Trust traps: {total_traps}")
        print(f"[+] Attack class signals total: {total_signals}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
