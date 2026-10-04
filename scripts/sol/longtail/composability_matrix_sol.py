#!/usr/bin/env python3
"""composability_matrix_sol.py — CPI graph + cross-program dependency."""
import argparse, json, re, sys
from collections import defaultdict
from pathlib import Path

CPI_RE = re.compile(r"invoke(?:_signed)?\s*\(\s*&Instruction\s*\{\s*program_id\s*:\s*([\w:.()\[\]_]+)")
PROGRAM_ID_REF_RE = re.compile(r"declare_id!\s*\(\s*\"([\w]+)\"")


def scan_file(path):
    try: text = path.read_text(encoding="utf-8", errors="ignore")
    except: return None
    cpis = []
    for m in CPI_RE.finditer(text):
        cpis.append({"target": m.group(1), "line": text[:m.start()].count("\n") + 1})
    program_ids = [m.group(1) for m in PROGRAM_ID_REF_RE.finditer(text)]
    return {"file": str(path), "cpis": cpis, "declares": program_ids}


def main():
    ap = argparse.ArgumentParser(description="Build CPI/composability dependency graph")
    ap.add_argument("--target", required=True)
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    target = Path(args.target)
    files = [target] if target.is_file() and target.suffix == ".rs" else list(target.rglob("*.rs")) if target.is_dir() else []
    if not files: print("[!] No .rs", file=sys.stderr); sys.exit(1)

    cpis_by_target = defaultdict(list)
    total_cpis = 0
    declarations = []
    for f in files:
        if "/target/" in str(f).replace("\\", "/"): continue
        result = scan_file(f)
        if not result: continue
        declarations.extend(result["declares"])
        for cpi in result["cpis"]:
            cpis_by_target[cpi["target"]].append({"file": result["file"], "line": cpi["line"]})
            total_cpis += 1

    findings = []
    for target_expr, locations in cpis_by_target.items():
        if len(locations) >= 3:
            findings.append({
                "class": "composability_concentration",
                "target_program": target_expr,
                "call_count": len(locations),
                "locations": locations[:10],
                "advice": f"{len(locations)} CPI calls into {target_expr} — compromise of {target_expr} breaks this protocol. Cross-protocol invariant check needed.",
                "severity": "medium",
                "classification": "novel_instance",
            })

    if not args.quiet:
        print(f"[+] Total CPI sites: {total_cpis}, unique targets: {len(cpis_by_target)}")
        print(f"[+] High-concentration targets: {len(findings)}")
        for f in findings[:5]:
            print(f"  {f['target_program']:40} {f['call_count']}x")

    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "composability_matrix.json").write_text(json.dumps({
            "total_cpis": total_cpis,
            "unique_targets": list(cpis_by_target.keys()),
            "declarations": declarations,
            "findings": findings,
        }, indent=2), encoding="utf-8")

if __name__ == "__main__": main()
