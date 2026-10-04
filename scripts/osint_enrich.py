#!/usr/bin/env python3
"""
OSINT enrichment for target companies.

Sources:
- Hunter.io — emails for the domain (find security@ contact)
- BuiltWith API — tech stack (faster than running wappalyzer)
- security.txt — the official disclosure contact
- DNS WHOIS — registration info, age
- Wayback first seen — domain age proxy

Usage:
    python3 osint_enrich.py --domain example.com --output sessions/example.com
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests

HUNTER_KEY = os.getenv("HUNTER_API_KEY", "")
BUILTWITH_KEY = os.getenv("BUILTWITH_API_KEY", "")


def hunter_emails(domain: str) -> dict:
    if not HUNTER_KEY:
        return {"error": "HUNTER_API_KEY not set"}
    try:
        r = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": HUNTER_KEY, "limit": 25},
            timeout=20,
        )
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}"}
        data = r.json().get("data", {})
        emails = data.get("emails", [])
        security_contacts = [
            e for e in emails
            if any(k in (e.get("value", "") or "").lower()
                   for k in ["security", "abuse", "disclosure", "infosec"])
        ]
        return {
            "organization": data.get("organization"),
            "country": data.get("country"),
            "linkedin": data.get("linkedin"),
            "twitter": data.get("twitter"),
            "total_emails": len(emails),
            "security_contacts": [
                {"email": e.get("value"), "name": f"{e.get('first_name', '')} {e.get('last_name', '')}".strip(),
                 "position": e.get("position"), "confidence": e.get("confidence")}
                for e in security_contacts
            ],
            "all_emails_top10": [e.get("value") for e in emails[:10]],
        }
    except Exception as e:
        return {"error": str(e)}


def security_txt(domain: str) -> dict:
    """RFC 9116 — the official disclosure contact."""
    candidates = [
        f"https://{domain}/.well-known/security.txt",
        f"https://{domain}/security.txt",
    ]
    for url in candidates:
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200 and "Contact:" in r.text:
                lines = [l.strip() for l in r.text.splitlines() if l.strip()
                         and not l.strip().startswith("#")]
                fields = {}
                for line in lines:
                    if ":" in line:
                        k, v = line.split(":", 1)
                        fields.setdefault(k.strip(), []).append(v.strip())
                return {"url": url, "fields": fields}
        except Exception:
            continue
    return {"error": "no security.txt found"}


def builtwith(domain: str) -> dict:
    if not BUILTWITH_KEY:
        return {"error": "BUILTWITH_API_KEY not set"}
    try:
        r = requests.get(
            "https://api.builtwith.com/v21/api.json",
            params={"KEY": BUILTWITH_KEY, "LOOKUP": domain},
            timeout=30,
        )
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}"}
        data = r.json()
        results = data.get("Results", [])
        if not results:
            return {"error": "no data"}
        paths = results[0].get("Result", {}).get("Paths", [])
        techs = []
        for p in paths:
            for t in p.get("Technologies", []):
                techs.append({"name": t.get("Name"), "tag": t.get("Tag"),
                              "first_seen": t.get("FirstDetected"),
                              "last_seen": t.get("LastDetected")})
        return {"technologies_count": len(techs), "technologies_top20": techs[:20]}
    except Exception as e:
        return {"error": str(e)}


def wayback_first_seen(domain: str) -> dict:
    """Domain age proxy via Wayback Machine."""
    try:
        r = requests.get(
            "http://archive.org/wayback/available",
            params={"url": domain, "timestamp": "19960101"},
            timeout=15,
        )
        if r.status_code != 200:
            return {"error": "wayback unavailable"}
        snap = r.json().get("archived_snapshots", {}).get("closest", {})
        ts = snap.get("timestamp")
        if not ts:
            return {"error": "no snapshot"}
        first = datetime.strptime(ts, "%Y%m%d%H%M%S")
        age_years = (datetime.utcnow() - first).days / 365
        return {
            "first_seen": first.isoformat(),
            "age_years": round(age_years, 1),
            "snapshot_url": snap.get("url"),
        }
    except Exception as e:
        return {"error": str(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    print(f"[*] OSINT enrichment for: {args.domain}")
    result = {
        "domain": args.domain,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    print("[*] security.txt...")
    result["security_txt"] = security_txt(args.domain)

    print("[*] Hunter.io emails...")
    result["hunter"] = hunter_emails(args.domain)

    print("[*] BuiltWith tech stack...")
    result["builtwith"] = builtwith(args.domain)

    print("[*] Wayback Machine domain age...")
    result["wayback"] = wayback_first_seen(args.domain)

    target_file = out / "osint.json"
    target_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    print(f"[+] Saved to {target_file}")

    # Recommendation summary
    print("\n[i] Disclosure contact recommendations:")
    sec_txt = result.get("security_txt", {}).get("fields", {})
    if sec_txt.get("Contact"):
        print(f"  • From security.txt: {sec_txt['Contact'][0]}")
    if isinstance(result.get("hunter"), dict):
        for sc in result["hunter"].get("security_contacts", []):
            print(f"  • Hunter: {sc['email']} ({sc.get('name', '')})")
    if not sec_txt and not result.get("hunter", {}).get("security_contacts"):
        print(f"  • Fallback: security@{args.domain}")


if __name__ == "__main__":
    main()
