#!/usr/bin/env python3
"""memecoin_launcher_hunter.py — pump.fun-class hunter."""
import argparse, json, re, sys
from pathlib import Path

CHECKS = [
    ("bonding_curve_math", re.compile(r"bonding_curve|curve\.\w+\(|virtual_reserves"), "Bonding curve math — verify monotonic, no overflow at thresholds, fee not 100%"),
    ("graduation_threshold", re.compile(r"graduate|migration_threshold|liquidity_threshold"), "Graduation logic — verify threshold cannot be gamed, atomic migration"),
    ("creator_fee", re.compile(r"creator_fee|creator_share"), "Creator fee — verify cap, recipient validation"),
    ("anti_sniper", re.compile(r"anti_sniper|first_block|launch_block"), "Anti-sniper logic — verify cannot be bypassed via direct tx"),
    ("withdrawal_trust", re.compile(r"withdraw_liquidity|drain_pool"), "Liquidity withdrawal — admin only? Sole creator? Rug-pull surface."),
]

def scan_file(path):
    try: text = path.read_text(encoding="utf-8", errors="ignore")
    except: return []
    out = []; lines = text.splitlines()
    for cid, r, advice in CHECKS:
        for m in r.finditer(text):
            ln = text[:m.start()].count("\n") + 1
            snip = lines[ln-1].strip()[:140] if ln <= len(lines) else ""
            out.append({"class": "memecoin_launcher", "subclass": cid, "file": str(path), "line": ln, "snippet": snip, "advice": advice, "severity": "high", "classification": "novel_instance"})
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--target", required=True); ap.add_argument("--output"); ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(); target = Path(args.target)
    files = [target] if target.is_file() and target.suffix == ".rs" else list(target.rglob("*.rs")) if target.is_dir() else []
    if not files: print("[!] No .rs", file=sys.stderr); sys.exit(1)
    all_f = []
    for f in files:
        if "/target/" in str(f).replace("\\", "/"): continue
        all_f.extend(scan_file(f))
    if not args.quiet: print(f"[+] Memecoin findings: {len(all_f)}")
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "memecoin_findings.json").write_text(json.dumps(all_f, indent=2), encoding="utf-8")

if __name__ == "__main__": main()
