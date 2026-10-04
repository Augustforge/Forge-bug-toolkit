#!/usr/bin/env python3
"""
token_extensions_hunter.py — Token-2022 extensions hunter.

Targets:
- Transfer hooks (reentrancy import)
- Confidential transfers (ZK proof completeness)
- Interest-bearing (rate manipulation)
- Transfer fees (calc precision)
- Freeze authority drift
- Mint close authority
- Non-transferable enforcement
"""
import argparse, json, re, sys
from pathlib import Path

CHECKS = [
    ("transfer_hook", re.compile(r"TransferHook|transfer_hook|HookInstruction"), "Transfer hook — CPI to hook program mid-transfer → reentrancy surface"),
    ("confidential_transfer", re.compile(r"ConfidentialTransfer|elgamal|zk_proof"), "Confidential transfer — verify ZK proof completeness (Fiat-Shamir hash inputs)"),
    ("interest_bearing", re.compile(r"InterestBearing|interest_rate"), "Interest-bearing extension — rate update authority? Manipulation?"),
    ("transfer_fee", re.compile(r"TransferFee|transfer_fee_config"), "Transfer fee — fee math precision, max fee enforcement, fee recipient"),
    ("freeze_authority", re.compile(r"freeze_authority|MintFreeze"), "Freeze authority — verify lifecycle, drift to attacker"),
    ("mint_close_authority", re.compile(r"MintCloseAuthority|close_mint"), "Mint close — verify lamports drain protection"),
    ("non_transferable", re.compile(r"NonTransferable"), "Non-transferable extension — verify ALL transfer paths blocked, including burn-then-mint trick"),
    ("default_account_state", re.compile(r"DefaultAccountState|frozen.*default"), "Default frozen accounts — bypass paths?"),
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
            severity = "high" if cid in ("transfer_hook", "confidential_transfer") else "medium"
            out.append({
                "class": "token_extensions", "subclass": cid,
                "file": str(path), "line": ln, "snippet": snip,
                "advice": advice, "severity": severity, "classification": "novel_instance",
            })
    return out


def main():
    ap = argparse.ArgumentParser(description="Token-2022 extensions hunter")
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
        print(f"[+] Token-2022 findings: {len(all_f)}")
        by = {}
        for f in all_f: by[f["subclass"]] = by.get(f["subclass"], 0) + 1
        for k, v in sorted(by.items(), key=lambda x: -x[1]): print(f"  {k:30} {v}")
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "token_extensions_findings.json").write_text(json.dumps(all_f, indent=2), encoding="utf-8")

if __name__ == "__main__": main()
