#!/usr/bin/env python3
"""
audit_rebuttal_analyzer_sol.py — re-examine "approved by auditor" code.

If protocol passed 3+ audits (Sec3/OtterSec/Halborn/Neodyme/Trail of Bits),
those audits had blind spots. This script flags code areas that match
auditor-typical blind spots.
"""
import argparse, json, re, sys
from pathlib import Path

AUDITOR_BLIND_SPOTS = {
    "sec3_misses": [
        ("business_logic_loop", re.compile(r"fn\s+\w+\s*\([^)]*\)\s*->\s*Result[^{]*\{[\s\S]{500,}}", re.MULTILINE), "Long business logic functions — Sec3 thorough on primitives, light on custom logic"),
        ("novel_pattern_not_in_50", re.compile(r"#\[derive\([^)]*Custom[^)]*\)\]"), "Custom derive — not in Sec3's 50 known vuln types"),
    ],
    "ottersec_misses": [
        ("cross_program_state", re.compile(r"invoke(?:_signed)?\s*\([^)]+\)[\s\S]{0,300}invoke", re.DOTALL), "Multiple CPIs in single instruction — OtterSec strong on Anchor footguns, weaker on cross-program state drift"),
    ],
    "neodyme_misses": [
        ("deployment_idl", re.compile(r"#\[program\]"), "Anchor program declaration — check IDL authority claimed at deploy (Neodyme time-pressured on large codebases, misses deployment hygiene)"),
    ],
    "halborn_misses": [
        ("share_math", re.compile(r"shares?\s*\*\s*\w+\s*/|total_supply\s*\*"), "Share-based math — Halborn strong on surface, weaker on deep precision"),
    ],
}


def scan_file(path):
    try: text = path.read_text(encoding="utf-8", errors="ignore")
    except: return []
    out = []
    lines = text.splitlines()
    for auditor, checks in AUDITOR_BLIND_SPOTS.items():
        for cid, regex, advice in checks:
            for m in regex.finditer(text):
                ln = text[:m.start()].count("\n") + 1
                snip = lines[ln-1].strip()[:140] if ln <= len(lines) else ""
                out.append({
                    "class": "audit_rebuttal", "subclass": cid,
                    "auditor_blind_spot": auditor,
                    "file": str(path), "line": ln, "snippet": snip,
                    "advice": advice, "severity": "medium", "classification": "novel_instance",
                })
    return out


def main():
    ap = argparse.ArgumentParser(description="Re-examine audited code through blind-spot lens")
    ap.add_argument("--target", required=True)
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    target = Path(args.target)
    files = [target] if target.is_file() and target.suffix == ".rs" else list(target.rglob("*.rs")) if target.is_dir() else []
    if not files: print("[!] No .rs", file=sys.stderr); sys.exit(1)
    all_f = []
    for f in files:
        if "/target/" in str(f).replace("\\", "/"): continue
        all_f.extend(scan_file(f))
    if not args.quiet:
        print(f"[+] Audit rebuttal candidates: {len(all_f)}")
        by_auditor = {}
        for f in all_f:
            by_auditor[f["auditor_blind_spot"]] = by_auditor.get(f["auditor_blind_spot"], 0) + 1
        for k, v in by_auditor.items(): print(f"  {k:25} {v}")
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "audit_rebuttal_findings.json").write_text(json.dumps(all_f, indent=2), encoding="utf-8")

if __name__ == "__main__": main()
