#!/usr/bin/env python3
"""
red_team_simulator.py — self-calibration after public exploit disclosure.

Question: "Would we find this BEFORE the public fix?"

Workflow:
1. Download pre-fix code (commit before fix merged)
2. Run our toolkit on it (hypothesis + specialized + detectors)
3. Check: does relevant script flag the bug?
4. If yes → confirm hypothesis quality
5. If no → analyse what we missed, update failure_modes.md
"""
import argparse, json, shutil, subprocess, sys, tempfile
from pathlib import Path


def clone_at_commit(repo_url: str, commit: str, dest: Path) -> bool:
    try:
        subprocess.run(["git", "clone", repo_url, str(dest)], check=True, capture_output=True, timeout=180)
        subprocess.run(["git", "-C", str(dest), "checkout", commit], check=True, capture_output=True, timeout=60)
        return True
    except Exception as e:
        print(f"[!] Clone/checkout failed: {e}", file=sys.stderr)
        return False


def run_toolkit_solana(target_dir: Path, output: Path) -> dict:
    """Run all Solana hypothesis + specialized scripts."""
    sol_dir = Path(__file__).parent.parent / "sol"
    findings = []
    for category in ["hypothesis", "specialized", "longtail", "detectors"]:
        cat_dir = sol_dir / category
        if not cat_dir.is_dir(): continue
        for script in cat_dir.glob("*.py"):
            try:
                r = subprocess.run(
                    ["python3", str(script), "--target", str(target_dir), "--output", str(output / category / script.stem), "--quiet"],
                    capture_output=True, timeout=120,
                )
            except Exception:
                continue
    for jf in output.rglob("*.json"):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
            items = data if isinstance(data, list) else data.get("findings", [])
            for item in items:
                if isinstance(item, dict):
                    findings.append(item)
        except Exception:
            continue
    return {"total": len(findings), "findings": findings}


def check_match(findings: list, expected_keywords: list[str]) -> dict:
    """Did any finding match the expected exploit class?"""
    for f in findings:
        text = json.dumps(f).lower()
        for kw in expected_keywords:
            if kw.lower() in text:
                return {"matched": True, "matching_finding": f, "keyword": kw}
    return {"matched": False, "matching_finding": None}


def main():
    ap = argparse.ArgumentParser(description="Red-team self-calibration after exploit disclosure")
    ap.add_argument("--exploit-name", required=True)
    ap.add_argument("--repo-url", required=True)
    ap.add_argument("--pre-fix-commit", required=True)
    ap.add_argument("--expected-class", required=True, help="Expected bug class keyword (e.g. 'cpi_program_id')")
    ap.add_argument("--chain", choices=["evm", "solana"], default="solana")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        repo_dir = Path(tmp) / "repo"
        print(f"[*] Cloning {args.repo_url} @ {args.pre_fix_commit}...")
        if not clone_at_commit(args.repo_url, args.pre_fix_commit, repo_dir):
            sys.exit(1)

        print(f"[*] Running toolkit on pre-fix code...")
        if args.chain == "solana":
            toolkit_out = out / "toolkit_output"
            toolkit_out.mkdir(exist_ok=True)
            result = run_toolkit_solana(repo_dir, toolkit_out)
        else:
            print("[!] EVM run not implemented in this draft", file=sys.stderr)
            sys.exit(2)

        match = check_match(result["findings"], [args.expected_class])

        verdict = {
            "exploit": args.exploit_name,
            "expected_class": args.expected_class,
            "total_findings": result["total"],
            "matched": match["matched"],
            "matching_finding": match.get("matching_finding"),
            "verdict": "WOULD_HAVE_FOUND" if match["matched"] else "WOULD_HAVE_MISSED",
        }

        print(f"\n[+] Exploit: {args.exploit_name}")
        print(f"[+] Total toolkit findings: {result['total']}")
        print(f"[+] Verdict: {verdict['verdict']}")
        if not match["matched"]:
            print(f"\n[!] We would have MISSED this. Update failure_modes.md")
            print(f"    Expected class: {args.expected_class}")

        (out / "verdict.json").write_text(json.dumps(verdict, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
