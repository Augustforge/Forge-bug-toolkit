#!/usr/bin/env python3
"""
cpi_program_id_validator.py — Loopscale 2025 class.

CLASS: CPI target program ID not validated (separately from authority).
Subset of account_trust_audit, more focused.

Pattern: `invoke(&Instruction { program_id: <accounts[N].key>, ... })` without
`require_keys_eq!(<accounts[N].key>, EXPECTED_PROGRAM_ID)`.
"""
import argparse
import json
import re
import sys
from pathlib import Path

INVOKE_RE = re.compile(r"invoke(?:_signed)?\s*\(\s*&Instruction\s*\{")
KEY_EQ_CHECK_RE = re.compile(r"require_keys_eq!|key\s*==|assert_eq!\s*\([^)]*\.key")
PROGRAM_ID_FIELD_RE = re.compile(r"program_id\s*:\s*([\w.()_\[\]]+)")


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    findings = []
    lines = text.splitlines()

    for m in INVOKE_RE.finditer(text):
        line_no = text[: m.start()].count("\n") + 1
        local = text[m.start(): min(len(text), m.start() + 800)]
        pm = PROGRAM_ID_FIELD_RE.search(local)
        if not pm:
            continue
        prog_id_expr = pm.group(1)
        if "::id()" in prog_id_expr or "system_program" in prog_id_expr:
            continue
        check_zone = text[max(0, m.start() - 600): m.end() + 600]
        if not KEY_EQ_CHECK_RE.search(check_zone):
            snippet = lines[line_no - 1].strip()[:140] if line_no <= len(lines) else ""
            findings.append({
                "class": "cpi_program_id_unchecked",
                "file": str(path),
                "line": line_no,
                "snippet": snippet,
                "program_id_expr": prog_id_expr,
                "advice": f"CPI target `program_id: {prog_id_expr}` without verification against expected program. "
                          f"Loopscale 2025-class: attacker can substitute a malicious program with the same interface.",
                "severity": "critical",
                "classification": "known_class",
            })
    return findings


def main():
    ap = argparse.ArgumentParser(description="Audit CPI program ID validation")
    ap.add_argument("--target", required=True)
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    target = Path(args.target)
    files = [target] if target.is_file() and target.suffix == ".rs" else list(target.rglob("*.rs")) if target.is_dir() else []
    if not files:
        print(f"[!] No .rs files", file=sys.stderr); sys.exit(1)
    all_findings = []
    for f in files:
        if "/target/" in str(f).replace("\\", "/"): continue
        all_findings.extend(scan_file(f))
    if not args.quiet:
        print(f"[+] CPI program ID findings: {len(all_findings)}")
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "cpi_program_id_findings.json").write_text(json.dumps(all_findings, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
