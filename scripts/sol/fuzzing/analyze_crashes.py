#!/usr/bin/env python3
"""
analyze_crashes.py — parse Trident v0.12+ crash corpus, classify by invariant violated, severity-rank.

Usage:
    python3 analyze_crashes.py <test_fuzz_dir> [--output report.md]

Trident outputs:
- `hfuzz_workspace/<test_name>/` contains honggfuzz raw output + crash inputs
- Crash files: *.fuzz binary inputs that triggered assertion or panic
- Stderr / log files: contain assertion messages (which invariant violated)

This script parses both binary crash inputs and log assertion messages.
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


# Severity inference from invariant name keywords
SEVERITY_KEYWORDS = {
    "critical": ["solvency", "drain", "mint_authority", "supply_mismatch",
                 "no_roundtrip_profit", "k_invariant", "liquidity_conservation",
                 "vault_solvency", "freeze_authority"],
    "high": ["fee_owed_bounded", "fee_growth_monotonic", "slippage",
             "first_init", "permissionless_setup", "cpi_program_id",
             "flash_loan_state_flag", "cooldown_enforced",
             "tick_consistency", "sqrt_price_bounds"],
    "medium": ["tick_array_bounds", "discriminator", "type_confusion",
               "stale_state", "race", "cu_exhaustion"],
    "low": ["documentation", "minor_inconsistency", "info_disclosure"],
}


def infer_severity(invariant_name: str) -> str:
    name_lower = invariant_name.lower()
    for sev, keywords in SEVERITY_KEYWORDS.items():
        for kw in keywords:
            if kw in name_lower:
                return sev
    return "unknown"


def parse_crash(crash_path: Path) -> dict | None:
    """Parse a Trident crash file. Format may be JSON or binary fuzz input."""
    try:
        # Try JSON first
        content = crash_path.read_text(encoding="utf-8", errors="ignore")
        try:
            data = json.loads(content)
            return {
                "file": str(crash_path),
                "invariant": data.get("invariant", "?"),
                "tx_sequence": data.get("tx_sequence", []),
                "error_message": data.get("error", ""),
                "raw_metadata": data,
            }
        except json.JSONDecodeError:
            # Binary fuzz input — search for invariant marker
            invariant = None
            for line in content.split("\n"):
                if "InvariantViolation" in line or "Invariant" in line:
                    invariant = line.strip()
                    break
            return {
                "file": str(crash_path),
                "invariant": invariant or "unknown",
                "tx_sequence": [],
                "error_message": content[:500],
                "raw_metadata": None,
            }
    except Exception as e:
        return None


def classify_and_dedupe(crashes: list) -> dict:
    """Group crashes by invariant, classify severity."""
    grouped = defaultdict(list)
    for c in crashes:
        if c is None:
            continue
        inv = c.get("invariant", "?")
        grouped[inv].append(c)

    classified = {}
    for inv, crash_list in grouped.items():
        sev = infer_severity(inv)
        classified[inv] = {
            "severity": sev,
            "count": len(crash_list),
            "first_crash_file": crash_list[0]["file"] if crash_list else None,
            "tx_sequences": [c.get("tx_sequence", [])[:5] for c in crash_list[:3]],
        }
    return classified


def severity_priority(sev: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3, "unknown": 4}.get(sev, 5)


def generate_report(classified: dict, output_path: Path | None = None) -> str:
    total_invariants = len(classified)
    total_crashes = sum(c["count"] for c in classified.values())

    sev_counts = Counter(c["severity"] for c in classified.values())

    sorted_invs = sorted(
        classified.items(),
        key=lambda kv: (severity_priority(kv[1]["severity"]), -kv[1]["count"])
    )

    lines = [
        "# Trident Fuzz Crash Analysis",
        "",
        f"Total invariants violated: {total_invariants}",
        f"Total crash inputs: {total_crashes}",
        "",
        "## Severity breakdown",
        "",
    ]
    for sev in ["critical", "high", "medium", "low", "unknown"]:
        n = sev_counts.get(sev, 0)
        if n > 0:
            lines.append(f"- {sev.upper()}: {n} invariant(s)")
    lines.append("")

    lines.append("## Crashes by severity")
    lines.append("")

    for inv, data in sorted_invs:
        lines.append(f"### [{data['severity'].upper()}] {inv}")
        lines.append("")
        lines.append(f"- Crashes: {data['count']}")
        lines.append(f"- First crash: `{data['first_crash_file']}`")
        if data['tx_sequences']:
            lines.append(f"- Sample tx sequence:")
            for tx in data['tx_sequences'][0]:
                lines.append(f"  - {tx}")
        lines.append("")
        lines.append("**Action**: build PoC (Phase S5) demonstrating exploit on local fork.")
        lines.append("")

    if not sorted_invs:
        lines.append("**No crashes found.** Fuzzer ran clean. Either:")
        lines.append("- Protocol is robust (genuine no bugs)")
        lines.append("- Invariants too weak (missed real bugs)")
        lines.append("- Strategy too narrow (didn't explore problematic state space)")
        lines.append("")
        lines.append("Recommend: review invariants list, add more, re-run.")

    report = "\n".join(lines)

    if output_path:
        output_path.write_text(report, encoding="utf-8")
        print(f"[+] Report saved: {output_path}")
    else:
        print(report)

    return report


def find_crash_files(test_dir: Path) -> list:
    """Find crash files in Trident's output locations.

    Trident v0.12 hfuzz workspace structure:
        <test_dir>/hfuzz_workspace/<test_name>/SIGABRT.*.fuzz
        <test_dir>/hfuzz_workspace/<test_name>/HONGGFUZZ.REPORT.TXT
    """
    candidates = []
    # Direct in test_dir
    candidates.extend(test_dir.glob("*.fuzz"))
    candidates.extend(test_dir.glob("crash_*"))

    # hfuzz_workspace nested
    hfuzz_ws = test_dir / "hfuzz_workspace"
    if hfuzz_ws.exists():
        for sub in hfuzz_ws.iterdir():
            if sub.is_dir():
                candidates.extend(sub.glob("*.fuzz"))
                candidates.extend(sub.glob("SIG*.*"))
                candidates.extend(sub.glob("crash_*"))

    return candidates


def find_log_files(test_dir: Path) -> list:
    """Find logs containing assertion messages."""
    logs = []
    log_dir = test_dir / "logs"
    if log_dir.exists():
        logs.extend(log_dir.glob("*.log"))

    hfuzz_ws = test_dir / "hfuzz_workspace"
    if hfuzz_ws.exists():
        for sub in hfuzz_ws.iterdir():
            if sub.is_dir():
                logs.extend(sub.glob("*.TXT"))
                logs.extend(sub.glob("HONGGFUZZ.REPORT*"))

    return logs


def main():
    ap = argparse.ArgumentParser(description="Trident v0.12+ crash analysis")
    ap.add_argument("test_dir", help="Path to trident-tests/<test_name>/ directory")
    ap.add_argument("--output", default=None, help="Write report.md to this path")
    args = ap.parse_args()

    test_dir = Path(args.test_dir)
    if not test_dir.is_dir():
        print(f"[!] Not a directory: {test_dir}", file=sys.stderr)
        sys.exit(1)

    crash_files = find_crash_files(test_dir)
    log_files = find_log_files(test_dir)

    print(f"[*] Searched: {test_dir}")
    print(f"[*] Crash files found: {len(crash_files)}")
    print(f"[*] Log files found: {len(log_files)}")

    if not crash_files and not log_files:
        print(f"[!] No crashes or logs found in {test_dir}")
        print(f"[*] Trident output expected at <test_dir>/hfuzz_workspace/<test_name>/")
        print(f"[*] If fuzz ran clean (no invariant violations), this is expected.")

    crashes = [parse_crash(f) for f in crash_files]
    # Also try to extract from log assertion messages
    for log_f in log_files:
        try:
            content = log_f.read_text(encoding="utf-8", errors="ignore")
            for line in content.split("\n"):
                if "assertion failed" in line.lower() or "VIOLATED" in line or "panicked at" in line:
                    crashes.append({
                        "file": str(log_f),
                        "invariant": line.strip()[:200],
                        "tx_sequence": [],
                        "error_message": line.strip(),
                        "raw_metadata": None,
                    })
        except Exception:
            continue

    classified = classify_and_dedupe(crashes)
    output_path = Path(args.output) if args.output else None
    generate_report(classified, output_path)


if __name__ == "__main__":
    main()
