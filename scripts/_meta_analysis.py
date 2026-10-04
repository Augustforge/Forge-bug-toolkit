#!/usr/bin/env python3
"""
Meta-analysis of own sessions.

Tracks per-tool effectiveness over time, identifies blind spots,
suggests where to add custom detectors / checklists.

Run weekly to get data-driven feedback for tuning the toolkit.

Usage:
    python3 _meta_analysis.py --sessions sessions/ --output meta_report.md
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def collect_findings(sessions_dir: Path) -> list[dict]:
    findings = []
    for session in sessions_dir.iterdir():
        if not session.is_dir() or session.name.startswith("_"):
            continue
        target = session.name

        for fname in ["scan_summary.json", "web3_summary.json"]:
            f = session / fname
            if not f.exists():
                continue
            try:
                data = json.loads(f.read_text())
                for finding in data.get("findings", []):
                    finding["target"] = target
                    finding["source_file"] = fname
                    findings.append(finding)
            except Exception:
                continue
    return findings


def analyze(findings: list[dict]) -> dict:
    total = len(findings)
    by_tool = Counter()
    by_severity = Counter()
    by_vuln = Counter()
    by_swc = Counter()

    confirmed_per_tool = defaultdict(int)
    rejected_per_tool = defaultdict(int)
    total_per_tool = defaultdict(int)

    for f in findings:
        for tool in f.get("tools_flagged", []):
            by_tool[tool] += 1
            total_per_tool[tool] += 1

        verification = f.get("verification", {})
        status = verification.get("status", "unknown")
        for tool in f.get("tools_flagged", []):
            if status == "verified":
                confirmed_per_tool[tool] += 1
            elif status == "false_positive":
                rejected_per_tool[tool] += 1

        by_severity[f.get("severity", "unknown")] += 1
        by_vuln[f.get("vulnerability", "unknown")] += 1
        if f.get("swc_id"):
            by_swc[f["swc_id"]] += 1

    tool_effectiveness = {}
    for tool, total in total_per_tool.items():
        confirmed = confirmed_per_tool[tool]
        rejected = rejected_per_tool[tool]
        unknown = total - confirmed - rejected
        tool_effectiveness[tool] = {
            "total": total,
            "confirmed": confirmed,
            "false_positive": rejected,
            "unknown_status": unknown,
            "confirmation_rate": round(confirmed / total * 100, 1) if total else 0,
            "fp_rate": round(rejected / total * 100, 1) if total else 0,
        }

    return {
        "total_findings": total,
        "unique_targets": len({f["target"] for f in findings}),
        "by_severity": dict(by_severity),
        "top_vulnerabilities": dict(by_vuln.most_common(15)),
        "top_swc": dict(by_swc.most_common(10)),
        "tool_effectiveness": tool_effectiveness,
    }


def render_markdown(analysis: dict) -> str:
    lines = ["# Meta Analysis — Toolkit Performance Report", ""]
    lines.append(f"- Total findings: {analysis['total_findings']}")
    lines.append(f"- Unique targets: {analysis['unique_targets']}")
    lines.append("")

    lines.append("## By Severity")
    for sev, count in sorted(analysis["by_severity"].items(),
                              key=lambda x: ["critical", "high", "medium", "low", "info"].index(x[0])
                              if x[0] in ["critical", "high", "medium", "low", "info"] else 99):
        lines.append(f"- {sev}: {count}")
    lines.append("")

    lines.append("## Tool Effectiveness")
    lines.append("| Tool | Total | Confirmed | FP | Confirm% | FP% |")
    lines.append("|------|-------|-----------|-----|----------|------|")
    for tool, stats in sorted(analysis["tool_effectiveness"].items(),
                               key=lambda x: -x[1]["total"]):
        lines.append(f"| {tool} | {stats['total']} | {stats['confirmed']} | "
                     f"{stats['false_positive']} | {stats['confirmation_rate']}% | "
                     f"{stats['fp_rate']}% |")
    lines.append("")

    lines.append("## Top Vulnerability Categories Found")
    for vuln, count in analysis["top_vulnerabilities"].items():
        lines.append(f"- {vuln}: {count}")
    lines.append("")

    lines.append("## Recommendations (data-driven)")
    high_fp_tools = [
        t for t, s in analysis["tool_effectiveness"].items()
        if s["fp_rate"] > 50 and s["total"] >= 5
    ]
    if high_fp_tools:
        lines.append(f"- ⚠️ High FP rate (>50%): {', '.join(high_fp_tools)} — review tuning")

    low_confirm_tools = [
        t for t, s in analysis["tool_effectiveness"].items()
        if s["confirmation_rate"] < 10 and s["total"] >= 10
    ]
    if low_confirm_tools:
        lines.append(f"- ⚠️ Low confirmation rate (<10%): {', '.join(low_confirm_tools)} "
                     f"— possibly noisy or needs better quick_verify")

    if not analysis["top_swc"]:
        lines.append("- ⚠️ No SWC IDs assigned — extend SWC mapping in correlate.py")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", default="sessions/", help="Sessions directory")
    ap.add_argument("--output", default="meta_report.md")
    args = ap.parse_args()

    sessions = Path(args.sessions)
    if not sessions.exists():
        print(f"[!] Sessions dir not found: {sessions}")
        return

    print(f"[*] Collecting findings from {sessions}/")
    findings = collect_findings(sessions)
    if not findings:
        print("[i] No findings yet — run /hunt on some targets first")
        return

    print(f"[*] Analyzing {len(findings)} findings...")
    analysis = analyze(findings)

    Path(args.output).write_text(render_markdown(analysis), encoding="utf-8")
    print(f"[+] Report saved to {args.output}")
    print(f"[+] Findings: {analysis['total_findings']} | "
          f"Targets: {analysis['unique_targets']}")


if __name__ == "__main__":
    main()
