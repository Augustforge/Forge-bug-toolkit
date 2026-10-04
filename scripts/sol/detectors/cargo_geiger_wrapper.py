#!/usr/bin/env python3
"""
cargo_geiger_wrapper.py — Wrapper for cargo-geiger (unsafe code density).

Solana program with high unsafe density = surface for memory safety bugs.
Threshold: >5% unsafe lines per crate = warning, >15% = high attention.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def run_geiger(target: Path) -> dict:
    if shutil.which("cargo") is None:
        return {"error": "cargo not installed"}
    if shutil.which("cargo-geiger") is None:
        return {"error": "cargo-geiger not installed (run: cargo install cargo-geiger)"}
    try:
        r = subprocess.run(
            ["cargo", "geiger", "--output-format", "Json"],
            cwd=target,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if r.stdout:
            try:
                return json.loads(r.stdout)
            except json.JSONDecodeError:
                return {"error": "json decode failed", "raw_stdout": r.stdout[:500]}
        return {"error": "no output"}
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}


def parse_geiger(data: dict) -> list[dict]:
    findings = []
    packages = data.get("packages", [])
    for pkg in packages:
        info = pkg.get("package", {}).get("id", {})
        counts = pkg.get("unsafety", {}).get("used", {})
        total_funcs = sum(counts.get(k, {}).get("safe", 0) + counts.get(k, {}).get("unsafe_", 0)
                          for k in ("functions", "exprs", "item_impls", "item_traits", "methods"))
        unsafe_count = sum(counts.get(k, {}).get("unsafe_", 0)
                           for k in ("functions", "exprs", "item_impls", "item_traits", "methods"))
        if total_funcs == 0:
            continue
        density = unsafe_count / total_funcs

        severity = "low"
        if density > 0.15:
            severity = "high"
        elif density > 0.05:
            severity = "medium"

        if density > 0:
            findings.append({
                "class": "unsafe_code_density",
                "severity": severity,
                "file": info.get("name", "?"),
                "line": 0,
                "package": info.get("name"),
                "version": info.get("version"),
                "unsafe_count": unsafe_count,
                "total": total_funcs,
                "density_pct": round(density * 100, 2),
                "advice": f"Package has {round(density*100,2)}% unsafe code. Review unsafe blocks for memory safety.",
                "classification": "known_class",
            })
    return findings


def main():
    ap = argparse.ArgumentParser(description="cargo-geiger wrapper (unsafe code density)")
    ap.add_argument("--target", required=True)
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    target = Path(args.target)
    if not target.is_dir():
        print(f"[!] Target not a dir: {target}", file=sys.stderr)
        sys.exit(1)

    data = run_geiger(target)
    if data.get("error"):
        print(f"[!] {data['error']}", file=sys.stderr)
        sys.exit(2)

    findings = parse_geiger(data)

    if not args.quiet:
        print(f"[+] Packages with unsafe code: {len(findings)}")
        for f in findings[:10]:
            print(f"  [{f['severity']:8}] {f['package']:30} {f['density_pct']:6.2f}% ({f['unsafe_count']}/{f['total']})")

    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "cargo_geiger.json").write_text(json.dumps(findings, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
