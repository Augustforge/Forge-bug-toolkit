#!/usr/bin/env python3
"""
correlate.py — Merge Solana findings, deduplicate, map severity to Immunefi.

Reads outputs from hypothesis/, specialized/, detectors/ folders.
Outputs unified solana_summary.json.

Solana-specific severity mapping (Immunefi Solana classification):
- Critical: direct fund loss / unauthorized minting / permanent freezing
- High: temporary freezing / griefing / oracle manipulation
- Medium: griefing without direct loss / DoS specific functions
- Low: optimization / non-exploitable issues
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path


SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


def classify_severity(finding: dict) -> str:
    """Map finding to Immunefi-style severity."""
    cls = finding.get("class", "").lower()
    confidence = finding.get("confidence", "low").lower()

    critical_classes = {
        "missing_signer_check", "missing_owner_check", "cpi_program_id_unchecked",
        "account_trust_violation", "flash_loan_state_bypass", "durable_nonce_governance",
        "bridge_signature_replay", "zk_proof_forgery", "lamports_drain",
    }
    high_classes = {
        "pda_seed_collision", "account_reinit", "type_confusion",
        "arithmetic_overflow", "discriminator_collision", "transfer_hook_reentrancy",
        "bidirectional_rounding", "permissionless_setup_race", "time_horizon_extension",
        "callback_state_mutation", "inverse_op_asymmetry",
    }
    medium_classes = {
        "sysvar_trust", "compute_dos", "rent_drift", "stale_oracle",
        "sealevel_race", "cu_budget_dos",
    }

    if any(c in cls for c in critical_classes):
        return "critical" if confidence in ("high", "medium") else "high"
    if any(c in cls for c in high_classes):
        return "high" if confidence == "high" else "medium"
    if any(c in cls for c in medium_classes):
        return "medium"
    return "low"


def dedupe(findings: list) -> list:
    """Deduplicate by (file, line, class)."""
    seen = {}
    for f in findings:
        key = (f.get("file"), f.get("line"), f.get("class"))
        if key in seen:
            existing = seen[key]
            if SEVERITY_ORDER.get(f.get("severity", "low"), 0) > SEVERITY_ORDER.get(existing.get("severity", "low"), 0):
                seen[key] = f
        else:
            seen[key] = f
    return list(seen.values())


def load_findings(scan_dir: Path) -> list:
    findings = []
    for json_file in scan_dir.rglob("*.json"):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        item.setdefault("source_script", json_file.name)
                        findings.append(item)
            elif isinstance(data, dict):
                if "findings" in data and isinstance(data["findings"], list):
                    for item in data["findings"]:
                        item.setdefault("source_script", json_file.name)
                        findings.append(item)
        except Exception:
            continue
    return findings


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Correlate Solana findings into unified summary")
    ap.add_argument("--scan-dir", required=True, help="Directory with hypothesis/specialized/detector outputs")
    ap.add_argument("--output", required=True, help="Output JSON path")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    scan_dir = Path(args.scan_dir)
    if not scan_dir.is_dir():
        print(f"[!] Scan dir not found: {scan_dir}")
        return 1

    raw = load_findings(scan_dir)
    for f in raw:
        if "severity" not in f or not f["severity"]:
            f["severity"] = classify_severity(f)

    deduped = dedupe(raw)
    deduped.sort(key=lambda x: (-SEVERITY_ORDER.get(x.get("severity", "low"), 0), x.get("classification") == "novel_instance"))

    summary = {
        "chain": "solana",
        "total_findings": len(deduped),
        "by_severity": dict(
            (sev, sum(1 for f in deduped if f.get("severity") == sev))
            for sev in ("critical", "high", "medium", "low", "info")
        ),
        "by_class": dict(
            (cls, sum(1 for f in deduped if f.get("class") == cls))
            for cls in set(f.get("class") for f in deduped if f.get("class"))
        ),
        "novel_instances": sum(1 for f in deduped if f.get("classification") == "novel_instance"),
        "known_classes": sum(1 for f in deduped if f.get("classification") == "known_class"),
        "findings": deduped,
    }

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    if not args.quiet:
        print(f"[+] Total findings: {summary['total_findings']}")
        print(f"[+] By severity: {summary['by_severity']}")
        print(f"[+] Novel instances: {summary['novel_instances']} (high priority)")
        print(f"[+] Known classes:   {summary['known_classes']}")
        print(f"[+] Output:          {args.output}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
