#!/usr/bin/env python3
"""
sec3_xray_wrapper.py — Wrapper for Sec3 X-Ray scanner.

Sec3 X-Ray detects 50+ Solana vulnerability types. Free tier available via
github.com/sec3-product/x-ray. Wrapper runs binary, parses JSON, normalizes.

Fallback: if x-ray is not installed — show installation hint, don't crash.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def run_xray(target: Path) -> dict:
    candidates = ["x-ray", "sec3-x-ray", "sec3"]
    binary = None
    for c in candidates:
        if shutil.which(c):
            binary = c
            break
    if not binary:
        return {
            "error": "x-ray not installed",
            "hint": "Install Sec3 X-Ray from https://github.com/sec3-product/x-ray",
            "fallback": "Run custom_regex_checks.py + cargo_audit_wrapper.py for baseline coverage",
        }

    try:
        r = subprocess.run(
            [binary, "scan", "--format", "json", str(target)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if r.stdout:
            try:
                return json.loads(r.stdout)
            except json.JSONDecodeError:
                return {"raw_output": r.stdout[:2000], "stderr": r.stderr[:500]}
        return {"error": "no output", "stderr": r.stderr[:500]}
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}


def normalize(data: dict) -> list[dict]:
    if "error" in data:
        return []
    findings = []
    items = data.get("findings", []) or data.get("issues", []) or data.get("vulnerabilities", [])
    for item in items:
        sev_raw = (item.get("severity") or "low").lower()
        sev = {"critical": "critical", "high": "high", "medium": "medium", "low": "low",
               "info": "info", "warning": "medium", "error": "high"}.get(sev_raw, "low")
        findings.append({
            "class": item.get("rule", item.get("type", "sec3_xray")),
            "severity": sev,
            "file": item.get("file", item.get("path", "?")),
            "line": item.get("line", 0),
            "snippet": item.get("code", "")[:200],
            "advice": item.get("description", item.get("message", "")),
            "tool": "sec3_xray",
            "classification": "known_class",
        })
    return findings


def main():
    ap = argparse.ArgumentParser(description="Sec3 X-Ray wrapper")
    ap.add_argument("--target", required=True)
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"[!] Target not found: {target}", file=sys.stderr)
        sys.exit(1)

    data = run_xray(target)
    if data.get("error"):
        if not args.quiet:
            print(f"[!] {data['error']}")
            if data.get("hint"):
                print(f"    Hint: {data['hint']}")
            if data.get("fallback"):
                print(f"    Fallback: {data['fallback']}")
        if args.output:
            out = Path(args.output)
            out.mkdir(parents=True, exist_ok=True)
            (out / "sec3_xray.json").write_text(json.dumps([], indent=2), encoding="utf-8")
        sys.exit(0)

    findings = normalize(data)

    if not args.quiet:
        print(f"[+] Sec3 X-Ray findings: {len(findings)}")
        by_sev = {}
        for f in findings:
            by_sev[f["severity"]] = by_sev.get(f["severity"], 0) + 1
        for s, n in sorted(by_sev.items()):
            print(f"  {s}: {n}")

    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "sec3_xray.json").write_text(json.dumps(findings, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
