#!/usr/bin/env python3
"""multisig_hunter.py — Squads-class multisig hunter."""
import argparse, json, re, sys
from pathlib import Path

CHECKS = [
    ("threshold_validation", re.compile(r"threshold|min_signers|required_signatures"), "Multisig threshold — verify <= total signers, > 0"),
    ("approval_replay", re.compile(r"approve_proposal|approval\.count"), "Approval — verify cannot be double-counted (same signer twice)"),
    ("durable_nonce_usage", re.compile(r"durable_nonce|advance_nonce"), "Durable nonce in multisig flow — Drift 2026 pattern, signers should expire"),
    ("execution_delay", re.compile(r"execution_delay|time_lock|approval_expires"), "Execution delay — verify timelock present and non-zero"),
    ("transaction_replay", re.compile(r"executed\s*=|is_executed"), "Replay protection — verify executed flag cannot be reset"),
    ("signer_set_change", re.compile(r"add_signer|remove_signer|change_signers"), "Signer set changes — verify multi-step + timelock"),
]

def scan_file(path):
    try: text = path.read_text(encoding="utf-8", errors="ignore")
    except: return []
    out = []; lines = text.splitlines()
    for cid, r, advice in CHECKS:
        for m in r.finditer(text):
            ln = text[:m.start()].count("\n") + 1
            snip = lines[ln-1].strip()[:140] if ln <= len(lines) else ""
            sev = "critical" if cid == "durable_nonce_usage" else "high"
            out.append({"class": "multisig", "subclass": cid, "file": str(path), "line": ln, "snippet": snip, "advice": advice, "severity": sev, "classification": "known_class" if cid == "durable_nonce_usage" else "novel_instance"})
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
    if not args.quiet: print(f"[+] Multisig findings: {len(all_f)}")
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "multisig_findings.json").write_text(json.dumps(all_f, indent=2), encoding="utf-8")

if __name__ == "__main__": main()
