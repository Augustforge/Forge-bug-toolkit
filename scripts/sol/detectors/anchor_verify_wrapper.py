#!/usr/bin/env python3
"""
anchor_verify_wrapper.py — verify on-chain bytecode matches source.

Critical step BEFORE analysis: confirm what we analyse matches what's deployed.

Strategy:
1. Parse Anchor.toml → extract [programs.mainnet]
2. For each program_id → run `anchor verify <program_id>`
3. Output match/mismatch report

If mismatch: deployed bytecode != source we have. Continue analysis bytecode-only
via scripts/sol/bytecode/ tools.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def parse_anchor_toml(toml: Path) -> dict:
    """Extract programs.mainnet entries from Anchor.toml."""
    if not toml.exists():
        return {}
    text = toml.read_text(encoding="utf-8", errors="ignore")

    programs = {}
    in_mainnet = False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("[programs.mainnet]"):
            in_mainnet = True
            continue
        if line.startswith("[") and in_mainnet:
            in_mainnet = False
        if in_mainnet and "=" in line:
            name, addr = line.split("=", 1)
            programs[name.strip()] = addr.strip().strip('"').strip("'")
    return programs


def run_anchor_verify(program_id: str, project_dir: Path) -> dict:
    if shutil.which("anchor") is None:
        return {"error": "anchor CLI not installed"}
    try:
        r = subprocess.run(
            ["anchor", "verify", program_id],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=300,
        )
        return {
            "verified": r.returncode == 0,
            "stdout": r.stdout[:1000],
            "stderr": r.stderr[:1000] if r.stderr else None,
        }
    except subprocess.TimeoutExpired:
        return {"error": "timeout (300s)"}
    except Exception as e:
        return {"error": str(e)}


def main():
    ap = argparse.ArgumentParser(description="anchor verify wrapper")
    ap.add_argument("--target", required=True, help="Anchor project dir")
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    target = Path(args.target)
    anchor_tomls = list(target.rglob("Anchor.toml"))
    if not anchor_tomls:
        print(f"[!] No Anchor.toml found in {target}", file=sys.stderr)
        sys.exit(2)

    all_findings = []
    for toml in anchor_tomls:
        proj = toml.parent
        programs = parse_anchor_toml(toml)
        if not args.quiet:
            print(f"[*] {proj.name}: {len(programs)} mainnet programs")

        for name, prog_id in programs.items():
            result = run_anchor_verify(prog_id, proj)
            entry = {
                "class": "anchor_verify",
                "program_name": name,
                "program_id": prog_id,
                "project": str(proj),
                "result": result,
                "classification": "known_class",
            }
            if result.get("error"):
                entry["severity"] = "info"
                entry["advice"] = f"Could not verify: {result['error']}"
            elif result.get("verified"):
                entry["severity"] = "info"
                entry["advice"] = "Bytecode matches source. Source-level analysis valid."
            else:
                entry["severity"] = "high"
                entry["advice"] = "MISMATCH: deployed bytecode != source. Use scripts/sol/bytecode/ tools."
                entry["file"] = str(toml)
                entry["line"] = 0
            all_findings.append(entry)
            if not args.quiet:
                marker = "OK" if result.get("verified") else ("ERR" if result.get("error") else "MISMATCH")
                print(f"  [{marker:8}] {name:20} {prog_id}")

    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "anchor_verify.json").write_text(json.dumps(all_findings, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
