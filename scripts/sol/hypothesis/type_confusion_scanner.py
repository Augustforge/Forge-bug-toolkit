#!/usr/bin/env python3
"""
type_confusion_scanner.py — AccountInfo → T cast without a discriminator check.
"""
import argparse, json, re, sys
from pathlib import Path

CAST_RE = re.compile(r"try_from_account_info\s*\(|AccountInfo\s*::\s*try_into|\.try_to::<\w+>\(")
DISC_CHECK_NEARBY = re.compile(r"DISCRIMINATOR|discriminator\s*\[")


def scan_file(path):
    try: text = path.read_text(encoding="utf-8", errors="ignore")
    except: return []
    out = []
    lines = text.splitlines()
    for m in CAST_RE.finditer(text):
        ln = text[:m.start()].count("\n") + 1
        ctx = text[max(0, m.start()-200): m.end()+200]
        if DISC_CHECK_NEARBY.search(ctx): continue
        snip = lines[ln-1].strip()[:140] if ln <= len(lines) else ""
        out.append({
            "class": "type_confusion", "file": str(path), "line": ln, "snippet": snip,
            "advice": "Account cast without discriminator verification — attacker can pass a wrong-type account with a matching layout.",
            "severity": "high", "classification": "novel_instance",
        })
    return out


def main():
    ap = argparse.ArgumentParser(description="Detect type confusion casts")
    ap.add_argument("--target", required=True); ap.add_argument("--output", default=None); ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    target = Path(args.target)
    files = [target] if target.is_file() and target.suffix == ".rs" else list(target.rglob("*.rs")) if target.is_dir() else []
    if not files: print("[!] No .rs", file=sys.stderr); sys.exit(1)
    all_f = []
    for f in files:
        if "/target/" in str(f).replace("\\", "/"): continue
        all_f.extend(scan_file(f))
    if not args.quiet: print(f"[+] Type confusion: {len(all_f)}")
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "type_confusion_findings.json").write_text(json.dumps(all_f, indent=2), encoding="utf-8")

if __name__ == "__main__": main()
