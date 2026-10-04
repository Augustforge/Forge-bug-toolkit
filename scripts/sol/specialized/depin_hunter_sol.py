#!/usr/bin/env python3
"""depin_hunter_sol.py — Helium/Render/IO.net/Hivemapper DePIN hunter."""
import argparse, json, re, sys
from pathlib import Path

CHECKS = [
    ("reward_distribution", re.compile(r"distribute_reward|claim_reward|emission"), "Reward distribution — verify pro-rata, no double-claim, time-locked"),
    ("oracle_attestation", re.compile(r"attestation|proof_of_coverage|signed_attestation"), "Off-chain attestation — signature verification? Replay protection? Time bounding?"),
    ("hardware_identity", re.compile(r"hardware_id|device_id|node_pubkey"), "Hardware identity — verify uniqueness, prevent multi-claim same device"),
    ("data_proof", re.compile(r"data_proof|merkle.*proof"), "Data proof verification — Merkle tree integrity, leaf hash domain"),
    ("subnet_governance", re.compile(r"subnet|hex.*allocation"), "Subnet allocation — gameable? Verify constraints"),
]

def scan_file(path):
    try: text = path.read_text(encoding="utf-8", errors="ignore")
    except: return []
    out = []; lines = text.splitlines()
    for cid, r, advice in CHECKS:
        for m in r.finditer(text):
            ln = text[:m.start()].count("\n") + 1
            snip = lines[ln-1].strip()[:140] if ln <= len(lines) else ""
            out.append({"class": "depin", "subclass": cid, "file": str(path), "line": ln, "snippet": snip, "advice": advice, "severity": "high", "classification": "novel_instance", "experimental": True})
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
    if not args.quiet: print(f"[+] DePIN findings (experimental): {len(all_f)}")
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "depin_findings.json").write_text(json.dumps(all_f, indent=2), encoding="utf-8")

if __name__ == "__main__": main()
