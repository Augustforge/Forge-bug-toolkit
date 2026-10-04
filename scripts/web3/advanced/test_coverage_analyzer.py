#!/usr/bin/env python3
"""
test_coverage_analyzer.py — find Solidity functions NOT exercised by tests.

Heuristic: scan src/ for function names, scan test/ for invocations.
Uncovered = no test mentions the function name.
"""
import argparse
import json
import re
import sys
from pathlib import Path


FUNC_DEF = re.compile(r"function\s+(\w+)\s*\(", re.MULTILINE)
SKIP_NAMES = {"constructor", "fallback", "receive"}


def collect_functions(src_dir: Path) -> dict:
    funcs = {}
    for sol in src_dir.rglob("*.sol"):
        spath = str(sol).replace("\\", "/").lower()
        if "/test" in spath or "/mock" in spath:
            continue
        try:
            text = sol.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for m in FUNC_DEF.finditer(text):
            name = m.group(1)
            if name in SKIP_NAMES or name.startswith("_"):
                continue
            line = text[: m.start()].count("\n") + 1
            funcs.setdefault(name, []).append({"file": str(sol), "line": line})
    return funcs


def collect_test_calls(test_dirs: list[Path]) -> set:
    called = set()
    for td in test_dirs:
        for sol in td.rglob("*.sol"):
            try:
                text = sol.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for m in re.finditer(r"\.(\w+)\s*\(", text):
                called.add(m.group(1))
            for m in re.finditer(r"\b(test\w+|invariant_\w+)\s*\(", text):
                called.add(m.group(1))
    return called


def main():
    ap = argparse.ArgumentParser(description="Find Solidity functions not covered by tests")
    ap.add_argument("--src", required=True, help="Source dir (e.g. src/)")
    ap.add_argument("--test", action="append", required=True, help="Test dir(s), may repeat")
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    src = Path(args.src)
    test_dirs = [Path(t) for t in args.test]
    if not src.is_dir():
        print(f"[!] src not found: {src}", file=sys.stderr)
        sys.exit(1)

    funcs = collect_functions(src)
    called = collect_test_calls(test_dirs)

    uncovered = {n: locs for n, locs in funcs.items() if n not in called}
    covered = {n: locs for n, locs in funcs.items() if n in called}

    if not args.quiet:
        print(f"[+] Total public functions: {len(funcs)}")
        print(f"[+] Covered: {len(covered)}")
        print(f"[!] Uncovered: {len(uncovered)}\n")
        print("Top uncovered (high-value targets for hypothesis):")
        for name, locs in list(uncovered.items())[:30]:
            for loc in locs[:1]:
                print(f"  {name:30}  {Path(loc['file']).name}:{loc['line']}")

    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "coverage_report.json").write_text(json.dumps({
            "total": len(funcs),
            "covered": len(covered),
            "uncovered": len(uncovered),
            "uncovered_functions": uncovered,
        }, indent=2), encoding="utf-8")
        md = f"# Coverage Report\n\nTotal: {len(funcs)} | Covered: {len(covered)} | Uncovered: {len(uncovered)}\n\n## Uncovered functions\n\n"
        for n, locs in uncovered.items():
            md += f"- **{n}**\n"
            for loc in locs:
                md += f"  - {loc['file']}:{loc['line']}\n"
        (out / "coverage_report.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
