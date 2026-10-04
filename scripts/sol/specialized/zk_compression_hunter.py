#!/usr/bin/env python3
"""zk_compression_hunter.py — Light Protocol-class ZK compression hunter."""
import argparse, json, re, sys
from pathlib import Path

CHECKS = [
    ("validity_proof", re.compile(r"validity_proof|compressed_proof"), "Validity proof verification — completeness of public inputs in challenge"),
    ("state_root", re.compile(r"state_root|merkle_root|tree_root"), "State root attacks — verify nullifier check, root freshness"),
    ("nullifier", re.compile(r"nullifier|spent_set"), "Nullifier set — verify uniqueness check, no replay"),
    ("batch_verify", re.compile(r"batch_verify|verify_batch"), "Batch verification — verify each proof independent (no aggregation collapse)"),
    ("compressed_account", re.compile(r"compressed_account|compressed_data"), "Compressed account data — off-chain availability + on-chain root sync"),
]

def scan_file(path):
    try: text = path.read_text(encoding="utf-8", errors="ignore")
    except: return []
    out = []; lines = text.splitlines()
    for cid, r, advice in CHECKS:
        for m in r.finditer(text):
            ln = text[:m.start()].count("\n") + 1
            snip = lines[ln-1].strip()[:140] if ln <= len(lines) else ""
            out.append({"class": "zk_compression", "subclass": cid, "file": str(path), "line": ln, "snippet": snip, "advice": advice, "severity": "high", "classification": "novel_instance", "experimental": True})
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
    if not args.quiet: print(f"[+] ZK compression findings (experimental): {len(all_f)}")
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "zk_compression_findings.json").write_text(json.dumps(all_f, indent=2), encoding="utf-8")

if __name__ == "__main__": main()
