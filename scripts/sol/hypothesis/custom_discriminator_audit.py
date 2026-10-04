#!/usr/bin/env python3
"""
custom_discriminator_audit.py — Anchor 0.30+ custom discriminator audit.

CLASS: custom discriminators (#[instruction(discriminator = [...])]) allow
overlapping prefixes between account types → confusion.
"""
import argparse
import json
import re
import sys
from pathlib import Path

CUSTOM_DISC_RE = re.compile(r"#\[instruction\([^)]*discriminator\s*=\s*\[([^\]]+)\]")


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    findings = []
    for m in CUSTOM_DISC_RE.finditer(text):
        line_no = text[: m.start()].count("\n") + 1
        findings.append({
            "class": "custom_discriminator",
            "file": str(path), "line": line_no,
            "discriminator_bytes": m.group(1).strip(),
            "advice": "Custom discriminator detected. Run discriminator_collision.py for overlap check. "
                      "Anchor 0.31+ has built-in ambiguity check, but legacy programs are vulnerable.",
            "severity": "medium", "classification": "novel_instance",
        })
    return findings


def main():
    ap = argparse.ArgumentParser(description="Audit custom discriminators")
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
    if not args.quiet: print(f"[+] Custom discriminator findings: {len(all_findings)}")
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "custom_discriminator_findings.json").write_text(json.dumps(all_findings, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
