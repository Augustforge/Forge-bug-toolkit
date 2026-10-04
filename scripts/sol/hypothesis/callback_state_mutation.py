#!/usr/bin/env python3
"""
callback_state_mutation.py — Token-2022 hooks + external callback surfaces.

CLASS: an external program gets control flow during a protocol op via CPI,
and can mutate state before returning.
"""
import argparse, json, re, sys
from pathlib import Path

CALLBACK_PATTERNS = [
    ("transfer_hook", re.compile(r"transfer_checked\s*\(")),
    ("oracle_callback", re.compile(r"oracle.*callback|aggregator.*update")),
    ("custom_cpi_with_callback", re.compile(r"invoke(?:_signed)?\s*\([^)]*callback")),
]
STATE_LOCK_RE = re.compile(r"is_locked|reentrancy_guard|mutex|lock\s*=\s*true")


def scan_file(path):
    try: text = path.read_text(encoding="utf-8", errors="ignore")
    except: return []
    out = []
    lines = text.splitlines()
    for name, regex in CALLBACK_PATTERNS:
        for m in regex.finditer(text):
            ln = text[:m.start()].count("\n") + 1
            ctx = text[max(0, m.start()-500): m.end()+500]
            has_lock = bool(STATE_LOCK_RE.search(ctx))
            mutation_after = bool(re.search(r"\.\s*\w+\s*=\s*\w+|\.set_|\.add_|\.sub_", text[m.end(): min(len(text), m.end()+500)]))
            if not has_lock and mutation_after:
                snip = lines[ln-1].strip()[:140] if ln <= len(lines) else ""
                out.append({
                    "class": "callback_state_mutation", "subclass": name,
                    "file": str(path), "line": ln, "snippet": snip,
                    "advice": f"{name} CPI followed by state mutation without reentrancy guard. "
                              f"External callback may mutate state during transfer/callback.",
                    "severity": "high", "classification": "novel_instance",
                })
    return out


def main():
    ap = argparse.ArgumentParser(description="Detect callback state mutation")
    ap.add_argument("--target", required=True); ap.add_argument("--output", default=None); ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    target = Path(args.target)
    files = [target] if target.is_file() and target.suffix == ".rs" else list(target.rglob("*.rs")) if target.is_dir() else []
    if not files: print("[!] No .rs", file=sys.stderr); sys.exit(1)
    all_f = []
    for f in files:
        if "/target/" in str(f).replace("\\", "/"): continue
        all_f.extend(scan_file(f))
    if not args.quiet: print(f"[+] Callback state mutation: {len(all_f)}")
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "callback_state_findings.json").write_text(json.dumps(all_f, indent=2), encoding="utf-8")

if __name__ == "__main__": main()
