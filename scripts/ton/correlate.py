#!/usr/bin/env python3
"""
Correlates cppcheck + semgrep findings for TON node analysis.
Produces ton_summary.json with deduplicated, prioritized findings.
"""

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime

SEVERITY_WEIGHT = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}

# Patterns that indicate high priority in TON
HIGH_VALUE_KEYWORDS = [
    "catchain", "validator", "consensus", "signature", "verify",
    "election", "elector", "seqno", "round", "block_id",
    "deserializ", "fetch_bytes", "fetch_string", "td::Status",
]


def parse_cppcheck_xml(path: Path) -> list[dict]:
    findings = []
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        for error in root.findall(".//error"):
            severity_raw = error.get("severity", "style")
            severity = {
                "error": "high", "warning": "medium",
                "style": "low", "performance": "low",
                "portability": "low", "information": "info",
            }.get(severity_raw, "low")

            location = error.find("location")
            file_path = location.get("file", "") if location is not None else ""
            line = location.get("line", "0") if location is not None else "0"

            msg = error.get("msg", "")
            check_id = error.get("id", "")

            # Bump priority if it touches key modules
            for kw in HIGH_VALUE_KEYWORDS:
                if kw in file_path.lower() or kw in msg.lower():
                    if severity == "medium":
                        severity = "high"
                    break

            findings.append({
                "tool": "cppcheck",
                "id": f"CPP-{check_id}",
                "severity": severity,
                "file": file_path,
                "line": int(line),
                "message": msg,
                "check": check_id,
            })
    except Exception as e:
        findings.append({"tool": "cppcheck", "error": str(e)})
    return findings


def parse_semgrep_json(path: Path, source: str = "semgrep") -> list[dict]:
    findings = []
    try:
        data = json.loads(path.read_text())
        for r in data.get("results", []):
            severity_raw = r.get("extra", {}).get("severity", "WARNING").lower()
            severity = {"error": "high", "warning": "medium", "info": "low"}.get(
                severity_raw, "medium"
            )
            rule_id = r.get("check_id", "")
            msg = r.get("extra", {}).get("message", "")
            file_path = r.get("path", "")
            start = r.get("start", {})

            for kw in HIGH_VALUE_KEYWORDS:
                if kw in file_path.lower() or kw in msg.lower():
                    if severity == "medium":
                        severity = "high"
                    break

            findings.append({
                "tool": source,
                "id": f"SG-{rule_id.split('.')[-1]}",
                "severity": severity,
                "file": file_path,
                "line": start.get("line", 0),
                "message": msg,
                "rule": rule_id,
            })
    except Exception as e:
        findings.append({"tool": source, "error": str(e)})
    return findings


def deduplicate(findings: list[dict]) -> list[dict]:
    seen = {}
    for f in findings:
        key = (f.get("file", ""), f.get("line", 0), f.get("message", "")[:60])
        if key not in seen:
            seen[key] = f
        else:
            # If 2 tools found the same bug — bump confidence
            existing = seen[key]
            existing["tools_flagged"] = existing.get("tools_flagged", [existing["tool"]])
            if f["tool"] not in existing["tools_flagged"]:
                existing["tools_flagged"].append(f["tool"])
                if existing["severity"] == "medium":
                    existing["severity"] = "high"
    return list(seen.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    inp = Path(args.input)
    findings = []

    cppcheck_xml = inp / "cppcheck.xml"
    if cppcheck_xml.exists():
        findings += parse_cppcheck_xml(cppcheck_xml)

    semgrep_cpp = inp / "semgrep_cpp.json"
    if semgrep_cpp.exists():
        findings += parse_semgrep_json(semgrep_cpp, "semgrep-cpp")

    semgrep_ton = inp / "semgrep_ton.json"
    if semgrep_ton.exists():
        findings += parse_semgrep_json(semgrep_ton, "semgrep-ton-custom")

    findings = deduplicate(findings)
    findings.sort(
        key=lambda x: SEVERITY_WEIGHT.get(x.get("severity", "low"), 0),
        reverse=True,
    )

    # Filter out obvious noise (style-only, no critical context)
    high_findings = [f for f in findings if f.get("severity") in ("critical", "high")]
    medium_findings = [f for f in findings if f.get("severity") == "medium"]

    summary = {
        "target": "ton-blockchain/ton",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "tools_run": ["cppcheck", "semgrep-cpp", "semgrep-ton-custom"],
        "total_findings": len(findings),
        "high_priority": len(high_findings),
        "findings": findings[:50],  # top-50 for Claude review
        "note": (
            "Next step: Claude AI pass — open checklists/cpp_logic.md "
            "and verify each high_priority finding manually. "
            "Submit via @ton_bugs_bot on Telegram."
        ),
    }

    Path(args.output).write_text(json.dumps(summary, indent=2))
    print(f"[+] {len(findings)} total | {len(high_findings)} high priority")
    print(f"[+] Saved: {args.output}")

    if high_findings:
        print("\n[!] Top HIGH findings for Claude review:")
        for f in high_findings[:5]:
            print(f"  [{f['severity'].upper()}] {f.get('file','?')}:{f.get('line','?')} — {f.get('message','')[:80]}")


if __name__ == "__main__":
    main()
