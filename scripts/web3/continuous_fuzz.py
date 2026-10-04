#!/usr/bin/env python3
"""
Continuous fuzzing infrastructure for high-value targets.

Runs Echidna or Foundry invariants for hours/days, saves corpus,
alerts via notify.py when counterexample found.

Recommended for targets:
- TVL > $10M
- Marked as "golden case" by TVL monitor
- Multiple high-severity findings from /hunt

Usage:
    python3 continuous_fuzz.py --project sessions/X/foundry-project \\
        --hours 24 --rpc <fork-url>
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
NOTIFY = SCRIPT_DIR / "monitors" / "notify.py"


def has_echidna_tests(project: Path) -> bool:
    return any(project.rglob("*echidna_*.sol")) or any(
        "function echidna_" in (p.read_text(encoding="utf-8", errors="ignore"))
        for p in project.rglob("*.sol") if p.is_file()
    )


def has_foundry_invariants(project: Path) -> bool:
    return any(
        "function invariant_" in (p.read_text(encoding="utf-8", errors="ignore"))
        for p in project.rglob("*.t.sol") if p.is_file()
    )


def run_echidna(project: Path, output: Path, hours: int) -> int:
    cmd = ["echidna", str(project), "--corpus-dir", str(output / "corpus"),
           "--format", "json", "--test-mode", "assertion",
           "--seq-len", "100"]
    seconds = hours * 3600
    print(f"[*] Echidna for {hours}h with corpus at {output}/corpus")
    log = (output / "echidna.log").open("w")
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
    start = time.time()
    while time.time() - start < seconds:
        if proc.poll() is not None:
            return proc.returncode
        time.sleep(60)
        if (output / "corpus").exists():
            counterexamples = list((output / "corpus").rglob("*.txt"))
            if counterexamples:
                alert(f"Echidna found {len(counterexamples)} counterexamples in {project.name}")
                break
    proc.terminate()
    return proc.returncode


def run_foundry(project: Path, output: Path, hours: int, rpc: str | None) -> int:
    seconds = hours * 3600
    runs = max(seconds * 100, 100_000)
    cmd = ["forge", "test", "--match-test", "invariant_",
           "--fuzz-runs", str(runs)]
    if rpc:
        cmd.extend(["--fork-url", rpc])
    print(f"[*] Foundry invariants for ~{hours}h ({runs} runs cap)")
    log = (output / "foundry_fuzz.log").open("w")
    r = subprocess.run(cmd, cwd=project, stdout=log, stderr=subprocess.STDOUT,
                       timeout=seconds)
    if r.returncode != 0:
        alert(f"Foundry invariants FAILED in {project.name} — counterexample found!")
    return r.returncode


def alert(message: str):
    """Push to Telegram via notify.py."""
    if NOTIFY.exists():
        try:
            subprocess.run(
                [sys.executable, str(NOTIFY), "--message", f"🚨 FUZZ ALERT: {message}"],
                timeout=20,
            )
        except Exception:
            pass
    print(f"[!] {message}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True, help="Foundry project root")
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--rpc", help="Mainnet fork RPC URL (optional)")
    ap.add_argument("--output", help="Output dir (default: <project>/fuzz_results)")
    args = ap.parse_args()

    project = Path(args.project)
    if not project.exists():
        sys.exit(f"Project not found: {project}")

    output = Path(args.output) if args.output else project / "fuzz_results"
    output.mkdir(parents=True, exist_ok=True)

    if has_echidna_tests(project):
        print("[*] Echidna tests detected")
        rc = run_echidna(project, output, args.hours)
    elif has_foundry_invariants(project):
        print("[*] Foundry invariants detected")
        rc = run_foundry(project, output, args.hours, args.rpc)
    else:
        print("[!] No echidna_* nor invariant_* tests found in project")
        print("[i] Add property tests to enable continuous fuzzing")
        sys.exit(1)

    summary = {
        "project": str(project),
        "started": time.time() - args.hours * 3600,
        "ended": time.time(),
        "duration_hours": args.hours,
        "exit_code": rc,
        "alerts_sent": rc != 0,
    }
    (output / "fuzz_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"[+] Fuzz summary: {output}/fuzz_summary.json")


if __name__ == "__main__":
    main()
