#!/usr/bin/env python3
"""
mutation_test_runner.py — mutate protocol's source code, run its tests.

Tests that PASS after mutation = weak test coverage = bug-rich zone.

Mutations applied:
- ==/!=  → swap
- +/-    → swap
- </>    → swap
- <=/>=  → swap to strict
- &&/||  → swap
- require → comment out
- comparisons with 0 / address(0) flip

Then `forge test` is run; if all tests still pass → mutation survived.
"""
import argparse
import json
import re
import subprocess
import shutil
import sys
import tempfile
from pathlib import Path


MUTATIONS = [
    ("eq_to_ne", re.compile(r"==\s"), "!= "),
    ("ne_to_eq", re.compile(r"!=\s"), "== "),
    ("plus_to_minus", re.compile(r"(?<!\+)\+\s(?!\+)"), "- "),
    ("minus_to_plus", re.compile(r"(?<!\-)\-\s(?!\-)"), "+ "),
    ("lt_to_gt", re.compile(r"<\s(?![=<])"), "> "),
    ("gt_to_lt", re.compile(r">\s(?![=>])"), "< "),
    ("lte_to_lt", re.compile(r"<=\s"), "< "),
    ("gte_to_gt", re.compile(r">=\s"), "> "),
    ("and_to_or", re.compile(r"&&"), "||"),
    ("require_comment", re.compile(r"^(\s*)require\s*\(", re.MULTILINE), r"\1// require("),
]


def run_forge_tests(repo: Path, timeout: int = 120) -> bool:
    try:
        r = subprocess.run(
            ["forge", "test", "--no-match-test", "invariant"],
            cwd=repo,
            timeout=timeout,
            capture_output=True,
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def apply_mutation(file: Path, regex, replacement) -> str | None:
    text = file.read_text(encoding="utf-8", errors="ignore")
    new = regex.sub(replacement, text, count=1)
    if new == text:
        return None
    file.write_text(new, encoding="utf-8")
    return text


def main():
    ap = argparse.ArgumentParser(description="Mutation testing for Solidity")
    ap.add_argument("--repo", required=True, help="Foundry-style repo")
    ap.add_argument("--src-dir", default="src", help="Source dir within repo")
    ap.add_argument("--max-mutations", type=int, default=20)
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    repo = Path(args.repo)
    src = repo / args.src_dir
    if not src.is_dir():
        print(f"[!] src dir not found: {src}", file=sys.stderr)
        sys.exit(1)

    if shutil.which("forge") is None:
        print("[!] forge not installed — install foundry first", file=sys.stderr)
        sys.exit(2)

    files = list(src.rglob("*.sol"))
    if not files:
        print("[!] no .sol files found", file=sys.stderr)
        sys.exit(1)

    if not args.quiet:
        print("[*] Running baseline tests...")
    if not run_forge_tests(repo):
        print("[!] Baseline tests fail — fix tests first", file=sys.stderr)
        sys.exit(3)

    survivors = []
    killed = []
    attempts = 0

    for f in files:
        if attempts >= args.max_mutations:
            break
        for mid, regex, replacement in MUTATIONS:
            if attempts >= args.max_mutations:
                break
            original = apply_mutation(f, regex, replacement)
            if original is None:
                continue
            attempts += 1
            still_passes = run_forge_tests(repo)
            f.write_text(original, encoding="utf-8")
            rec = {"file": str(f), "mutation": mid}
            if still_passes:
                survivors.append(rec)
                if not args.quiet:
                    print(f"  SURVIVED: [{mid}] {f.name}")
            else:
                killed.append(rec)
                if not args.quiet:
                    print(f"  killed:   [{mid}] {f.name}")

    if not args.quiet:
        print(f"\n[+] Attempts: {attempts}")
        print(f"[+] Killed:    {len(killed)}")
        print(f"[+] SURVIVED:  {len(survivors)}  ← test gaps")
        score = (len(killed) / attempts * 100) if attempts > 0 else 0
        print(f"[+] Mutation score: {score:.1f}%")

    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "mutation_report.json").write_text(json.dumps({
            "attempts": attempts,
            "killed": killed,
            "survivors": survivors,
            "score_pct": (len(killed) / attempts * 100) if attempts > 0 else 0,
        }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
