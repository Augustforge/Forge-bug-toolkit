#!/usr/bin/env python3
"""
dapp_clone_detector.py — Find dApp clones (dev/staging/preprod) of a production target.

A clone is identified by:
1. Same auth provider app ID (Privy/Magic/WC) in the bundle
2. Same JS bundle filename pattern + bundle-head SHA-256 hash
3. Same HTML <title> / brand markers
4. Same dApp banner string (console.log "Future DApp v3.11.15" pattern)

Clones often share trust with production via auth provider wildcard, so each
clone that ships the same dApp but lacks framing protection is a finding
candidate.

Usage:
    python3 dapp_clone_detector.py --primary https://oyster.synfutures.com/ \
        --subdomains sessions/$DOMAIN/crtsh.json \
        --auth-id clz2gl5r702phkqjy3zhlalh9 \
        --output sessions/$DOMAIN/clones.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Set


_PRIVY_RX = re.compile(r"\bcl[a-z0-9]{20,26}\b")
_WC_RX = re.compile(r"projectId\s*[:=]\s*['\"]([a-f0-9]{32})['\"]")
_BUNDLE_PATTERN_RX = re.compile(r"/(?:assets|static|_next/static)/([\w./-]+\.js)")
_TITLE_RX = re.compile(r"<title[^>]*>([^<]+)</title>", re.IGNORECASE)
# env-diff grep (FDE Plan 4, Task 3) — literal VITE_*/REACT_APP_*/NEXT_PUBLIC_* key/value pairs
# baked into the bundle by the build step.
_ENV_VAR_RX = re.compile(
    r"[\"']?\b((?:VITE|REACT_APP|NEXT_PUBLIC)_[A-Z0-9_]+)[\"']?\s*[:=]\s*[\"']([^\"'\\\n]{0,200})[\"']"
)


@dataclass
class CloneCandidate:
    host: str
    url: str
    is_clone: bool
    reasons: List[str]
    privy_app_id: Optional[str]
    wc_project_id: Optional[str]
    bundle_pattern: Optional[str]
    bundle_head_hash: Optional[str]
    title: Optional[str]
    severity_hint: str
    env_vars: Dict[str, str] = field(default_factory=dict)


@dataclass
class CloneReport:
    primary_url: str
    primary_privy_id: Optional[str]
    primary_wc_id: Optional[str]
    primary_bundle_hash: Optional[str]
    primary_bundle_pattern: Optional[str]
    primary_title: Optional[str]
    candidates: List[CloneCandidate] = field(default_factory=list)
    clones: List[str] = field(default_factory=list)
    # SET of clone hosts, ready to feed into asymmetry_scanner_dapp's --subdomains (JSON array is
    # already an accepted input format there). Mirrors `clones` under the name Task 3's brief asked
    # for; `clones` is kept unchanged for backward compatibility with existing consumers.
    clone_hosts: List[str] = field(default_factory=list)


def _grep_env_vars(text: str) -> Dict[str, str]:
    found: Dict[str, str] = {}
    for m in _ENV_VAR_RX.finditer(text):
        found.setdefault(m.group(1), m.group(2))
    return found


def _fetch(url: str, timeout: float = 8.0, max_bytes: int = 3_000_000) -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dapphunt-clone-detector/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(max_bytes)
            return raw.decode("utf-8", errors="replace")
    except Exception:
        return None


def _fingerprint_host(url: str) -> CloneCandidate:
    cand = CloneCandidate(
        host=urllib.parse.urlparse(url).netloc,
        url=url,
        is_clone=False,
        reasons=[],
        privy_app_id=None,
        wc_project_id=None,
        bundle_pattern=None,
        bundle_head_hash=None,
        title=None,
        severity_hint="low",
    )
    html = _fetch(url)
    if not html:
        cand.reasons.append("could not fetch")
        return cand

    # Title
    m = _TITLE_RX.search(html)
    if m:
        cand.title = m.group(1).strip()

    # Bundle URL pattern
    m = _BUNDLE_PATTERN_RX.search(html)
    if m:
        full = m.group(0)
        cand.bundle_pattern = re.sub(r"-[a-f0-9]{8,16}\.js", "-<hash>.js", full)
        # Fetch first 8KB of main bundle for signature
        parsed = urllib.parse.urlparse(url)
        bundle_url = f"{parsed.scheme}://{parsed.netloc}{full}"
        bundle = _fetch(bundle_url, max_bytes=5_000_000)
        if bundle:
            cand.bundle_head_hash = hashlib.sha256(bundle[:8192].encode("utf-8")).hexdigest()
            # Privy / WC IDs may live anywhere in bundle
            privy = _PRIVY_RX.search(bundle)
            if privy:
                cand.privy_app_id = privy.group(0)
            wc = _WC_RX.search(bundle)
            if wc:
                cand.wc_project_id = wc.group(1)
            cand.env_vars = _grep_env_vars(bundle)
    return cand


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


def detect_clones(primary_url: str, candidate_urls: List[str], expected_privy_id: Optional[str] = None) -> CloneReport:
    primary = _fingerprint_host(primary_url)

    report = CloneReport(
        primary_url=primary_url,
        primary_privy_id=primary.privy_app_id,
        primary_wc_id=primary.wc_project_id,
        primary_bundle_hash=primary.bundle_head_hash,
        primary_bundle_pattern=primary.bundle_pattern,
        primary_title=primary.title,
    )

    # Allow caller override (e.g. when expected ID is known from auth_provider_probe)
    if expected_privy_id and not report.primary_privy_id:
        report.primary_privy_id = expected_privy_id

    for url in candidate_urls:
        if urllib.parse.urlparse(url).netloc == urllib.parse.urlparse(primary_url).netloc:
            continue
        cand = _fingerprint_host(url)
        reasons: List[str] = []
        # Match by Privy app
        if report.primary_privy_id and cand.privy_app_id == report.primary_privy_id:
            reasons.append("shared_privy_app_id")
        # Match by WC project
        if report.primary_wc_id and cand.wc_project_id == report.primary_wc_id:
            reasons.append("shared_walletconnect_project_id")
        # Match by bundle pattern (suggests same build pipeline)
        if report.primary_bundle_pattern and cand.bundle_pattern == report.primary_bundle_pattern:
            reasons.append("matching_bundle_pattern")
        # Bundle-head hash equivalence (strongest signal)
        if report.primary_bundle_hash and cand.bundle_head_hash == report.primary_bundle_hash:
            reasons.append("identical_bundle_head_hash")
        # Title match
        if report.primary_title and cand.title and cand.title.strip().lower() == report.primary_title.strip().lower():
            reasons.append("matching_title")

        cand.reasons = reasons
        # Clone classification heuristic: ≥1 strong signal (privy/wc/bundle_hash) OR ≥2 weak signals
        strong = {"shared_privy_app_id", "shared_walletconnect_project_id", "identical_bundle_head_hash"}
        weak = {"matching_bundle_pattern", "matching_title"}
        n_strong = len(strong & set(reasons))
        n_weak = len(weak & set(reasons))
        if n_strong >= 1 or n_weak >= 2:
            cand.is_clone = True
            cand.severity_hint = "high" if "shared_privy_app_id" in reasons else "medium"
            report.clones.append(cand.host)
        report.candidates.append(cand)

    report.clone_hosts = list(report.clones)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--primary", required=True)
    parser.add_argument("--subdomains", type=Path, help="JSON list of subdomains to test as candidate clones")
    parser.add_argument("--auth-id", help="Expected Privy / auth provider app ID (optional override)")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    subdomains = _load_subdomains(args.subdomains) if args.subdomains else []
    candidate_urls = [_normalize_url(s) for s in subdomains]
    report = detect_clones(args.primary, candidate_urls, expected_privy_id=args.auth_id)

    payload = json.dumps(asdict(report), ensure_ascii=False, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")

    if not args.quiet:
        print(f"Primary: {report.primary_url}")
        print(f"  Privy app: {report.primary_privy_id}")
        print(f"  Bundle hash (head): {report.primary_bundle_hash and report.primary_bundle_hash[:16]+'…'}")
        print(f"  Title: {report.primary_title}")
        print(f"\nCandidates examined: {len(report.candidates)}")
        for c in report.candidates:
            marker = "CLONE" if c.is_clone else "no   "
            reasons = ",".join(c.reasons) if c.reasons else "(none)"
            print(f"  {marker}  [{c.severity_hint:6}]  {c.host:50s}  reasons={reasons}")
        if report.clones:
            print(f"\nClones detected: {len(report.clones)}")
            for h in report.clones:
                print(f"  • {h}")
    return 0 if not report.clones else 1


if __name__ == "__main__":
    sys.exit(main())
