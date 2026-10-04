#!/usr/bin/env python3
"""
iframe_trust_check.py — Mass-HEAD every subdomain, build a trust matrix.

For each host on the list:
- Issue HEAD/GET request
- Capture security headers (X-Frame-Options, CSP frame-ancestors, STS, etc.)
- Determine framing posture (DENY / SAMEORIGIN / wildcard / missing)

Then compare each host against the production target and against the auth
provider's frame-ancestors policy. Flag mismatches.

Usage:
    python3 iframe_trust_check.py --primary https://oyster.synfutures.com/ \
        --subdomains sessions/$DOMAIN/crtsh.json \
        --output sessions/$DOMAIN/iframe_trust_matrix.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Set


SECURITY_HEADERS = [
    "x-frame-options",
    "content-security-policy",
    "strict-transport-security",
    "referrer-policy",
    "x-content-type-options",
    "permissions-policy",
]


@dataclass
class HostHeaderProfile:
    host: str
    url: str
    status_code: Optional[int]
    x_frame_options: Optional[str]
    csp_frame_ancestors: Optional[str]
    hsts: Optional[str]
    referrer_policy: Optional[str]
    content_type_options: Optional[str]
    permissions_policy: Optional[str]
    framing_posture: str       # "deny" | "sameorigin" | "wildcard" | "missing" | "explicit_list" | "error"
    raw_headers: Dict[str, str] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


@dataclass
class IframeTrustReport:
    primary_url: str
    primary_profile: Optional[HostHeaderProfile]
    profiles: List[HostHeaderProfile] = field(default_factory=list)
    asymmetries: List[str] = field(default_factory=list)
    findings: List[str] = field(default_factory=list)


def _fetch_head(url: str, timeout: float = 6.0) -> tuple[Optional[int], Dict[str, str]]:
    """Try HEAD first; if 405/blocked, fall back to GET reading only headers."""
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method, headers={"User-Agent": "dapphunt-iframe-trust/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if method == "GET":
                    resp.read(0)  # don't actually pull body
                return resp.status, {k.lower(): v for k, v in resp.headers.items()}
        except urllib.error.HTTPError as e:
            if e.code in (404, 410, 502, 503, 504):
                return e.code, {}
            # 405 = HEAD not allowed → try GET
            continue
        except Exception:
            continue
    return None, {}


def _extract_frame_ancestors(csp: Optional[str]) -> Optional[str]:
    if not csp:
        return None
    for directive in csp.split(";"):
        d = directive.strip()
        if d.lower().startswith("frame-ancestors"):
            parts = d.split(None, 1)
            return parts[1] if len(parts) > 1 else ""
    return None


def _framing_posture(xfo: Optional[str], frame_ancestors: Optional[str]) -> str:
    # Strongest signal: explicit DENY in either
    if xfo and xfo.upper().strip() == "DENY":
        return "deny"
    if frame_ancestors and "'none'" in frame_ancestors.lower():
        return "deny"
    if xfo and "SAMEORIGIN" in xfo.upper():
        return "sameorigin"
    if frame_ancestors and "'self'" in frame_ancestors.lower() and "*" not in frame_ancestors:
        return "sameorigin"
    # Wildcard in frame-ancestors
    if frame_ancestors and re.search(r"\*\.[a-z0-9-]+(?:\.[a-z0-9-]+)+", frame_ancestors, re.IGNORECASE):
        return "wildcard"
    if frame_ancestors and ("*" in frame_ancestors or "https:" in frame_ancestors.lower()):
        return "wildcard"
    if frame_ancestors:
        return "explicit_list"
    if xfo:
        return "explicit_list"
    return "missing"


def profile_host(url: str) -> HostHeaderProfile:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc
    status, headers = _fetch_head(url)
    fa = _extract_frame_ancestors(headers.get("content-security-policy"))

    profile = HostHeaderProfile(
        host=host,
        url=url,
        status_code=status,
        x_frame_options=headers.get("x-frame-options"),
        csp_frame_ancestors=fa,
        hsts=headers.get("strict-transport-security"),
        referrer_policy=headers.get("referrer-policy"),
        content_type_options=headers.get("x-content-type-options"),
        permissions_policy=headers.get("permissions-policy"),
        framing_posture=_framing_posture(headers.get("x-frame-options"), fa),
        raw_headers=headers,
    )

    if status is None:
        profile.framing_posture = "error"
        profile.notes.append("Could not fetch host (timeout / DNS / refused).")

    return profile


def _load_subdomains(path: Path) -> List[str]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if isinstance(data, list):
        return [str(x) for x in data]
    if isinstance(data, dict):
        for key in ("subdomains", "hosts", "results"):
            v = data.get(key)
            if isinstance(v, list):
                return [str(x) for x in v]
    return []


def _normalize_url(s: str) -> str:
    if s.startswith("http://") or s.startswith("https://"):
        return s
    return f"https://{s}"


def detect_asymmetries(primary: Optional[HostHeaderProfile], profiles: List[HostHeaderProfile]) -> tuple[List[str], List[str]]:
    asymmetries: List[str] = []
    findings: List[str] = []

    if not primary:
        return asymmetries, findings

    primary_strong = primary.framing_posture in ("deny", "sameorigin")
    for p in profiles:
        if p.host == primary.host:
            continue
        if p.status_code != 200:
            continue
        if primary_strong and p.framing_posture in ("missing", "wildcard"):
            asymmetries.append(
                f"Primary `{primary.host}` is {primary.framing_posture} but sibling `{p.host}` is "
                f"{p.framing_posture}. Iframe-rendering primitive likely on `{p.host}`."
            )
            findings.append(
                f"finding_candidate: sibling `{p.host}` lacks framing protection while primary is hardened — "
                f"verify shared auth provider, then this is a clickjacking + phishing chain on `{primary.host}`'s users."
            )

    # Always flag any wildcard frame-ancestors
    for p in profiles:
        if p.framing_posture == "wildcard":
            findings.append(
                f"finding_candidate: host `{p.host}` declares wildcard in CSP frame-ancestors → may be "
                f"frameable from attacker-controlled subdomain under that wildcard."
            )

    # Flag missing HSTS on hosts that ship dApp content
    for p in profiles:
        if p.status_code == 200 and not p.hsts:
            findings.append(f"finding_candidate: host `{p.host}` is missing Strict-Transport-Security (downgrade risk).")

    return asymmetries, findings


def scan(primary_url: str, subdomains: List[str]) -> IframeTrustReport:
    primary_profile = profile_host(primary_url)
    hosts: Set[str] = set()
    hosts.add(primary_url)
    for s in subdomains:
        hosts.add(_normalize_url(s))

    profiles: List[HostHeaderProfile] = []
    for url in sorted(hosts):
        p = profile_host(url)
        profiles.append(p)

    asyms, findings = detect_asymmetries(primary_profile, profiles)
    return IframeTrustReport(
        primary_url=primary_url,
        primary_profile=primary_profile,
        profiles=profiles,
        asymmetries=asyms,
        findings=findings,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--primary", required=True, help="Primary dApp URL")
    parser.add_argument("--subdomains", type=Path, help="JSON file of subdomains")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    subdomains = _load_subdomains(args.subdomains) if args.subdomains else []
    report = scan(args.primary, subdomains)

    payload = json.dumps(asdict(report), ensure_ascii=False, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")

    if not args.quiet:
        print(f"Primary: {report.primary_url}")
        if report.primary_profile:
            print(f"  posture: {report.primary_profile.framing_posture}  xfo={report.primary_profile.x_frame_options}  csp.frame-ancestors={report.primary_profile.csp_frame_ancestors}")
        print(f"\nProfiles ({len(report.profiles)}):")
        for p in report.profiles:
            if p.host == urllib.parse.urlparse(report.primary_url).netloc:
                continue
            print(f"  {p.host:50s}  status={p.status_code}  posture={p.framing_posture}")
        if report.asymmetries:
            print(f"\nAsymmetries ({len(report.asymmetries)}):")
            for a in report.asymmetries:
                print(f"  ⚠ {a}")
        if report.findings:
            print(f"\nFinding candidates ({len(report.findings)}):")
            for f in report.findings:
                print(f"  • {f}")
    return 0 if not report.findings else 1


if __name__ == "__main__":
    sys.exit(main())
