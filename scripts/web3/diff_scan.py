#!/usr/bin/env python3
"""
Smart contract diff scanner — scan only changed functions after upgrade.

When proxy gets upgraded (new implementation), instead of full scan we:
1. Fetch both old and new implementation source via Etherscan
2. Diff function-by-function
3. Run scan only on changed/new functions

Massive competitive edge — fresh code = highest probability of new bugs,
and we're scanning in minutes after upgrade event.

Usage:
    python3 diff_scan.py --target eth:0xPROXY \\
        --from-impl 0xOLD_IMPL --to-impl 0xNEW_IMPL --output ./out
"""

import argparse
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
FETCH_SOURCE = SCRIPT_DIR / "fetch_source.py"
SCAN_SH = SCRIPT_DIR / "scan.sh"


def fetch_impl(chain: str, addr: str, out_dir: Path):
    """Fetch one implementation source code."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = f"{chain}:{addr}"
    r = subprocess.run(
        [sys.executable, str(FETCH_SOURCE), "--target", target, "--output", str(out_dir)],
        capture_output=True, text=True, timeout=120,
    )
    return r.returncode == 0


def collect_solidity_files(root: Path) -> dict[str, str]:
    """Walk foundry-project/src/ and collect .sol files."""
    src = root / "foundry-project" / "src"
    if not src.exists():
        return {}
    files = {}
    for p in src.rglob("*.sol"):
        rel = p.relative_to(src)
        try:
            files[str(rel)] = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
    return files


def extract_functions(content: str) -> dict[str, str]:
    """
    Naive parser — extract function signatures and bodies.
    Good enough for diff detection without full AST parsing.
    """
    funcs = {}
    pattern = re.compile(
        r"function\s+(\w+)\s*\([^)]*\)[^{]*\{",
        re.MULTILINE,
    )
    for m in pattern.finditer(content):
        name = m.group(1)
        start = m.start()
        # Match braces to find function end
        depth = 0
        i = m.end() - 1
        while i < len(content):
            c = content[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    funcs[name] = content[start:i + 1]
                    break
            i += 1
    return funcs


def compute_diff(old_files: dict[str, str], new_files: dict[str, str]) -> dict:
    """Compute file-level + function-level diff."""
    diff = {
        "added_files": [],
        "removed_files": [],
        "modified_files": [],
        "unchanged_files": [],
        "added_functions": [],
        "modified_functions": [],
        "removed_functions": [],
    }

    for fname in new_files:
        if fname not in old_files:
            diff["added_files"].append(fname)
            for fn_name in extract_functions(new_files[fname]):
                diff["added_functions"].append({"file": fname, "function": fn_name})
        elif old_files[fname] == new_files[fname]:
            diff["unchanged_files"].append(fname)
        else:
            diff["modified_files"].append(fname)
            old_fns = extract_functions(old_files[fname])
            new_fns = extract_functions(new_files[fname])
            for name in new_fns:
                if name not in old_fns:
                    diff["added_functions"].append({"file": fname, "function": name})
                elif old_fns[name] != new_fns[name]:
                    diff["modified_functions"].append({"file": fname, "function": name})
            for name in old_fns:
                if name not in new_fns:
                    diff["removed_functions"].append({"file": fname, "function": name})

    for fname in old_files:
        if fname not in new_files:
            diff["removed_files"].append(fname)

    return diff


def write_diff_project(new_root: Path, diff: dict, out_dir: Path):
    """Write only changed files to a new foundry project for focused scan."""
    src = new_root / "foundry-project" / "src"
    target_src = out_dir / "diff-project" / "src"
    target_src.mkdir(parents=True, exist_ok=True)

    changed_files = set(diff["added_files"]) | set(diff["modified_files"])
    for fname in changed_files:
        src_file = src / fname
        if not src_file.exists():
            continue
        target = target_src / fname
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(src_file.read_text(encoding="utf-8", errors="ignore"))

    foundry_toml = new_root / "foundry-project" / "foundry.toml"
    if foundry_toml.exists():
        (out_dir / "diff-project" / "foundry.toml").write_text(
            foundry_toml.read_text(encoding="utf-8")
        )

    return out_dir / "diff-project"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, help="proxy address as <chain>:<addr>")
    ap.add_argument("--from-impl", required=True, help="old implementation address")
    ap.add_argument("--to-impl", required=True, help="new implementation address")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    if ":" not in args.target:
        sys.exit("Target format: <chain>:<address>")
    chain, _ = args.target.split(":", 1)

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    old_dir = out / "impl_old"
    new_dir = out / "impl_new"

    print(f"[*] Fetching old implementation: {args.from_impl}")
    if not fetch_impl(chain, args.from_impl, old_dir):
        print("[!] Failed to fetch old implementation")
        sys.exit(1)

    print(f"[*] Fetching new implementation: {args.to_impl}")
    if not fetch_impl(chain, args.to_impl, new_dir):
        print("[!] Failed to fetch new implementation")
        sys.exit(1)

    print("[*] Computing diff...")
    old_files = collect_solidity_files(old_dir)
    new_files = collect_solidity_files(new_dir)
    diff = compute_diff(old_files, new_files)

    diff_summary = {
        "old_impl": args.from_impl,
        "new_impl": args.to_impl,
        "files_added": len(diff["added_files"]),
        "files_modified": len(diff["modified_files"]),
        "files_removed": len(diff["removed_files"]),
        "files_unchanged": len(diff["unchanged_files"]),
        "functions_added": len(diff["added_functions"]),
        "functions_modified": len(diff["modified_functions"]),
        "functions_removed": len(diff["removed_functions"]),
        "diff": diff,
    }
    (out / "diff_summary.json").write_text(json.dumps(diff_summary, indent=2))

    print(f"[+] Files: +{diff_summary['files_added']} ~{diff_summary['files_modified']} "
          f"-{diff_summary['files_removed']}")
    print(f"[+] Functions: +{diff_summary['functions_added']} "
          f"~{diff_summary['functions_modified']} "
          f"-{diff_summary['functions_removed']}")

    if not (diff["added_files"] or diff["modified_files"]):
        print("[i] No changes detected — nothing to scan")
        return

    diff_project = write_diff_project(new_dir, diff, out)
    print(f"[*] Scanning diff project at {diff_project}...")
    r = subprocess.run(
        ["bash", str(SCAN_SH), "--repo", str(diff_project),
         "--output", str(out / "scan_results"), "--mode", "deep"],
        timeout=3600,
    )
    print(f"[+] Diff scan complete (exit: {r.returncode})")
    print(f"[+] Output: {out / 'scan_results' / 'web3_summary.json'}")


if __name__ == "__main__":
    main()
