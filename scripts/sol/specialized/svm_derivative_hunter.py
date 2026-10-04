#!/usr/bin/env python3
"""svm_derivative_hunter.py — Eclipse/Sonic/MagicBlock/SOON SVM-derivative hunter."""
import argparse, json, re, sys
from pathlib import Path

CHECKS = [
    ("ephemeral_state", re.compile(r"ephemeral|delegate.*state|rollup_state"), "Ephemeral state — verify commit-back logic, state freshness on base layer"),
    ("bridge_trust", re.compile(r"bridge|cross_chain.*message"), "Cross-chain bridge — verify sequencer/relayer trust assumptions"),
    ("sequencer_assumption", re.compile(r"sequencer|leader_schedule"), "Sequencer assumption — single point of failure? Censorship resistance?"),
    ("fault_proof", re.compile(r"fault_proof|challenge_period"), "Fault proof — challenge window, who can challenge, slashing?"),
    ("data_availability", re.compile(r"data_availability|DA_layer"), "Data availability — validium vs rollup, what if DA fails?"),
    ("force_exit", re.compile(r"force_exit|emergency_exit"), "Force exit mechanism — verify always works (centralization bypass)"),
]

def scan_file(path):
    try: text = path.read_text(encoding="utf-8", errors="ignore")
    except: return []
    out = []; lines = text.splitlines()
    for cid, r, advice in CHECKS:
        for m in r.finditer(text):
            ln = text[:m.start()].count("\n") + 1
            snip = lines[ln-1].strip()[:140] if ln <= len(lines) else ""
            out.append({"class": "svm_derivative", "subclass": cid, "file": str(path), "line": ln, "snippet": snip, "advice": advice, "severity": "high", "classification": "novel_instance", "experimental": True})
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
    if not args.quiet: print(f"[+] SVM derivative findings (experimental): {len(all_f)}")
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "svm_derivative_findings.json").write_text(json.dumps(all_f, indent=2), encoding="utf-8")

if __name__ == "__main__": main()
