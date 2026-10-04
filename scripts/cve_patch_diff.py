#!/usr/bin/env python3
"""
CVE patch diff — daily scan of fresh CVEs from NVD vs our sessions targets.

When a new CVE is published — check all our target tech stacks
against the affected version. If match → high-priority alert.

Sources:
- NVD CVE feed: https://services.nvd.nist.gov/rest/json/cves/2.0
- GitHub Security Advisories: https://api.github.com/advisories
- ProjectDiscovery nuclei templates (as a fast path)

Usage:
    python3 cve_patch_diff.py --sessions sessions/ --output sessions/_cve_alerts/
"""

import argparse
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


def fetch_recent_cves(days: int = 7) -> list[dict]:
    """Fetch recent CVEs from NVD."""
    pub_start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000")
    pub_end = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000")
    try:
        r = requests.get(
            "https://services.nvd.nist.gov/rest/json/cves/2.0",
            params={"pubStartDate": pub_start, "pubEndDate": pub_end,
                    "resultsPerPage": 100},
            timeout=30,
        )
        if r.status_code != 200:
            return []
        return r.json().get("vulnerabilities", [])
    except Exception as e:
        print(f"[!] NVD fetch failed: {e}")
        return []


def fetch_recent_ghsa(days: int = 7) -> list[dict]:
    """GitHub Security Advisories."""
    headers = {"Accept": "application/vnd.github+json"}
    if os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.getenv('GITHUB_TOKEN')}"
    try:
        r = requests.get(
            "https://api.github.com/advisories",
            headers=headers,
            params={"per_page": 100, "type": "reviewed"},
            timeout=30,
        )
        if r.status_code != 200:
            return []
        return r.json()
    except Exception:
        return []


def collect_target_techs(sessions_dir: Path) -> dict[str, list[str]]:
    """Per-target detected technologies (CMS, framework, version)."""
    techs = {}
    for session in sessions_dir.iterdir():
        if not session.is_dir() or session.name.startswith("_"):
            continue
        target_techs = []
        for fname in ["fingerprint_summary.json", "technologies.txt"]:
            f = session / fname
            if not f.exists():
                continue
            try:
                if fname.endswith(".json"):
                    data = json.loads(f.read_text())
                    target_techs.append(json.dumps(data))
                else:
                    target_techs.extend(f.read_text(encoding="utf-8").splitlines())
            except Exception:
                continue
        if target_techs:
            techs[session.name] = target_techs
    return techs


def match_cve_to_target(cve: dict, target_techs: list[str]) -> bool:
    """Heuristic: keyword match between CVE description and target tech."""
    descriptions = []
    for desc in cve.get("cve", {}).get("descriptions", []):
        if desc.get("lang") == "en":
            descriptions.append(desc.get("value", ""))
    cve_text = " ".join(descriptions).lower()

    config_keys = []
    for cfg in cve.get("cve", {}).get("configurations", []):
        for node in cfg.get("nodes", []):
            for cpe in node.get("cpeMatch", []):
                config_keys.append(cpe.get("criteria", ""))

    target_text = " ".join(target_techs).lower()

    cve_keywords = re.findall(r"\b(wordpress|drupal|magento|joomla|nginx|apache|openssh|"
                               r"jquery|nodejs|express|django|spring|react|vue|angular|"
                               r"jboss|tomcat|websphere|kubernetes|docker|"
                               r"php|mysql|postgres|redis|mongo)\b", cve_text)

    for kw in cve_keywords:
        if kw in target_text:
            return True
    for cpe in config_keys:
        for part in cpe.lower().split(":"):
            if len(part) >= 4 and part in target_text:
                return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", default="sessions/")
    ap.add_argument("--output", required=True)
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    print(f"[*] Fetching CVEs from last {args.days} days...")
    cves = fetch_recent_cves(args.days)
    print(f"    NVD: {len(cves)}")
    ghsa = fetch_recent_ghsa(args.days)
    print(f"    GHSA: {len(ghsa)}")

    print("[*] Collecting target technologies...")
    target_techs = collect_target_techs(Path(args.sessions))
    print(f"    {len(target_techs)} sessions analyzed")

    alerts = []
    for cve in cves:
        cve_id = cve.get("cve", {}).get("id", "")
        for target, techs in target_techs.items():
            if match_cve_to_target(cve, techs):
                metrics = cve.get("cve", {}).get("metrics", {})
                cvss_v3 = metrics.get("cvssMetricV31", [{}])[0].get("cvssData", {}).get("baseScore", 0)
                alerts.append({
                    "cve": cve_id,
                    "target": target,
                    "cvss": cvss_v3,
                    "description": (cve.get("cve", {}).get("descriptions", [{}])[0]
                                    .get("value", ""))[:300],
                })

    out_file = out / f"cve_alerts_{time.strftime('%Y-%m-%d')}.json"
    out_file.write_text(json.dumps({
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "alerts_count": len(alerts),
        "alerts": alerts,
    }, indent=2, ensure_ascii=False))

    print(f"\n[+] {len(alerts)} potential CVE alerts")
    high_severity = [a for a in alerts if a["cvss"] >= 7.0]
    if high_severity:
        print(f"[!] HIGH SEVERITY ({len(high_severity)}):")
        for a in high_severity[:5]:
            print(f"    {a['cve']} on {a['target']} (CVSS {a['cvss']})")
    print(f"[+] Saved: {out_file}")


if __name__ == "__main__":
    main()
