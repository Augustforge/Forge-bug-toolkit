#!/usr/bin/env python3
"""
compute_dos_analyzer.py — unbounded loops, large allocs, CU budget DoS.
"""
import argparse, json, re, sys
from pathlib import Path

UNBOUNDED_LOOP_RE = re.compile(r"for\s+\w+\s+in\s+(\w+)(?:\.iter\(\))?\s*\{|while\s+!?\w+", re.MULTILINE)
LARGE_ALLOC_RE = re.compile(r"vec!\[\s*0\s*;\s*(\d+)\s*\]|Vec::with_capacity\s*\(\s*(\d+)\s*\)")
HEAVY_OP_IN_LOOP_RE = re.compile(r"for[^{]*\{[^}]*(?:invoke|find_program_address|hash|crypto)", re.DOTALL)


def scan_file(path):
    try: text = path.read_text(encoding="utf-8", errors="ignore")
    except: return []
    out = []
    lines = text.splitlines()
    for m in UNBOUNDED_LOOP_RE.finditer(text):
        ln = text[:m.start()].count("\n") + 1
        local = text[m.start(): min(len(text), m.start()+300)]
        if ".take(" in local or "break" in local or "MAX_" in local: continue
        snip = lines[ln-1].strip()[:140] if ln <= len(lines) else ""
        out.append({
            "class": "compute_dos", "subclass": "unbounded_loop",
            "file": str(path), "line": ln, "snippet": snip,
            "advice": "Unbounded loop — compute budget DoS possible. Add explicit bound or .take(MAX).",
            "severity": "medium", "classification": "known_class",
        })
    for m in LARGE_ALLOC_RE.finditer(text):
        size = int(m.group(1) or m.group(2) or 0)
        if size > 10000:
            ln = text[:m.start()].count("\n") + 1
            out.append({
                "class": "compute_dos", "subclass": "large_alloc",
                "file": str(path), "line": ln, "size": size,
                "advice": f"Large allocation {size} bytes — compute budget impact.",
                "severity": "low", "classification": "novel_instance",
            })
    for m in HEAVY_OP_IN_LOOP_RE.finditer(text):
        ln = text[:m.start()].count("\n") + 1
        out.append({
            "class": "compute_dos", "subclass": "heavy_op_in_loop",
            "file": str(path), "line": ln,
            "advice": "Heavy operation (invoke/find_program_address/crypto) in loop — CU budget amplification.",
            "severity": "high", "classification": "novel_instance",
        })
    return out


def main():
    ap = argparse.ArgumentParser(description="Compute DoS analyzer")
    ap.add_argument("--target", required=True); ap.add_argument("--output", default=None); ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    target = Path(args.target)
    files = [target] if target.is_file() and target.suffix == ".rs" else list(target.rglob("*.rs")) if target.is_dir() else []
    if not files: print("[!] No .rs", file=sys.stderr); sys.exit(1)
    all_f = []
    for f in files:
        if "/target/" in str(f).replace("\\", "/"): continue
        all_f.extend(scan_file(f))
    if not args.quiet: print(f"[+] Compute DoS findings: {len(all_f)}")
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "compute_dos_findings.json").write_text(json.dumps(all_f, indent=2), encoding="utf-8")

if __name__ == "__main__": main()
