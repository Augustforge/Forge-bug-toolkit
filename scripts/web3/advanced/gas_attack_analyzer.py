#!/usr/bin/env python3
"""
gas_attack_analyzer.py — find gas-griefing / OOG / block-gas DoS patterns.

Targets:
- Unbounded loop over storage array
- External call inside loop (gas amplification on each iteration)
- .call with no gas limit forwarded
- Reentry-safe external call missing return-value check (gas-bomb fallback)
- Storage write inside loop (large SSTORE cost)
- selfdestruct refund usage (post-EIP-3529 dead)
"""
import argparse
import json
import re
import sys
from pathlib import Path


PATTERNS = [
    ("unbounded_loop_storage", re.compile(r"for\s*\([^;]*;\s*\w+\s*<\s*\w+\.length\s*;[^)]*\)\s*\{[^}]*\b(\w+)\[", re.DOTALL), "Unbounded loop over storage — block gas DoS if array grows"),
    ("ext_call_in_loop", re.compile(r"for\s*\([^)]+\)\s*\{[^}]*\.(?:call|transfer|send|delegatecall|staticcall)\s*[\({]", re.DOTALL), "External call inside loop — gas griefing amplified per iteration"),
    ("call_no_gas_limit", re.compile(r"\.call\{[^}]*\}\s*\([^)]+\)\s*;?(?!\s*//\s*gas)"), ".call without explicit gas limit — recipient can grief by burning gas"),
    ("storage_write_in_loop", re.compile(r"for\s*\([^)]+\)\s*\{[^}]*\b\w+\s*=\s*[^;]+;[^}]*\}", re.DOTALL), "Storage SSTORE inside loop — high gas cost per iter"),
    ("transfer_2300_assumption", re.compile(r"\.transfer\s*\("), ".transfer/.send hardcode 2300 gas — breaks recipients with non-trivial fallback (Istanbul fork)"),
    ("selfdestruct_refund", re.compile(r"\bselfdestruct\s*\("), "selfdestruct refund removed in EIP-3529; pre-existing assumption broken"),
    ("low_level_no_check", re.compile(r"^\s*\w+\.call\s*\([^)]+\)\s*;\s*$", re.MULTILINE), "low-level .call return value not checked"),
    ("oog_revert_path", re.compile(r"require\s*\([^,)]+,\s*\"[^\"]*\"\s*\)"), "Long string literals in require → higher revert gas (favours attacker)"),
]


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    findings = []
    lines = text.splitlines()
    for pid, regex, advice in PATTERNS:
        for m in regex.finditer(text):
            line_no = text[: m.start()].count("\n") + 1
            snippet = lines[line_no - 1].strip()[:140] if line_no <= len(lines) else ""
            findings.append({
                "pattern": pid,
                "file": str(path),
                "line": line_no,
                "snippet": snippet,
                "advice": advice,
            })
    return findings


def main():
    ap = argparse.ArgumentParser(description="Gas attack / DoS analyzer")
    ap.add_argument("--target", required=True)
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    target = Path(args.target)
    files = [target] if target.is_file() else list(target.rglob("*.sol")) if target.is_dir() else []
    if not files:
        print(f"[!] Target not found: {target}", file=sys.stderr)
        sys.exit(1)

    all_findings = []
    for f in files:
        if "/test" in str(f).replace("\\", "/").lower():
            continue
        all_findings.extend(scan_file(f))

    if not args.quiet:
        print(f"[+] Scanned {len(files)} files. Gas findings: {len(all_findings)}")
        by = {}
        for f in all_findings:
            by.setdefault(f["pattern"], 0)
            by[f["pattern"]] += 1
        for p, n in sorted(by.items(), key=lambda x: -x[1]):
            print(f"  {p:30}  {n}")

    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "gas_attack.json").write_text(json.dumps(all_findings, indent=2), encoding="utf-8")
        md = "# Gas Attack Report\n\n"
        for f in all_findings:
            md += f"- **[{f['pattern']}]** {f['file']}:{f['line']}\n  `{f['snippet']}`\n  → {f['advice']}\n\n"
        (out / "gas_attack.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
