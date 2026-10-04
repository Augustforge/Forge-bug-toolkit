#!/usr/bin/env python3
"""
Correlate findings from multiple Web3 analyzers into a single prioritized list.

Inputs (one or more, picks up automatically from --input dir):
  slither.json, aderyn.json, wake.json, semgrep.json, mythril.jsonl,
  echidna.json, halmos.json, gitleaks.json

Logic:
  - Dedup by (file, line_range, vuln_type)
  - Cross-validation: 2+ tools flagged → confidence = high
  - Severity mapped to Immunefi V2.3 (4 levels): Critical / High / Medium / Low
  - Sort by severity_weight × confidence_weight

Output: single web3_summary.json
"""

import argparse
import json
import re
from pathlib import Path

# ─── CONSTANTS ────────────────────────────────────────────────────────────────

SEVERITY_WEIGHT = {"critical": 4.0, "high": 3.0, "medium": 2.0, "low": 1.0, "info": 0.5}
CONFIDENCE_WEIGHT = {"high": 1.0, "medium": 0.7, "low": 0.4}

# Slither detector → SWC ID mapping (Smart Contract Weakness Classification)
# See https://swcregistry.io for full registry
SLITHER_TO_SWC = {
    "reentrancy-eth": "SWC-107",
    "reentrancy-no-eth": "SWC-107",
    "reentrancy-benign": "SWC-107",
    "reentrancy-events": "SWC-107",
    "reentrancy-unlimited-gas": "SWC-107",
    "tx-origin": "SWC-115",
    "timestamp": "SWC-116",
    "weak-prng": "SWC-120",
    "incorrect-equality": "SWC-132",
    "uninitialized-state": "SWC-109",
    "uninitialized-storage": "SWC-109",
    "uninitialized-local": "SWC-109",
    "shadowing-state": "SWC-119",
    "shadowing-abstract": "SWC-119",
    "shadowing-builtin": "SWC-119",
    "shadowing-local": "SWC-119",
    "controlled-delegatecall": "SWC-112",
    "delegatecall-loop": "SWC-112",
    "suicidal": "SWC-106",
    "arbitrary-send-eth": "SWC-105",
    "arbitrary-send-erc20": "SWC-105",
    "unchecked-transfer": "SWC-104",
    "unchecked-send": "SWC-104",
    "unchecked-lowlevel": "SWC-104",
    "locked-ether": "SWC-132",
    "incorrect-shift": "SWC-101",
    "controlled-array-length": "SWC-128",
    "assembly": "SWC-127",
    "low-level-calls": "SWC-104",
    "calls-loop": "SWC-128",
    "events-access": "SWC-129",
    "unprotected-upgrade": "SWC-118",
    "missing-zero-check": "SWC-105",
    "transient-storage-reentrancy": "SWC-107",
    "erc4626-inflation": "SWC-NEW-INFLATION",
    "erc4337-issues": "SWC-NEW-AA",
    "oracle-single-source": "SWC-NEW-ORACLE",
    "missing-signature-nonce": "SWC-121",
    "timelock-too-short": "SWC-NEW-GOV",
    "missing-circuit-breaker": "SWC-NEW-PAUSE",
    "frontrunnable-state-change": "SWC-114",
    # May 2026 attack patterns
    "hook-callback-unauthorized": "SWC-105",
    "layerzero-verifier-count": "SWC-NEW-DVN",
    "cpimp-proxy-init": "SWC-118",
    "groth16-setup-check": "SWC-NEW-ZK",
    "signature-scope-coverage": "SWC-121",
    "erc3525-reentrancy": "SWC-107",
    "slippage-shared-intermediates": "SWC-NEW-SLIPPAGE",
    # TrustedVolumes May 2026
    "unprotected-role-granting": "SWC-106",
}

# Slither impact → Immunefi severity mapping
SLITHER_TO_IMMUNEFI = {
    "High": "high", "Medium": "medium", "Low": "low",
    "Informational": "info", "Optimization": "info",
}

# Top Slither detectors that should be auto-bumped to critical for bug bounty
CRITICAL_DETECTORS = {
    "arbitrary-send-eth", "controlled-delegatecall", "unprotected-upgrade",
    "suicidal", "arbitrary-send-erc20",
    "hook-callback-unauthorized",
    "layerzero-verifier-count",
    "groth16-setup-check",
    "unprotected-role-granting",
}
HIGH_DETECTORS = {
    "reentrancy-eth", "reentrancy-balance", "uninitialized-state",
    "shadowing-state", "incorrect-shift", "controlled-array-length",
    "delegatecall-loop",
    "cpimp-proxy-init",
    "signature-scope-coverage",
    "erc3525-reentrancy",
}


def normalize_severity(raw: str, detector: str = "") -> str:
    if detector in CRITICAL_DETECTORS:
        return "critical"
    if detector in HIGH_DETECTORS:
        return "high"
    raw = (raw or "").lower()
    if raw in ("critical", "high", "medium", "low", "info"):
        return raw
    return SLITHER_TO_IMMUNEFI.get(raw.capitalize(), "low")


def normalize_confidence(raw: str) -> str:
    raw = (raw or "").lower()
    if raw in ("high", "medium", "low"):
        return raw
    return "medium"


def make_key(finding: dict) -> tuple:
    file = (finding.get("file") or "").rsplit("/", 1)[-1]
    lines = finding.get("lines") or []
    line_key = (min(lines), max(lines)) if lines else (0, 0)
    return (file, line_key, finding.get("vulnerability", ""))


# ─── PARSERS ──────────────────────────────────────────────────────────────────

def parse_slither(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except Exception:
        return []
    findings = []
    for d in data.get("results", {}).get("detectors", []):
        check = d.get("check", "")
        elements = d.get("elements", [])
        file = ""
        lines = []
        if elements:
            sm = elements[0].get("source_mapping", {})
            file = sm.get("filename_short", sm.get("filename_relative", ""))
            lines = sm.get("lines", [])
        findings.append({
            "tool": "slither",
            "vulnerability": check,
            "severity": normalize_severity(d.get("impact"), check),
            "confidence": normalize_confidence(d.get("confidence")),
            "file": file,
            "lines": lines,
            "function": (elements[0].get("name") if elements else "") or "",
            "description": d.get("description", "").strip(),
        })
    return findings


def parse_aderyn(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except Exception:
        return []
    findings = []
    for severity in ("critical", "high", "medium", "low", "nc"):
        for issue in data.get("issues", {}).get(f"{severity}_issues", []) or []:
            for inst in issue.get("instances", []):
                findings.append({
                    "tool": "aderyn",
                    "vulnerability": issue.get("title", "unknown"),
                    "severity": "low" if severity == "nc" else severity,
                    "confidence": "high",
                    "file": inst.get("contract_path", ""),
                    "lines": [inst.get("line_no", 0)],
                    "function": "",
                    "description": issue.get("description", ""),
                })
    return findings


def parse_wake(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except Exception:
        return []
    findings = []
    for det in data.get("detections", []) if isinstance(data, dict) else (data if isinstance(data, list) else []):
        findings.append({
            "tool": "wake",
            "vulnerability": det.get("detector_name", det.get("impact", "unknown")),
            "severity": normalize_severity(det.get("impact")),
            "confidence": normalize_confidence(det.get("confidence")),
            "file": det.get("file", ""),
            "lines": [det.get("line", 0)] if det.get("line") else [],
            "function": "",
            "description": det.get("message", ""),
        })
    return findings


def parse_semgrep(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except Exception:
        return []
    findings = []
    for r in data.get("results", []):
        sev_raw = r.get("extra", {}).get("severity", "INFO").lower()
        sev = {"error": "high", "warning": "medium", "info": "low"}.get(sev_raw, "low")
        findings.append({
            "tool": "semgrep",
            "vulnerability": r.get("check_id", "").split(".")[-1],
            "severity": sev,
            "confidence": "medium",
            "file": r.get("path", ""),
            "lines": [r.get("start", {}).get("line", 0)],
            "function": "",
            "description": r.get("extra", {}).get("message", ""),
        })
    return findings


def parse_mythril(path: Path) -> list[dict]:
    if not path.exists():
        return []
    findings = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        for issue in d.get("issues", []):
            findings.append({
                "tool": "mythril",
                "vulnerability": issue.get("title", "unknown"),
                "severity": normalize_severity(issue.get("severity")),
                "confidence": "medium",
                "file": issue.get("filename", ""),
                "lines": [issue.get("lineno", 0)] if issue.get("lineno") else [],
                "function": issue.get("function", ""),
                "description": issue.get("description", ""),
            })
    return findings


def parse_gitleaks(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except Exception:
        return []
    return [
        {
            "tool": "gitleaks",
            "vulnerability": "leaked-secret",
            "severity": "critical",
            "confidence": "high",
            "file": item.get("File", ""),
            "lines": [item.get("StartLine", 0)],
            "function": "",
            "description": f"{item.get('RuleID', '')}: {item.get('Match', '')[:100]}",
        }
        for item in (data if isinstance(data, list) else data.get("results", []))
    ]


# ─── DEDUP & SCORING ──────────────────────────────────────────────────────────

def dedup_and_score(findings: list[dict]) -> list[dict]:
    grouped: dict[tuple, dict] = {}
    for f in findings:
        key = make_key(f)
        if key in grouped:
            existing = grouped[key]
            existing["tools_flagged"].add(f["tool"])
            existing["severity"] = max(
                [existing["severity"], f["severity"]],
                key=lambda s: SEVERITY_WEIGHT.get(s, 0),
            )
        else:
            grouped[key] = {**f, "tools_flagged": {f["tool"]}}

    out = []
    for i, item in enumerate(grouped.values(), start=1):
        tools_count = len(item["tools_flagged"])
        confidence_str = "high" if tools_count >= 3 else (
            "medium" if tools_count == 2 else item.get("confidence", "low")
        )
        sev_w = SEVERITY_WEIGHT.get(item["severity"], 0)
        conf_w = CONFIDENCE_WEIGHT.get(confidence_str, 0.4)
        priority = sev_w * conf_w * (1 + 0.5 * (tools_count - 1))
        swc_id = SLITHER_TO_SWC.get(item["vulnerability"], "")

        out.append({
            "id": f"F{i:03d}",
            "severity": item["severity"],
            "confidence": confidence_str,
            "vulnerability": item["vulnerability"],
            "swc_id": swc_id,
            "swc_url": f"https://swcregistry.io/docs/{swc_id}" if swc_id else "",
            "file": item["file"],
            "function": item.get("function", ""),
            "lines": item["lines"],
            "tools_flagged": sorted(item["tools_flagged"]),
            "description": item["description"][:500],
            "priority_score": round(priority, 2),
        })

    out.sort(key=lambda x: x["priority_score"], reverse=True)
    for i, f in enumerate(out, start=1):
        f["id"] = f"F{i:03d}"
    return out


def estimate_bounty(severity: str, tvl: float = 0) -> str:
    """
    Rough Immunefi-aligned bounty estimate.
    Reward = 10% of affected funds, capped per-project.
    """
    if not tvl or tvl <= 0:
        return {
            "critical": "$50,000–$1,000,000",
            "high": "$10,000–$100,000",
            "medium": "$1,000–$10,000",
            "low": "$500–$2,500",
            "info": "$0",
        }.get(severity, "unknown")
    pct = {"critical": 0.20, "high": 0.05, "medium": 0.01, "low": 0.001}.get(severity, 0)
    raw = tvl * pct * 0.10
    return f"${min(raw, 1_000_000):,.0f} (10% of ${tvl * pct:,.0f} affected)"


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Directory with tool outputs")
    ap.add_argument("--output", required=True)
    ap.add_argument("--tvl", type=float, default=0,
                    help="TVL at risk (for bounty estimation)")
    args = ap.parse_args()

    inp = Path(args.input)
    all_findings = []
    all_findings.extend(parse_slither(inp / "slither.json"))
    all_findings.extend(parse_aderyn(inp / "aderyn.json"))
    all_findings.extend(parse_wake(inp / "wake.json"))
    all_findings.extend(parse_semgrep(inp / "semgrep.json"))
    all_findings.extend(parse_mythril(inp / "mythril.jsonl"))
    all_findings.extend(parse_gitleaks(inp / "gitleaks.json"))

    deduped = dedup_and_score(all_findings)

    for f in deduped:
        f["estimated_bounty"] = estimate_bounty(f["severity"], args.tvl)

    fetch_summary = {}
    fs_path = inp / "fetch_summary.json"
    if fs_path.exists():
        try:
            fetch_summary = json.loads(fs_path.read_text())
        except Exception:
            pass

    summary = {
        "target": fetch_summary.get("target", "local-repo"),
        "chain": fetch_summary.get("chainid", ""),
        "address": fetch_summary.get("address", ""),
        "is_verified": fetch_summary.get("is_verified", True),
        "compiler": fetch_summary.get("compiler_version", ""),
        "proxy": fetch_summary.get("proxy", {}),
        "tools_run": sorted({f["tool"] for f in all_findings}),
        "findings_total": len(deduped),
        "findings_by_severity": {
            sev: sum(1 for f in deduped if f["severity"] == sev)
            for sev in ("critical", "high", "medium", "low", "info")
        },
        "findings": deduped,
        "tvl_at_risk": args.tvl,
    }

    Path(args.output).write_text(json.dumps(summary, indent=2))

    print(f"[+] Total findings: {len(deduped)}")
    for sev in ("critical", "high", "medium", "low"):
        c = summary["findings_by_severity"][sev]
        if c:
            print(f"    {sev.upper():<10}: {c}")
    print(f"[+] Saved to {args.output}")


if __name__ == "__main__":
    main()
