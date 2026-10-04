#!/usr/bin/env python3
"""
sysvar_trust_scanner.py — fake sysvar account injection detection.

CLASS: Clock/Rent/StakeHistory passed as raw AccountInfo (no type check) →
attacker can substitute fake sysvar.
"""
import argparse
import json
import re
import sys
from pathlib import Path

SYSVAR_NAMES = ["clock", "rent", "stake_history", "recent_blockhashes", "instructions", "slot_hashes", "epoch_schedule"]
SYSVAR_AS_ACCOUNTINFO_RE = re.compile(
    r"pub\s+(" + "|".join(SYSVAR_NAMES) + r"):\s*AccountInfo<", re.IGNORECASE,
)
SYSVAR_AS_UNCHECKED_RE = re.compile(
    r"pub\s+(" + "|".join(SYSVAR_NAMES) + r"):\s*UncheckedAccount<", re.IGNORECASE,
)


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    findings = []
    lines = text.splitlines()
    for regex, subclass in [(SYSVAR_AS_ACCOUNTINFO_RE, "as_accountinfo"), (SYSVAR_AS_UNCHECKED_RE, "as_unchecked")]:
        for m in regex.finditer(text):
            name = m.group(1)
            line_no = text[: m.start()].count("\n") + 1
            snippet = lines[line_no - 1].strip()[:140] if line_no <= len(lines) else ""
            findings.append({
                "class": "sysvar_trust",
                "subclass": subclass,
                "file": str(path), "line": line_no,
                "sysvar_name": name,
                "snippet": snippet,
                "advice": f"Sysvar `{name}` as raw account — fake sysvar substitution possible. "
                          f"Use `Sysvar<'info, {name.capitalize()}>` typed wrapper.",
                "severity": "high", "classification": "known_class",
            })
    return findings


def main():
    ap = argparse.ArgumentParser(description="Detect sysvar trust gaps")
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
    if not args.quiet: print(f"[+] Sysvar trust findings: {len(all_findings)}")
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "sysvar_findings.json").write_text(json.dumps(all_findings, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
