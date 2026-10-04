#!/usr/bin/env python3
"""
cpi_authority_checker.py — CPI signer authority verification gaps.

CLASS: invoke_signed without verifying PDA authority (correct seeds = authority).
"""
import argparse
import json
import re
import sys
from pathlib import Path

INVOKE_SIGNED_RE = re.compile(r"invoke_signed\s*\(", re.MULTILINE)
SIGNER_SEEDS_RE = re.compile(r"signer_seeds\s*[=:]\s*&?\[")


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    findings = []
    lines = text.splitlines()

    for m in INVOKE_SIGNED_RE.finditer(text):
        line_no = text[: m.start()].count("\n") + 1
        local = text[m.start(): min(len(text), m.start() + 500)]
        has_seeds = bool(SIGNER_SEEDS_RE.search(local))
        snippet = lines[line_no - 1].strip()[:140] if line_no <= len(lines) else ""
        if not has_seeds or "&[&[]]" in local or "&[]" in local:
            findings.append({
                "class": "cpi_authority_missing",
                "file": str(path),
                "line": line_no,
                "snippet": snippet,
                "advice": "invoke_signed without proper signer_seeds — authority not enforced. "
                          "Any caller can invoke this CPI without being the correct PDA.",
                "severity": "high",
                "classification": "novel_instance",
            })

    return findings


def main():
    ap = argparse.ArgumentParser(description="Audit CPI signer authority")
    ap.add_argument("--target", required=True)
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    target = Path(args.target)
    files = [target] if target.is_file() and target.suffix == ".rs" else list(target.rglob("*.rs")) if target.is_dir() else []
    if not files:
        print(f"[!] No .rs files: {target}", file=sys.stderr); sys.exit(1)
    all_findings = []
    for f in files:
        if "/target/" in str(f).replace("\\", "/"): continue
        all_findings.extend(scan_file(f))
    if not args.quiet:
        print(f"[+] CPI authority findings: {len(all_findings)}")
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "cpi_authority_findings.json").write_text(json.dumps(all_findings, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
