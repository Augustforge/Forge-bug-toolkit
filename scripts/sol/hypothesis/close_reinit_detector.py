#!/usr/bin/env python3
"""
close_reinit_detector.py — close+reinit in one tx → stale discriminator bypass.

CLASS: an account closed (lamports → 0) and re-init'd in the same tx may contain
stale discriminator/data → bypass type check.
"""
import argparse
import json
import re
import sys
from pathlib import Path

CLOSE_RE = re.compile(r"\.close\s*\(\s*\w+\s*\)")
LAMPORTS_ZERO_RE = re.compile(r"lamports\s*\.?\s*=\s*0|\*\s*\w+\.lamports\.borrow_mut\(\)\s*=\s*0")


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    findings = []
    lines = text.splitlines()

    for m in CLOSE_RE.finditer(text):
        line_no = text[: m.start()].count("\n") + 1
        snippet = lines[line_no - 1].strip()[:140] if line_no <= len(lines) else ""
        findings.append({
            "class": "close_reinit_bypass",
            "file": str(path), "line": line_no,
            "snippet": snippet,
            "advice": "Account close detected. Verify that subsequent instructions in same tx do not accept this account "
                      "without re-checking discriminator. Stale data may bypass type checks.",
            "severity": "medium", "classification": "novel_instance",
        })

    for m in LAMPORTS_ZERO_RE.finditer(text):
        line_no = text[: m.start()].count("\n") + 1
        local = text[m.start(): min(len(text), m.start() + 500)]
        if "data.zero" not in local and "data.fill(0)" not in local:
            findings.append({
                "class": "close_reinit_bypass",
                "subclass": "lamports_zero_without_data_clear",
                "file": str(path), "line": line_no,
                "advice": "Lamports set to 0 without data zero-fill. Account memory remains readable → stale discriminator attack.",
                "severity": "high", "classification": "novel_instance",
            })

    return findings


def main():
    ap = argparse.ArgumentParser(description="Detect close+reinit bypass")
    ap.add_argument("--target", required=True)
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    target = Path(args.target)
    files = [target] if target.is_file() and target.suffix == ".rs" else list(target.rglob("*.rs")) if target.is_dir() else []
    if not files: print(f"[!] No .rs files", file=sys.stderr); sys.exit(1)
    all_findings = []
    for f in files:
        if "/target/" in str(f).replace("\\", "/"): continue
        all_findings.extend(scan_file(f))
    if not args.quiet: print(f"[+] Close+reinit findings: {len(all_findings)}")
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "close_reinit_findings.json").write_text(json.dumps(all_findings, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
