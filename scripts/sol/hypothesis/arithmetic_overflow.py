#!/usr/bin/env python3
"""
arithmetic_overflow.py — Anchor < 0.30 unchecked arithmetic patterns.

CLASS: arithmetic ops without checked_/saturating_ wrappers → overflow.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ARITHMETIC_RE = re.compile(r"\b(\w+)\s*[\+\-\*]=\s*(\w+)|\b(\w+)\s*=\s*(\w+)\s*[\+\-\*]\s*(\w+)\b")
CHECKED_CONTEXT_RE = re.compile(r"checked_(add|sub|mul|div)|saturating_|wrapping_|overflow")
CARGO_TOML_OVERFLOW_RE = re.compile(r"overflow-checks\s*=\s*true")


def has_global_overflow_checks(target: Path) -> bool:
    for ct in target.rglob("Cargo.toml") if target.is_dir() else []:
        try:
            if CARGO_TOML_OVERFLOW_RE.search(ct.read_text(encoding="utf-8", errors="ignore")):
                return True
        except Exception:
            continue
    return False


def scan_file(path: Path, global_safe: bool) -> list[dict]:
    if global_safe:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    findings = []
    lines = text.splitlines()

    for m in ARITHMETIC_RE.finditer(text):
        line_no = text[: m.start()].count("\n") + 1
        context = text[max(0, m.start() - 60): m.end() + 30]
        if CHECKED_CONTEXT_RE.search(context):
            continue
        snippet = lines[line_no - 1].strip()[:140] if line_no <= len(lines) else ""
        if "//" in snippet[:snippet.find(m.group(0))] if m.group(0) in snippet else False:
            continue
        findings.append({
            "class": "arithmetic_overflow",
            "file": str(path), "line": line_no,
            "snippet": snippet,
            "advice": "Arithmetic op without a checked_/saturating_ wrapper. Confirm overflow-checks=true in Cargo.toml "
                      "or use explicit checked_add/sub/mul.",
            "severity": "medium", "classification": "known_class",
        })
    return findings


def main():
    ap = argparse.ArgumentParser(description="Detect unchecked arithmetic")
    ap.add_argument("--target", required=True)
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    target = Path(args.target)
    files = [target] if target.is_file() and target.suffix == ".rs" else list(target.rglob("*.rs")) if target.is_dir() else []
    if not files: print(f"[!] No .rs files", file=sys.stderr); sys.exit(1)

    global_safe = has_global_overflow_checks(target) if target.is_dir() else False
    if global_safe and not args.quiet:
        print("[*] Global overflow-checks=true detected — skipping arithmetic scan")

    all_findings = []
    for f in files:
        if "/target/" in str(f).replace("\\", "/"): continue
        all_findings.extend(scan_file(f, global_safe))
    if not args.quiet: print(f"[+] Arithmetic findings: {len(all_findings)}")
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "arithmetic_findings.json").write_text(json.dumps(all_findings[:200], indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
