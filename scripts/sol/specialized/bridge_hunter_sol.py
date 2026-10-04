#!/usr/bin/env python3
"""
bridge_hunter_sol.py — Wormhole-class bridge hunter.

Targets:
- VAA (Verifiable Action Approval) reuse / replay
- Signature account validation (Wormhole 2022 root cause)
- Guardian set transitions
- chainId in message hash
- Sequence number monotonicity
"""
import argparse, json, re, sys
from pathlib import Path

CHECKS = [
    ("vaa_validation", re.compile(r"vaa|VAA|verifiable_action"), "VAA verification — replay protection? Sequence enforced? Guardian set verified?"),
    ("signature_set_account", re.compile(r"signature_set|SignatureSet"), "SignatureSet account — Wormhole 2022 root cause. Verify owner + signer."),
    ("guardian_set", re.compile(r"guardian_set|GuardianSet"), "Guardian set — verify active index, expiration, threshold"),
    ("chain_id_in_hash", re.compile(r"keccak.*chain|hash.*chain_id"), "ChainId in hash? Critical for cross-chain replay protection."),
    ("sequence_check", re.compile(r"sequence\s*[><=]"), "Sequence number — verify monotonic increase, no skip"),
    ("emitter_check", re.compile(r"emitter|emitter_chain"), "Emitter verification — verify emitter authorized in config"),
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
            severity = "critical" if cid in ("signature_set_account", "chain_id_in_hash") else "high"
            out.append({
                "class": "bridge_specialized", "subclass": cid,
                "file": str(path), "line": ln, "snippet": snip,
                "advice": advice, "severity": severity,
                "classification": "known_class" if cid == "signature_set_account" else "novel_instance",
            })
    return out


def main():
    ap = argparse.ArgumentParser(description="Solana bridge hunter")
    ap.add_argument("--target", required=True); ap.add_argument("--output", default=None); ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    target = Path(args.target)
    files = [target] if target.is_file() and target.suffix == ".rs" else list(target.rglob("*.rs")) if target.is_dir() else []
    if not files: print("[!] No .rs", file=sys.stderr); sys.exit(1)
    all_f = []
    for f in files:
        if "/target/" in str(f).replace("\\", "/"): continue
        all_f.extend(scan_file(f))
    if not args.quiet: print(f"[+] Bridge findings: {len(all_f)}")
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "bridge_findings.json").write_text(json.dumps(all_f, indent=2), encoding="utf-8")

if __name__ == "__main__": main()
