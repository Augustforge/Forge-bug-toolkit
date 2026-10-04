#!/usr/bin/env python3
"""
platform_detector.py — Identify which bug bounty platform hosts a given target.

Detection strategy (in order of confidence):
1. Direct match against platform-owned domains (hackenproof.com, etc.)
2. Local cache of known program → platform mapping
   (sessions/_proactive/platforms_cache.json)
3. Lightweight curl probe of /.well-known/security.txt + meta tags for contact: links

Usage:
    python3 platform_detector.py --target https://oyster.synfutures.com/
    python3 platform_detector.py --target https://oyster.synfutures.com/ --output platform.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional


SUPPORTED_PLATFORMS = ["hackenproof", "immunefi", "cantina", "hackerone", "bugcrowd", "yeswehack", "intigriti"]


@dataclass
class PlatformVerdict:
    target: str
    platform: Optional[str]
    confidence: str            # "direct" / "cached" / "security_txt" / "unknown"
    program_url: Optional[str]
    notes: List[str]
    kyc_likely: Optional[bool]
    reputation_likely_required: Optional[bool]


# ── Domain heuristics ──
_PLATFORM_DOMAINS = {
    "hackenproof": [r"hackenproof\.com", r"dashboard\.hackenproof\.com"],
    "immunefi": [r"immunefi\.com", r"bugs\.immunefi\.com"],
    "cantina": [r"cantina\.xyz"],
    "hackerone": [r"hackerone\.com", r"\bh1\.com\b"],
    "bugcrowd": [r"bugcrowd\.com"],
    "yeswehack": [r"yeswehack\.com"],
    "intigriti": [r"intigriti\.com"],
}

_PLATFORM_COMPILED = {
    name: [re.compile(rx, re.IGNORECASE) for rx in patterns]
    for name, patterns in _PLATFORM_DOMAINS.items()
}


def _direct_match(target: str) -> Optional[str]:
    """Return platform name if target URL or host belongs to a platform itself."""
    for name, patterns in _PLATFORM_COMPILED.items():
        if any(p.search(target) for p in patterns):
            return name
    return None


def _load_cache(cache_path: Path) -> Dict[str, Dict[str, str]]:
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache_path: Path, cache: Dict[str, Dict[str, str]]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _fetch_security_txt(target: str, timeout: float = 5.0) -> Optional[str]:
    """Try /.well-known/security.txt → /security.txt. Return text or None."""
    parsed = urllib.parse.urlparse(target)
    base = f"{parsed.scheme}://{parsed.netloc}"
    candidates = [f"{base}/.well-known/security.txt", f"{base}/security.txt"]
    for url in candidates:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "dapphunt-platform-detector/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    raw = resp.read(8192)
                    return raw.decode("utf-8", errors="replace")
        except Exception:
            continue
    return None


def _platform_from_security_txt(text: str) -> Optional[str]:
    """Look for platform-owned URLs inside security.txt Contact: lines."""
    contact_lines = [ln for ln in text.splitlines() if ln.strip().lower().startswith(("contact:", "policy:", "acknowledgments:"))]
    for line in contact_lines:
        for name, patterns in _PLATFORM_COMPILED.items():
            if any(p.search(line) for p in patterns):
                return name
    return None


# ── KYC / reputation hints per platform (rough heuristics) ──
_PLATFORM_KYC = {
    "hackenproof": True,         # Most programs require KYC + reputation gate
    "immunefi": True,            # KYC required for High/Critical payouts
    "cantina": False,            # Cantina competitions skip KYC; bounties may require
    "hackerone": False,          # Per-program varies
    "bugcrowd": False,           # Per-program varies
    "yeswehack": False,
    "intigriti": False,
}


def detect(target: str, cache_path: Optional[Path] = None) -> PlatformVerdict:
    notes: List[str] = []
    verdict = PlatformVerdict(
        target=target,
        platform=None,
        confidence="unknown",
        program_url=None,
        notes=notes,
        kyc_likely=None,
        reputation_likely_required=None,
    )

    # Step 1: direct match
    direct = _direct_match(target)
    if direct:
        verdict.platform = direct
        verdict.confidence = "direct"
        verdict.program_url = target
        notes.append(f"Direct domain match against {direct} pattern.")
    else:
        # Step 2: cache
        if cache_path:
            cache = _load_cache(cache_path)
            parsed = urllib.parse.urlparse(target)
            netloc = parsed.netloc.lower()
            cache_hit = cache.get(netloc) or cache.get(target.rstrip("/"))
            if cache_hit and cache_hit.get("platform") in SUPPORTED_PLATFORMS:
                verdict.platform = cache_hit["platform"]
                verdict.confidence = "cached"
                verdict.program_url = cache_hit.get("program_url")
                notes.append(f"Cache hit: {netloc} → {verdict.platform}.")

        # Step 3: security.txt probe
        if not verdict.platform:
            sec_txt = _fetch_security_txt(target)
            if sec_txt:
                p = _platform_from_security_txt(sec_txt)
                if p:
                    verdict.platform = p
                    verdict.confidence = "security_txt"
                    notes.append(f"security.txt contact references {p}.")
                else:
                    notes.append("security.txt present but no platform reference detected.")
            else:
                notes.append("No security.txt found; platform unknown.")

    # Annotate KYC/reputation hints
    if verdict.platform:
        verdict.kyc_likely = _PLATFORM_KYC.get(verdict.platform)
        verdict.reputation_likely_required = verdict.platform in ("hackenproof", "immunefi")
        notes.append(
            f"Heuristic: kyc_likely={verdict.kyc_likely}, reputation_likely_required={verdict.reputation_likely_required}"
        )

    return verdict


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--target", required=True, help="Target URL or domain.")
    parser.add_argument("--output", type=Path, help="Write JSON to this file.")
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path("sessions/_proactive/platforms_cache.json"),
        help="Path to local program→platform mapping cache.",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    verdict = detect(args.target, cache_path=args.cache)
    payload = json.dumps(asdict(verdict), ensure_ascii=False, indent=2)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")

    if not args.quiet:
        print(payload)

    return 0 if verdict.platform else 1


if __name__ == "__main__":
    sys.exit(main())
