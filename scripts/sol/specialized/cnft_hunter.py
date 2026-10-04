#!/usr/bin/env python3
"""cnft_hunter.py — Compressed NFT / Bubblegum hunter."""
import argparse, json, re, sys
from pathlib import Path

CHECKS = [
    ("merkle_proof", re.compile(r"verify_proof|MerkleProof|merkle_verify"), "Merkle proof — verify leaf hash domain (prefix), correct depth"),
    ("canopy_depth", re.compile(r"canopy|max_depth|tree_depth"), "Canopy depth — verify config bounds, gas cost vs storage"),
    ("leaf_data", re.compile(r"leaf_node|data_hash|creator_hash"), "Leaf hashing — verify all fields included, no padding attack"),
    ("concurrent_mutation", re.compile(r"replace_leaf|append_leaf"), "Concurrent mutation — race conditions in tree update?"),
    ("delegate_authority", re.compile(r"delegate_authority|transfer.*compressed"), "cNFT delegation — verify authority chain integrity"),
]

def scan_file(path):
    try: text = path.read_text(encoding="utf-8", errors="ignore")
    except: return []
    out = []; lines = text.splitlines()
    for cid, r, advice in CHECKS:
        for m in r.finditer(text):
            ln = text[:m.start()].count("\n") + 1
            snip = lines[ln-1].strip()[:140] if ln <= len(lines) else ""
            out.append({"class": "cnft", "subclass": cid, "file": str(path), "line": ln, "snippet": snip, "advice": advice, "severity": "high", "classification": "novel_instance", "experimental": True})
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
    if not args.quiet: print(f"[+] cNFT findings (experimental): {len(all_f)}")
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "cnft_findings.json").write_text(json.dumps(all_f, indent=2), encoding="utf-8")

if __name__ == "__main__": main()
