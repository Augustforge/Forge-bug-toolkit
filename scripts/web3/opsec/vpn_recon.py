#!/usr/bin/env python3
"""
vpn_recon.py — Verify network identity for recon operations.

Checks current public IP. Warns if not behind VPN.
Use before any recon activity.

Usage:
  python3 vpn_recon.py --check
  python3 vpn_recon.py --check --required-country UK
"""

import argparse
import json
import urllib.request


def get_current_ip_info() -> dict:
    """Query a public IP API for current external IP info."""
    services = [
        "https://ipinfo.io/json",
        "https://ipapi.co/json/",
        "https://ifconfig.co/json",
    ]
    for url in services:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
            with urllib.request.urlopen(req, timeout=5) as r:
                return json.loads(r.read())
        except Exception:
            continue
    return {"error": "all IP services failed"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--check", action="store_true")
    p.add_argument("--required-country", help="Expected country code (warn if mismatch)")
    args = p.parse_args()

    info = get_current_ip_info()
    if "error" in info:
        print(f"ERROR: {info['error']}")
        return 1

    ip = info.get("ip", info.get("query", "?"))
    country = info.get("country", info.get("country_code", "?"))
    city = info.get("city", "?")
    isp = info.get("org", info.get("isp", "?"))

    print(f"Current external identity:")
    print(f"  IP:      {ip}")
    print(f"  Country: {country}")
    print(f"  City:    {city}")
    print(f"  ISP:     {isp}")

    # Warnings
    warnings = []
    if isp and any(home_isp in isp.lower() for home_isp in ("rostelecom", "comcast", "verizon", "spectrum", "deutsche telekom")):
        warnings.append("Home ISP detected — likely no VPN")
    if args.required_country and country != args.required_country.upper():
        warnings.append(f"Country mismatch: have {country}, expected {args.required_country}")

    if warnings:
        print("\n⚠️  WARNINGS:")
        for w in warnings:
            print(f"  - {w}")
        return 2
    else:
        print("\n✓ Identity looks isolated")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
