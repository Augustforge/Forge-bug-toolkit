#!/usr/bin/env python3
"""
cargo_audit_wrapper.py — Wrapper for cargo-audit (Rust deps CVE scanner).

Runs `cargo audit --json` in target dir. Parses output, maps severity to
Immunefi-style. Highlights deps used by Solana programs specifically (anchor-lang,
solana-program, spl-token, etc.).
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


CRITICAL_DEPS = {"anchor-lang", "anchor-spl", "solana-program", "spl-token", "spl-associated-token-account"}


def run_cargo_audit(target: Path) -> dict | None:
    if shutil.which("cargo") is None:
        return {"error": "cargo not installed"}
    try:
        r = subprocess.run(
            ["cargo", "audit", "--json"],
            cwd=target,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if r.stdout:
            return json.loads(r.stdout)
        return {"error": "no output", "stderr": r.stderr[:500]}
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    except json.JSONDecodeError:
        return {"error": "json decode failed", "raw": r.stdout[:500] if r.stdout else None}
    except FileNotFoundError:
        return {"error": "cargo-audit not installed (run: cargo install cargo-audit)"}


def classify_severity(advisory: dict) -> str:
    sev = advisory.get("severity", "").lower()
    pkg = advisory.get("package", {}).get("name", "")
    is_critical_dep = pkg in CRITICAL_DEPS

    if sev in ("critical", "high"):
        return "critical" if is_critical_dep else "high"
    if sev == "medium":
        return "high" if is_critical_dep else "medium"
    return "medium" if is_critical_dep else "low"


def main():
    ap = argparse.ArgumentParser(description="cargo-audit wrapper for Solana programs")
    ap.add_argument("--target", required=True, help="Cargo project root dir")
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    target = Path(args.target)
    if not target.is_dir():
        print(f"[!] Target dir not found: {target}", file=sys.stderr)
        sys.exit(1)

    cargo_tomls = list(target.rglob("Cargo.toml"))
    if not cargo_tomls:
        print(f"[!] No Cargo.toml found", file=sys.stderr)
        sys.exit(2)

    findings = []
    project_dirs = set(p.parent for p in cargo_tomls if p.parent.name != "target")

    for proj in project_dirs:
        result = run_cargo_audit(proj)
        if not result or result.get("error"):
            if not args.quiet:
                print(f"  [{proj.name}] error: {result.get('error') if result else 'none'}")
            continue

        vulns = result.get("vulnerabilities", {}).get("list", [])
        for v in vulns:
            adv = v.get("advisory", {})
            pkg = v.get("package", {})
            findings.append({
                "class": "rust_dep_cve",
                "severity": classify_severity({**adv, "package": pkg}),
                "file": f"{proj}/Cargo.lock",
                "line": 0,
                "package": pkg.get("name"),
                "version": pkg.get("version"),
                "advisory_id": adv.get("id"),
                "title": adv.get("title"),
                "url": adv.get("url"),
                "advice": f"Update {pkg.get('name')} (advisory: {adv.get('id')})",
                "classification": "known_class",
            })

    if not args.quiet:
        print(f"[+] Projects: {len(project_dirs)}, vulnerabilities: {len(findings)}")
        for f in findings[:10]:
            print(f"  [{f['severity']:8}] {f['package']:30} {f['advisory_id']}")

    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "cargo_audit.json").write_text(json.dumps(findings, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
