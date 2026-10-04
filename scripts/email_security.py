#!/usr/bin/env python3
"""
Email security check — SPF, DMARC, DKIM, MX misconfigurations.
Often a valid bug bounty report in a minute.

Usage:
    python3 email_security.py --domain example.com --output ./out
"""

import argparse
import json
from pathlib import Path

import dns.resolver


def query(domain: str, record_type: str) -> list[str]:
    try:
        answers = dns.resolver.resolve(domain, record_type, lifetime=10)
        return [str(r) for r in answers]
    except Exception:
        return []


def check_spf(domain: str) -> dict:
    txt_records = query(domain, "TXT")
    spf = [r for r in txt_records if "v=spf1" in r.lower()]
    issues = []

    if not spf:
        return {"status": "MISSING", "severity": "MEDIUM",
                "issues": ["No SPF record — domain spoofable"]}

    spf_str = spf[0].lower()
    if "+all" in spf_str:
        issues.append("CRITICAL: +all allows ANY sender")
    elif "?all" in spf_str:
        issues.append("HIGH: ?all (neutral) — weak protection")
    elif "~all" in spf_str:
        issues.append("LOW: ~all (softfail) — accepts spoofed mail")
    elif "-all" in spf_str:
        pass  # good
    else:
        issues.append("MEDIUM: missing 'all' mechanism")

    return {
        "status": "FOUND",
        "record": spf[0],
        "severity": "HIGH" if "+all" in spf_str else "INFO",
        "issues": issues,
    }


def check_dmarc(domain: str) -> dict:
    records = query(f"_dmarc.{domain}", "TXT")
    dmarc = [r for r in records if "v=dmarc1" in r.lower()]
    issues = []

    if not dmarc:
        return {"status": "MISSING", "severity": "HIGH",
                "issues": ["No DMARC record — phishing not blocked"]}

    rec = dmarc[0].lower()
    if "p=none" in rec:
        issues.append("MEDIUM: p=none (monitor only, not enforced)")
    elif "p=quarantine" in rec:
        issues.append("INFO: p=quarantine (partial enforcement)")
    elif "p=reject" in rec:
        pass
    else:
        issues.append("HIGH: no policy specified")

    if "sp=" not in rec:
        issues.append("LOW: no subdomain policy (sp=) — subdomains spoofable")

    return {"status": "FOUND", "record": dmarc[0],
            "severity": "MEDIUM" if "p=none" in rec else "INFO",
            "issues": issues}


def check_dkim(domain: str) -> dict:
    selectors = ["default", "google", "selector1", "selector2",
                 "k1", "mail", "smtp", "dkim"]
    found = {}
    for s in selectors:
        records = query(f"{s}._domainkey.{domain}", "TXT")
        if records:
            found[s] = records[0][:200]
    return {
        "status": "FOUND" if found else "NOT_DETECTED",
        "selectors_found": list(found.keys()),
        "records": found,
    }


def check_mx(domain: str) -> dict:
    mx = query(domain, "MX")
    return {"status": "FOUND" if mx else "MISSING", "records": mx}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    print(f"[*] Email security check for: {args.domain}")

    results = {
        "domain": args.domain,
        "spf": check_spf(args.domain),
        "dmarc": check_dmarc(args.domain),
        "dkim": check_dkim(args.domain),
        "mx": check_mx(args.domain),
    }

    # ─── PRIORITIZE ───────────────────────────────────────────────────────────
    high_findings = []
    for check_name in ["spf", "dmarc"]:
        c = results[check_name]
        if c.get("severity") in ("HIGH", "CRITICAL"):
            high_findings.append(f"{check_name.upper()}: {c.get('issues')}")

    results["actionable_findings"] = high_findings

    summary = out / "email_security.json"
    summary.write_text(json.dumps(results, indent=2))

    print(f"[+] SPF   : {results['spf']['status']} — {results['spf'].get('issues', [])}")
    print(f"[+] DMARC : {results['dmarc']['status']} — {results['dmarc'].get('issues', [])}")
    print(f"[+] DKIM  : {results['dkim']['status']} ({len(results['dkim']['selectors_found'])} selectors)")
    print(f"[+] MX    : {len(results['mx']['records'])} records")
    if high_findings:
        print(f"[!] Actionable findings: {len(high_findings)}")
    print(f"[+] Saved to {summary}")


if __name__ == "__main__":
    main()
