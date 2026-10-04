#!/usr/bin/env python3
"""
Burp Suite project state export.
Converts our scan findings into Burp-importable XML for manual deep dive.

Most pro hunters use Burp Suite for hands-on investigation. This export
lets you continue from where automated scan left off.

Usage:
    python3 burp_export.py --session sessions/example.com --output burp.xml
"""

import argparse
import json
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path


SEVERITY_MAP = {
    "critical": "High", "high": "High",
    "medium": "Medium", "low": "Low", "info": "Information",
}

CONFIDENCE_MAP = {
    "high": "Certain", "medium": "Firm", "low": "Tentative",
}


def load_findings(session: Path) -> list[dict]:
    findings = []
    for fname in ["scan_summary.json", "web3_summary.json"]:
        f = session / fname
        if f.exists():
            try:
                data = json.loads(f.read_text())
                items = data.get("findings", [])
                findings.extend(items if isinstance(items, list) else [])
            except Exception:
                pass

    nuclei_path = session / "nuclei.json"
    if nuclei_path.exists():
        for line in nuclei_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                findings.append({
                    "id": d.get("template-id"),
                    "vulnerability": d.get("info", {}).get("name", "Nuclei finding"),
                    "severity": d.get("info", {}).get("severity", "info"),
                    "confidence": "high",
                    "host": d.get("host"),
                    "matched_at": d.get("matched-at"),
                    "description": d.get("info", {}).get("description", ""),
                    "tools_flagged": ["nuclei"],
                })
            except Exception:
                continue
    return findings


def build_burp_xml(findings: list[dict], target: str) -> bytes:
    issues = ET.Element("issues",
                         attrib={"burpVersion": "2024.x", "exportTime": time.strftime("%c")})

    for i, f in enumerate(findings, 1):
        issue = ET.SubElement(issues, "issue")
        ET.SubElement(issue, "serialNumber").text = str(i)
        ET.SubElement(issue, "type").text = "0x08000000"
        ET.SubElement(issue, "name").text = f.get("vulnerability", "Unknown")[:200]
        ET.SubElement(issue, "host", attrib={"ip": ""}).text = f.get("host", target)

        path = f.get("matched_at") or f.get("file", "")
        ET.SubElement(issue, "path").text = path
        ET.SubElement(issue, "location").text = path

        severity = SEVERITY_MAP.get(f.get("severity", "info").lower(), "Information")
        ET.SubElement(issue, "severity").text = severity
        confidence = CONFIDENCE_MAP.get(f.get("confidence", "medium").lower(), "Firm")
        ET.SubElement(issue, "confidence").text = confidence

        bg = (f.get("description", "") or "")[:2000]
        if f.get("solodit_matches"):
            sm = f["solodit_matches"]
            if isinstance(sm, list) and sm:
                bg += "\n\nSolodit matches: " + str(len(sm)) + " similar historical findings"

        ET.SubElement(issue, "issueBackground").text = bg
        ET.SubElement(issue, "issueDetail").text = (
            f"Tools flagged: {', '.join(f.get('tools_flagged', []))}\n"
            f"Severity: {f.get('severity', '')}\n"
            f"Confidence: {f.get('confidence', '')}\n"
            f"Lines: {f.get('lines', '')}\n"
            f"SWC: {f.get('swc_id', '')}"
        )

        ET.SubElement(issue, "remediationBackground").text = (
            f.get("remediation", "") or "See finding description and Solodit references"
        )

    return ET.tostring(issues, encoding="utf-8", xml_declaration=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True, help="sessions/<target> path")
    ap.add_argument("--output", required=True, help="Output XML path")
    args = ap.parse_args()

    session = Path(args.session)
    if not session.exists():
        sys.exit(f"Session not found: {session}")

    target = session.name
    findings = load_findings(session)
    if not findings:
        print("[!] No findings to export")
        sys.exit(0)

    xml = build_burp_xml(findings, target)
    Path(args.output).write_bytes(xml)
    print(f"[+] Exported {len(findings)} findings to {args.output}")
    print("[+] Import in Burp: Project menu → Project options → Import")


if __name__ == "__main__":
    main()
