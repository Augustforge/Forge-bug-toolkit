#!/usr/bin/env python3
"""state_setup_miner_sol.py — rare Solana state configs that trigger bugs."""
import argparse, json, re, sys
from pathlib import Path

RARE_CONFIGS = [
    ("zero_threshold", re.compile(r"threshold\s*[=:]\s*0"), "Threshold=0 → no signatures required"),
    ("max_supply", re.compile(r"supply\s*[=:]\s*u64::MAX|supply\s*[=:]\s*0xFFFF"), "Max supply edge"),
    ("zero_fee", re.compile(r"fee\s*[=:]\s*0\b"), "Zero fee → fee bypass via crafted amounts"),
    ("max_fee", re.compile(r"fee\s*[=:]\s*10000|fee\s*[=:]\s*100\s*%"), "100% fee → user receives nothing"),
    ("empty_signers", re.compile(r"signers\s*[=:]\s*\[\s*\]"), "Empty signers list"),
    ("single_validator", re.compile(r"validators\s*[=:]\s*vec!\s*\[\s*\w+\s*\]"), "Single validator — centralization"),
    ("zero_decimals", re.compile(r"decimals\s*[=:]\s*0\b"), "0 decimals → precision loss"),
    ("18_decimals_on_sol", re.compile(r"decimals\s*[=:]\s*18\b"), "18 decimals on Solana — unusual, check math"),
]

def scan_file(path):
    try: text = path.read_text(encoding="utf-8", errors="ignore")
    except: return []
    out = []; lines = text.splitlines()
    for cid, r, advice in RARE_CONFIGS:
        for m in r.finditer(text):
            ln = text[:m.start()].count("\n") + 1
            snip = lines[ln-1].strip()[:140] if ln <= len(lines) else ""
            out.append({"class": "rare_state_config", "subclass": cid, "file": str(path), "line": ln, "snippet": snip, "advice": advice, "severity": "medium", "classification": "novel_instance"})
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
    if not args.quiet: print(f"[+] Rare state configs: {len(all_f)}")
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "rare_configs.json").write_text(json.dumps(all_f, indent=2), encoding="utf-8")

if __name__ == "__main__": main()
