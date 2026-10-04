#!/usr/bin/env python3
"""
complexity_risk_scorer.py — risk-prioritize Solidity functions.

McCabe cyclomatic complexity + LoC + nesting depth + external-call density.
High score = likely bug-rich.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path


DECISION_KEYWORDS = re.compile(r"\b(if|else if|for|while|require|assert|\?\s*[^:]+:)\b")
EXTERNAL_CALL = re.compile(r"\.(call|delegatecall|staticcall|transfer|send)\s*[\({]|\bIERC20\b|\.transferFrom\(|external\s+\w+")
FUNCTION_DEF = re.compile(
    r"^\s*function\s+(\w+)\s*\(([^)]*)\)\s*([^{;]*)\{",
    re.MULTILINE,
)


def find_function_body(text: str, start: int) -> tuple[str, int]:
    depth = 0
    i = start
    in_str = False
    str_ch = ""
    while i < len(text):
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == str_ch:
                in_str = False
        else:
            if c in ('"', "'"):
                in_str = True
                str_ch = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1], i + 1
        i += 1
    return text[start:], len(text)


def analyze_function(name: str, body: str, signature: str) -> dict:
    lines = [ln for ln in body.splitlines() if ln.strip() and not ln.strip().startswith("//")]
    loc = len(lines)
    decisions = len(DECISION_KEYWORDS.findall(body))
    external_calls = len(EXTERNAL_CALL.findall(body))

    max_nest = 0
    cur = 0
    for c in body:
        if c == "{":
            cur += 1
            max_nest = max(max_nest, cur)
        elif c == "}":
            cur -= 1

    mccabe = 1 + decisions
    risk = (mccabe * 2) + (loc // 20) + (max_nest * 3) + (external_calls * 4)
    if "payable" in signature.lower():
        risk += 5
    if "onlyOwner" not in signature and "onlyAdmin" not in signature and external_calls > 0:
        risk += 3

    severity = "low"
    if risk >= 40:
        severity = "critical"
    elif risk >= 25:
        severity = "high"
    elif risk >= 12:
        severity = "medium"

    return {
        "name": name,
        "loc": loc,
        "mccabe": mccabe,
        "nesting": max_nest,
        "external_calls": external_calls,
        "payable": "payable" in signature.lower(),
        "risk_score": risk,
        "severity": severity,
    }


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    results = []
    for m in FUNCTION_DEF.finditer(text):
        name = m.group(1)
        sig = m.group(0)
        body, _ = find_function_body(text, m.end() - 1)
        rec = analyze_function(name, body, sig)
        rec["file"] = str(path)
        rec["line"] = text[: m.start()].count("\n") + 1
        results.append(rec)
    return results


def main():
    ap = argparse.ArgumentParser(description="Risk-score Solidity functions by complexity heuristics")
    ap.add_argument("--target", required=True, help="File or directory")
    ap.add_argument("--output", default=None, help="Output directory")
    ap.add_argument("--top", type=int, default=20, help="Top N functions to print")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    target = Path(args.target)
    files = []
    if target.is_file() and target.suffix == ".sol":
        files = [target]
    elif target.is_dir():
        files = [p for p in target.rglob("*.sol") if "/test" not in str(p).replace("\\", "/").lower()]
    else:
        print(f"[!] Target not found: {target}", file=sys.stderr)
        sys.exit(1)

    all_results = []
    for f in files:
        all_results.extend(scan_file(f))

    all_results.sort(key=lambda r: r["risk_score"], reverse=True)

    if not args.quiet:
        print(f"[+] Scanned {len(files)} files, {len(all_results)} functions.")
        print(f"\nTop {args.top} risk functions:")
        for r in all_results[: args.top]:
            print(f"  [{r['severity']:8}] score={r['risk_score']:3} {r['name']:30} mc={r['mccabe']} loc={r['loc']} ext={r['external_calls']} ({Path(r['file']).name}:{r['line']})")

    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "complexity_report.json").write_text(json.dumps(all_results, indent=2), encoding="utf-8")
        md = "# Complexity Risk Report\n\n"
        md += f"Functions analyzed: {len(all_results)}\n\n"
        md += "| Severity | Score | Function | File:Line | McCabe | LoC | Ext.Calls |\n"
        md += "|---|---|---|---|---|---|---|\n"
        for r in all_results[: args.top]:
            md += f"| {r['severity']} | {r['risk_score']} | {r['name']} | {Path(r['file']).name}:{r['line']} | {r['mccabe']} | {r['loc']} | {r['external_calls']} |\n"
        (out / "complexity_report.md").write_text(md, encoding="utf-8")
        if not args.quiet:
            print(f"[+] Reports: {out}")


if __name__ == "__main__":
    main()
