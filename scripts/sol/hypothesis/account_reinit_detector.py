#!/usr/bin/env python3
"""
account_reinit_detector.py — `init` without already-init guard.

CLASS: Account::init reachable twice for the same account → state reset.
"""
import argparse
import json
import re
import sys
from pathlib import Path

INIT_ATTR_RE = re.compile(r"#\[account\(\s*init\s*[,)]")
INIT_IF_NEEDED_RE = re.compile(r"init_if_needed")
CONSTRAINT_RE = re.compile(r"constraint\s*=")


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    findings = []
    lines = text.splitlines()

    for m in INIT_ATTR_RE.finditer(text):
        line_no = text[: m.start()].count("\n") + 1
        local = text[max(0, m.start() - 50): m.end() + 300]
        if INIT_IF_NEEDED_RE.search(local):
            findings.append({
                "class": "account_reinit",
                "subclass": "init_if_needed_without_guard",
                "file": str(path), "line": line_no,
                "advice": "init_if_needed permits re-initialization. Add constraint check on existing data.",
                "severity": "medium", "classification": "novel_instance",
            })
        elif not CONSTRAINT_RE.search(local):
            findings.append({
                "class": "account_reinit",
                "subclass": "init_without_constraint",
                "file": str(path), "line": line_no,
                "advice": "Anchor init without constraint guard. Verify race conditions in account creation flow.",
                "severity": "low", "classification": "novel_instance",
            })
    return findings


def main():
    ap = argparse.ArgumentParser(description="Detect account reinit gaps")
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
    if not args.quiet: print(f"[+] Account reinit findings: {len(all_findings)}")
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "account_reinit_findings.json").write_text(json.dumps(all_findings, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
