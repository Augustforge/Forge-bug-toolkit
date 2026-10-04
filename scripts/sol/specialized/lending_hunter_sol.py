#!/usr/bin/env python3
"""
lending_hunter_sol.py — Solend/MarginFi/Kamino-class lending.

Targets:
- Flash loan state flag checks (Marginfi 2025)
- Health factor calc paths
- Liquidation math (bonus, threshold)
- Oracle price dependency
- Interest accrual edge cases
- Precision loss in exchange rate (Kamino)
- Collateral seizure ownership
"""
import argparse, json, re, sys
from pathlib import Path

CHECKS = [
    ("flash_loan_flag", re.compile(r"flash_loan|FLASHLOAN|in_flashloan", re.IGNORECASE), "Flash loan flag detected — verify ALL state-changing instructions check this flag (Marginfi 2025)"),
    ("health_check_path", re.compile(r"check_health|health_factor|account_health"), "Health check found — verify EVERY borrow/withdraw path triggers it"),
    ("liquidation_math", re.compile(r"liquidate|liquidation"), "Liquidation — verify bonus calc, threshold, partial vs full"),
    ("oracle_price_use", re.compile(r"oracle.*price|price_feed"), "Price feed — staleness, manipulation, multiple sources?"),
    ("interest_accrual", re.compile(r"accrue_interest|interest_index"), "Interest accrual — verify time-based math overflow, rounding"),
    ("exchange_rate_calc", re.compile(r"exchange_rate|share_price|asset_to_share"), "Exchange rate calc — Kamino-class precision loss in inverse ops"),
    ("collateral_seize", re.compile(r"seize_collateral|withdraw_collateral"), "Collateral seize — verify ownership transferred atomically with debt clearance"),
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
            severity = "critical" if cid in ("flash_loan_flag", "health_check_path") else "high"
            classification = "known_class" if cid == "flash_loan_flag" else "novel_instance"
            out.append({
                "class": "lending_specialized", "subclass": cid,
                "file": str(path), "line": ln, "snippet": snip,
                "advice": advice, "severity": severity, "classification": classification,
            })
    return out


def main():
    ap = argparse.ArgumentParser(description="Solana lending hunter")
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
        print(f"[+] Lending findings: {len(all_f)}")
        by = {}
        for f in all_f: by[f["subclass"]] = by.get(f["subclass"], 0) + 1
        for k, v in sorted(by.items(), key=lambda x: -x[1]): print(f"  {k:30} {v}")
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "lending_findings.json").write_text(json.dumps(all_f, indent=2), encoding="utf-8")

if __name__ == "__main__": main()
