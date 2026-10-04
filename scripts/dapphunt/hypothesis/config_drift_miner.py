#!/usr/bin/env python3
"""
config_drift_miner.py — Find drift between auth-provider config, frontend assumptions, and actual code.

Three drift classes:
1. **Auth provider config** declares X (e.g. allowed_domains=[A,B,C]),
   **frontend bundle** assumes Y (e.g. window.location.hostname is in some smaller set).
2. **Frontend code** says "X allowed", **server** allows superset (e.g. UI dropdown limits chains to [1, 137],
   contract supports [1, 137, 10, 42161]).
3. **Documentation / comments** claim Z, **runtime config** behaves differently.
   (Mezo/Alchemix class of bug — README claims fix, reality says no fix.)

Heuristics implemented here are conservative — they surface candidates, hunter validates.

Inputs:
- auth_provider_config.json (from auth_provider_probe)
- bundle paths (optional; for JS string-literal scan)
- target URL (for live runtime fetch of /robots.txt, /humans.txt, /security.txt for doc claims)

Usage:
    python3 config_drift_miner.py --target https://oyster.synfutures.com/ \
        --auth-config sessions/$DOMAIN/auth_provider_config.json \
        --bundle sessions/$DOMAIN/bundle-main.js \
        --output sessions/$DOMAIN/hypothesis/config_drift.json
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


@dataclass
class DriftCandidate:
    drift_id: str
    drift_class: str        # "auth_vs_frontend" / "frontend_vs_contract" / "docs_vs_runtime"
    severity_hint: str
    description: str
    evidence: Dict[str, str] = field(default_factory=dict)


@dataclass
class ConfigDriftReport:
    target: str
    candidates: List[DriftCandidate] = field(default_factory=list)
    hypotheses: List[str] = field(default_factory=list)


_HARDCODED_HOST_RX = re.compile(r"['\"](https?://(?!\$\{)[\w.-]+(?:\.[\w-]+)+(?:/[^'\"\s]*)?)['\"]")
_CHAIN_ID_RX = re.compile(r"\bchainId\s*[:=]\s*(\d+)\b")
_BASEURL_RX = re.compile(r"\b(?:baseURL|apiBase|API_URL|RPC_URL|API_ENDPOINT)\s*[:=]\s*['\"]([^'\"]+)['\"]")
_TODO_COMMENT_RX = re.compile(r"(?:TODO|FIXME|XXX|HACK|TEMPORARY)[\s:]+([^\n*/]{10,200})", re.IGNORECASE)


def _load_json(path: Path) -> Optional[dict]:
    if not path or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _flatten_allowed_domains(auth_cfg: dict) -> Set[str]:
    """Walk auth provider config tree, collect every 'allowed_domains' entry."""
    found: Set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("allowed_domains", "allowedDomains", "trustedDomains", "frame_ancestors", "allowed_origins"):
                    if isinstance(v, list):
                        for entry in v:
                            if isinstance(entry, str):
                                found.add(entry)
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(auth_cfg)
    return found


def _extract_bundle_hosts(bundle_text: str) -> Set[str]:
    """Collect string-literal host URLs that look like API endpoints in the bundle."""
    found: Set[str] = set()
    for m in _HARDCODED_HOST_RX.finditer(bundle_text):
        url = m.group(1)
        parsed = urllib.parse.urlparse(url)
        if parsed.netloc and "." in parsed.netloc:
            # Skip image/asset CDNs that aren't security-relevant
            if any(parsed.netloc.endswith(s) for s in ("googletagmanager.com", "googleapis.com", "fonts.gstatic.com")):
                continue
            found.add(parsed.netloc)
    # Also explicit baseURL fields
    for m in _BASEURL_RX.finditer(bundle_text):
        url = m.group(1)
        parsed = urllib.parse.urlparse(url)
        if parsed.netloc:
            found.add(parsed.netloc)
    return found


def _extract_bundle_chain_ids(bundle_text: str) -> Set[int]:
    """Find hardcoded chainId numbers that look like EVM chain IDs."""
    found: Set[int] = set()
    for m in _CHAIN_ID_RX.finditer(bundle_text):
        try:
            cid = int(m.group(1))
            # Filter to plausible EVM chain IDs (1..1e7 range catches all real chains)
            if 1 <= cid <= 10_000_000:
                found.add(cid)
        except ValueError:
            continue
    return found


def _fetch(url: str, timeout: float = 5.0) -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dapphunt-config-drift/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return resp.read(200_000).decode("utf-8", errors="replace")
    except Exception:
        pass
    return None


def _scan_docs_for_security_claims(target: str) -> List[tuple[str, str]]:
    """Look for security claims in /security.txt, /humans.txt, /robots.txt."""
    parsed = urllib.parse.urlparse(target)
    base = f"{parsed.scheme}://{parsed.netloc}"
    claims: List[tuple[str, str]] = []
    for path in ("/.well-known/security.txt", "/security.txt", "/humans.txt"):
        text = _fetch(f"{base}{path}")
        if not text:
            continue
        for kw in ("X-Frame-Options", "frame-ancestors", "CSP", "Content-Security-Policy", "no-iframe", "clickjack"):
            if kw.lower() in text.lower():
                claims.append((path, kw))
    return claims


def detect_drift(
    target: str,
    auth_config: Optional[dict],
    bundles: List[str],
) -> ConfigDriftReport:
    report = ConfigDriftReport(target=target)
    counter = 1

    primary_host = urllib.parse.urlparse(target).netloc

    # ── 1. Auth provider allowed_domains vs frontend hardcoded hosts ──
    auth_allowed: Set[str] = set()
    if auth_config:
        auth_allowed = _flatten_allowed_domains(auth_config)

    bundle_hosts: Set[str] = set()
    bundle_chain_ids: Set[int] = set()
    todo_comments: List[str] = []
    for bundle in bundles:
        bundle_hosts |= _extract_bundle_hosts(bundle)
        bundle_chain_ids |= _extract_bundle_chain_ids(bundle)
        for m in _TODO_COMMENT_RX.finditer(bundle):
            todo_comments.append(m.group(0).strip())

    # Hosts allowed by auth but NEVER referenced by frontend → orphan trust expansion
    # (e.g. wildcard *.iftl.info allows hosts that the production frontend never calls,
    #  but attacker could leverage them as iframe parents)
    if auth_allowed:
        normalize = lambda s: s.replace("https://", "").replace("http://", "").rstrip("/").lower()
        auth_norm = {normalize(d) for d in auth_allowed}
        wildcard_entries = {d for d in auth_norm if d.startswith("*.")}
        explicit_entries = auth_norm - wildcard_entries

        # Wildcards that the frontend itself doesn't reference
        for w in wildcard_entries:
            base_domain = w[2:]  # strip "*."
            # Find any bundle host that lands under this wildcard but isn't an explicit allow entry
            matching_bundle_hosts = {h for h in bundle_hosts if h.lower().endswith("." + base_domain)}
            unaccounted = matching_bundle_hosts - {e for e in explicit_entries}
            if matching_bundle_hosts and not any(e == base_domain or e.endswith("." + base_domain) for e in explicit_entries):
                report.candidates.append(DriftCandidate(
                    drift_id=f"D{counter:03d}",
                    drift_class="auth_vs_frontend",
                    severity_hint="high",
                    description=(
                        f"Auth provider permits wildcard `*.{base_domain}` but explicit allowlist does not "
                        f"enumerate matching subdomains. Any unaccounted-for subdomain inherits production "
                        f"trust automatically."
                    ),
                    evidence={
                        "wildcard": f"*.{base_domain}",
                        "bundle_references_under_wildcard": ",".join(sorted(matching_bundle_hosts)),
                        "explicit_allow_entries": ",".join(sorted(explicit_entries)),
                    },
                ))
                counter += 1
            elif wildcard_entries and not matching_bundle_hosts:
                # Wildcard with no bundle reference at all — pure trust expansion
                report.candidates.append(DriftCandidate(
                    drift_id=f"D{counter:03d}",
                    drift_class="auth_vs_frontend",
                    severity_hint="medium",
                    description=(
                        f"Auth provider permits wildcard `*.{base_domain}` but frontend bundle does not "
                        f"reference this domain at all. Why is the wildcard granted? Likely overscoped trust."
                    ),
                    evidence={"wildcard": f"*.{base_domain}"},
                ))
                counter += 1

    # ── 2. Multi-chain support drift (hardcoded chain ID vs deploy reality) ──
    if bundle_chain_ids:
        chain_id_list = sorted(bundle_chain_ids)
        if 1 in chain_id_list and len(chain_id_list) == 1:
            # Hardcoded mainnet only — but if dApp deploys on L2 too, EIP-712 will sign with wrong chainId
            report.candidates.append(DriftCandidate(
                drift_id=f"D{counter:03d}",
                drift_class="frontend_vs_contract",
                severity_hint="medium",
                description=(
                    "Frontend bundle hardcodes chainId=1 (Ethereum mainnet) but if the dApp is deployed "
                    "on L2s (Base / Arbitrum / Optimism), an EIP-712 signature with chainId=1 may be "
                    "replayable across chains. Verify EIP-712 domain.chainId is dynamic per network."
                ),
                evidence={"hardcoded_chain_ids": ",".join(str(c) for c in chain_id_list)},
            ))
            counter += 1

    # ── 3. TODO / FIXME / TEMPORARY comments in production bundle ──
    suspicious_todos = [t for t in todo_comments if any(kw in t.lower() for kw in ("security", "auth", "trust", "hardcode", "remove", "tmp", "temporary", "before launch", "before prod"))]
    if suspicious_todos:
        report.candidates.append(DriftCandidate(
            drift_id=f"D{counter:03d}",
            drift_class="docs_vs_runtime",
            severity_hint="low",
            description=(
                f"Production bundle contains {len(suspicious_todos)} suspicious TODO/FIXME/HACK comment(s) "
                f"hinting at unfinished security work. Review each — sometimes points to deferred mitigations."
            ),
            evidence={"sample_comments": " | ".join(suspicious_todos[:3])},
        ))
        counter += 1

    # ── 4. Documentation claims vs runtime (security.txt mentions hardening that headers don't reflect) ──
    doc_claims = _scan_docs_for_security_claims(target)
    if doc_claims:
        # Quick header fetch to check
        try:
            req = urllib.request.Request(target, headers={"User-Agent": "dapphunt/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                hdrs = {k.lower(): v for k, v in resp.headers.items()}
        except Exception:
            hdrs = {}

        # If security.txt mentions X-Frame-Options but header is absent → drift
        if any("frame" in kw.lower() for _, kw in doc_claims):
            if "x-frame-options" not in hdrs and "frame-ancestors" not in hdrs.get("content-security-policy", "").lower():
                report.candidates.append(DriftCandidate(
                    drift_id=f"D{counter:03d}",
                    drift_class="docs_vs_runtime",
                    severity_hint="medium",
                    description=(
                        "Documentation references X-Frame-Options or frame-ancestors hardening, but the "
                        "production response is missing both. Claim does not match reality."
                    ),
                    evidence={
                        "doc_references": "; ".join(f"{p}:{kw}" for p, kw in doc_claims),
                        "actual_headers_relevant": str({k: v for k, v in hdrs.items() if "frame" in k or "csp" in k or "content-security" in k}),
                    },
                ))
                counter += 1

    report.hypotheses = [
        f"H[{c.drift_id}]: {c.description}" for c in report.candidates
    ]
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--target", required=True)
    parser.add_argument("--auth-config", type=Path, help="auth_provider_probe output JSON")
    parser.add_argument("--bundle", action="append", type=Path, default=[], help="Bundle file (repeatable)")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    auth_config = _load_json(args.auth_config) if args.auth_config else None
    bundles: List[str] = []
    for bp in args.bundle:
        if bp.exists():
            try:
                bundles.append(bp.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                continue

    report = detect_drift(args.target, auth_config, bundles)
    payload = json.dumps(asdict(report), ensure_ascii=False, indent=2)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")

    if not args.quiet:
        print(f"Target: {report.target}")
        print(f"Drift candidates: {len(report.candidates)}")
        for c in report.candidates:
            print(f"  [{c.severity_hint.upper():6}] {c.drift_id}  class={c.drift_class}")
            print(f"           {c.description}")
    return 0 if not report.candidates else 1


if __name__ == "__main__":
    sys.exit(main())
