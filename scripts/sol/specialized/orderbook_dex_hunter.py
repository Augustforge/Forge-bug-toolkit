#!/usr/bin/env python3
"""orderbook_dex_hunter.py — OpenBook/Phoenix hunter."""
import argparse, json, re, sys
from pathlib import Path

CHECKS = [
    ("matching_engine", re.compile(r"match_orders|fill_order|cross_orders"), "Order matching — verify price priority, time priority, partial fill atomicity"),
    ("settlement_atomic", re.compile(r"settle_funds|settle_trade"), "Settlement — verify atomic (no partial state on revert)"),
    ("self_trade", re.compile(r"self_trade|same_user"), "Self-trade detection — verify cannot wash trade or manipulate price"),
    ("order_cancellation", re.compile(r"cancel_order|cancel_all"), "Cancellation — verify authorization, no front-run by canceller"),
    ("market_maker_rebate", re.compile(r"maker_rebate|maker_fee.*-"), "Maker rebate — verify negative fee doesn't underflow / drain"),
]

def scan_file(path):
    try: text = path.read_text(encoding="utf-8", errors="ignore")
    except: return []
    out = []; lines = text.splitlines()
    for cid, r, advice in CHECKS:
        for m in r.finditer(text):
            ln = text[:m.start()].count("\n") + 1
            snip = lines[ln-1].strip()[:140] if ln <= len(lines) else ""
            out.append({"class": "orderbook_dex", "subclass": cid, "file": str(path), "line": ln, "snippet": snip, "advice": advice, "severity": "high", "classification": "novel_instance"})
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
    if not args.quiet: print(f"[+] Orderbook findings: {len(all_f)}")
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "orderbook_findings.json").write_text(json.dumps(all_f, indent=2), encoding="utf-8")

if __name__ == "__main__": main()
