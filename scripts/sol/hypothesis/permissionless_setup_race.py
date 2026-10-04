#!/usr/bin/env python3
"""
permissionless_setup_race.py — IDL takeover + one-time setup races.

CLASS: permissionless one-time setup operations (IDL claim, vault init,
admin first-claim) → attacker can claim authority before legitimate deploy.
"""
import argparse, json, re, sys
from pathlib import Path

SETUP_PATTERNS = [
    ("idl_create", re.compile(r"IdlCreateAccount|idl.*authority")),
    ("first_init", re.compile(r"initialize\s*\([^)]*\)\s*->\s*Result")),
    ("set_authority", re.compile(r"set_authority|transfer_authority")),
    ("first_admin", re.compile(r"fn\s+initialize_admin|fn\s+set_admin")),
]
ACCESS_GUARD_RE = re.compile(r"only_admin|only_owner|require!\s*\([^)]*\.is_signer|has_one\s*=")
ONE_TIME_GUARD_RE = re.compile(r"is_initialized|already_init|first_time")


def scan_file(path):
    try: text = path.read_text(encoding="utf-8", errors="ignore")
    except: return []
    out = []
    lines = text.splitlines()
    for name, regex in SETUP_PATTERNS:
        for m in regex.finditer(text):
            ln = text[:m.start()].count("\n") + 1
            ctx = text[max(0, m.start()-300): m.end()+600]
            has_access = bool(ACCESS_GUARD_RE.search(ctx))
            has_one_time = bool(ONE_TIME_GUARD_RE.search(ctx))
            if not has_access and not has_one_time:
                snip = lines[ln-1].strip()[:140] if ln <= len(lines) else ""
                out.append({
                    "class": "permissionless_setup_race", "subclass": name,
                    "file": str(path), "line": ln, "snippet": snip,
                    "advice": f"{name} appears permissionless and without a one-time guard. "
                              f"Attacker can claim authority before legitimate caller.",
                    "severity": "high", "classification": "novel_instance",
                })
    return out


def main():
    ap = argparse.ArgumentParser(description="Detect permissionless setup races")
    ap.add_argument("--target", required=True); ap.add_argument("--output", default=None); ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    target = Path(args.target)
    files = [target] if target.is_file() and target.suffix == ".rs" else list(target.rglob("*.rs")) if target.is_dir() else []
    if not files: print("[!] No .rs", file=sys.stderr); sys.exit(1)
    all_f = []
    for f in files:
        if "/target/" in str(f).replace("\\", "/"): continue
        all_f.extend(scan_file(f))
    if not args.quiet: print(f"[+] Permissionless setup races: {len(all_f)}")
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "permissionless_setup_findings.json").write_text(json.dumps(all_f, indent=2), encoding="utf-8")

if __name__ == "__main__": main()
