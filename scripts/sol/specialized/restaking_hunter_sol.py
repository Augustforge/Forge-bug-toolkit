#!/usr/bin/env python3
"""
restaking_hunter_sol.py — Jito/Marinade/Sanctum LST hunter.
"""
import argparse, json, re, sys
from pathlib import Path

CHECKS = [
    ("withdrawal_queue", re.compile(r"withdrawal_queue|unstake_request"), "Withdrawal queue — verify FIFO, no skip-ahead, no double-claim"),
    ("slash_distribution", re.compile(r"slash|penalty"), "Slash distribution — verify pro-rata, no exit before slash"),
    ("lst_oracle", re.compile(r"lst_price|stake_pool_price"), "LST oracle — staleness, manipulation, marinade/jito specific"),
    ("validator_set", re.compile(r"validator_list|active_validators"), "Validator set — verify weights, exits handled"),
    ("delegation_authority", re.compile(r"delegate_stake|undelegate"), "Stake delegation — authority check, signer verify"),
    ("fee_accrual", re.compile(r"reward_fee|management_fee"), "Fee accrual — verify rounding direction, max cap"),
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
            out.append({
                "class": "restaking_specialized", "subclass": cid,
                "file": str(path), "line": ln, "snippet": snip,
                "advice": advice, "severity": "high", "classification": "novel_instance",
            })
    return out


def main():
    ap = argparse.ArgumentParser(description="Solana restaking hunter")
    ap.add_argument("--target", required=True); ap.add_argument("--output", default=None); ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    target = Path(args.target)
    files = [target] if target.is_file() and target.suffix == ".rs" else list(target.rglob("*.rs")) if target.is_dir() else []
    if not files: print("[!] No .rs", file=sys.stderr); sys.exit(1)
    all_f = []
    for f in files:
        if "/target/" in str(f).replace("\\", "/"): continue
        all_f.extend(scan_file(f))
    if not args.quiet: print(f"[+] Restaking findings: {len(all_f)}")
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "restaking_findings.json").write_text(json.dumps(all_f, indent=2), encoding="utf-8")

if __name__ == "__main__": main()
