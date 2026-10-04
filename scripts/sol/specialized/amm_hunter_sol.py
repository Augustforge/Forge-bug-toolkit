#!/usr/bin/env python3
"""
amm_hunter_sol.py — Raydium/Orca/Phoenix-class AMM hunting.

Targets:
- Tick array account validation (Raydium 2024 pattern)
- Tick manipulation (Crema 2022)
- sqrtPriceX64 overflow
- Concentrated liquidity edge cases
- remaining_accounts validation
- Bidirectional rounding in swap math
- LP token donation / first-depositor
"""
import argparse, json, re, sys
from pathlib import Path

CHECKS = [
    ("tick_array_no_validation", re.compile(r"tick_array|TickArray", re.IGNORECASE), "Tick array account passed — verify key matches expected via require_keys_eq!"),
    ("remaining_accounts_used", re.compile(r"remaining_accounts\s*\[\s*\d+\s*\]"), "remaining_accounts[N] indexed — must validate each account before use (Raydium 2024 pattern)"),
    ("sqrt_price_unchecked", re.compile(r"sqrt_price.*=|sqrtPriceX64"), "sqrt price calc — verify checked_mul/div, watch overflow at extreme ticks"),
    ("lp_donation_surface", re.compile(r"pool\.\w*reserve|pool\.\w*balance"), "Pool reserve read — verify via .amount field, not balance() (donation attack vector)"),
    ("swap_no_slippage", re.compile(r"fn\s+swap\s*\("), "Swap function — verify amount_out >= minimum_amount_out enforced"),
    ("oracle_dependency", re.compile(r"oracle|price_feed|aggregator"), "Oracle dependency — verify staleness check + manipulation resistance"),
    ("fee_collection_drift", re.compile(r"protocol_fee|swap_fee"), "Fee math — verify rounding direction symmetric with swap rounding"),
]


def scan_file(path):
    try: text = path.read_text(encoding="utf-8", errors="ignore")
    except: return []
    out = []
    lines = text.splitlines()
    for cid, regex, advice in CHECKS:
        for m in regex.finditer(text):
            ln = text[:m.start()].count("\n") + 1
            snip = lines[ln-1].strip()[:140] if ln <= len(lines) else ""
            severity = "critical" if cid in ("tick_array_no_validation", "remaining_accounts_used") else "high"
            classification = "known_class" if cid == "tick_array_no_validation" else "novel_instance"
            out.append({
                "class": "amm_specialized", "subclass": cid,
                "file": str(path), "line": ln, "snippet": snip,
                "advice": advice, "severity": severity, "classification": classification,
            })
    return out


def main():
    ap = argparse.ArgumentParser(description="Solana AMM hunter")
    ap.add_argument("--target", required=True); ap.add_argument("--output", default=None); ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    target = Path(args.target)
    files = [target] if target.is_file() and target.suffix == ".rs" else list(target.rglob("*.rs")) if target.is_dir() else []
    if not files: print("[!] No .rs", file=sys.stderr); sys.exit(1)
    all_f = []
    for f in files:
        if "/target/" in str(f).replace("\\", "/"): continue
        all_f.extend(scan_file(f))
    if not args.quiet:
        print(f"[+] AMM findings: {len(all_f)}")
        by = {}
        for f in all_f: by[f["subclass"]] = by.get(f["subclass"], 0) + 1
        for k, v in sorted(by.items(), key=lambda x: -x[1]): print(f"  {k:30} {v}")
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "amm_findings.json").write_text(json.dumps(all_f, indent=2), encoding="utf-8")

if __name__ == "__main__": main()
