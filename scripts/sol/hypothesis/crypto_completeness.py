#!/usr/bin/env python3
"""
crypto_completeness.py — Cryptographic completeness gaps audit.

CLASS: cryptographic primitives with incomplete hash inputs, missing nonce/chain
binding, partial domain separators, signature subset attacks.
"""
import argparse, json, re, sys
from pathlib import Path

PATTERNS = [
    ("hash_missing_chain", re.compile(r"keccak|sha256|hash\s*\("), "Hash op — verify chainId / program_id included in input"),
    ("ecrecover_no_v_check", re.compile(r"secp256k1_recover|ecrecover"), "secp256k1 recovery — verify v ∈ {0,1} or {27,28} to block malleability"),
    ("partial_domain", re.compile(r"DOMAIN_SEPARATOR|domain_sep"), "Domain separator — must include chainId + program_id + version"),
    ("vrf_predictable", re.compile(r"random|seed.*=.*clock|prng"), "Pseudo-random source — verify not based on predictable values (timestamp, slot)"),
    ("zk_proof", re.compile(r"verify_proof|zk_proof|fiat_shamir"), "ZK proof verification — verify ALL public inputs hashed into challenge"),
]


def scan_file(path):
    try: text = path.read_text(encoding="utf-8", errors="ignore")
    except: return []
    out = []
    lines = text.splitlines()
    for pid, regex, advice in PATTERNS:
        for m in regex.finditer(text):
            ln = text[:m.start()].count("\n") + 1
            snip = lines[ln-1].strip()[:140] if ln <= len(lines) else ""
            severity = "high" if pid == "zk_proof" else "medium"
            out.append({
                "class": "crypto_completeness", "subclass": pid,
                "file": str(path), "line": ln, "snippet": snip,
                "advice": advice,
                "severity": severity, "classification": "novel_instance",
            })
    return out


def main():
    ap = argparse.ArgumentParser(description="Audit cryptographic completeness")
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
        print(f"[+] Crypto completeness findings: {len(all_f)}")
        by = {}
        for f in all_f:
            by[f["subclass"]] = by.get(f["subclass"], 0) + 1
        for k, v in by.items(): print(f"  {k:25} {v}")
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "crypto_completeness_findings.json").write_text(json.dumps(all_f, indent=2), encoding="utf-8")

if __name__ == "__main__": main()
