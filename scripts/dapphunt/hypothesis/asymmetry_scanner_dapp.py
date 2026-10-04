#!/usr/bin/env python3
"""
asymmetry_scanner_dapp.py — Find dev/staging/prod clone asymmetries.

The most common high-severity dApp pattern (SynFutures 2026-05-20 finding):
production target is hardened, but a development clone serves the SAME bundle
without protection. Auth provider trusts both via wildcard, so attacker frames
the dev clone and rides the production trust chain.

Inputs:
- A primary target URL
- A list of subdomains (from crtsh_enum output)

For each subdomain alive on HTTP(S), we collect:
- Response headers (security headers presence)
- Top-of-HTML signature (looking for telltale "Future DApp v…" style banners)
- Hash of main JS bundle filename pattern
- Detected auth provider IDs

Then we surface ASYMMETRIES: subdomains that share bundle hash with production
but lack security headers; subdomains that share the same Privy app ID but live
on a different (less-hardened) host.

Cross-program mode: --cross-program flag scans across a candidate list to find
shared auth providers / bundle hashes across different programs (Phase 12 use).

Usage:
    python3 asymmetry_scanner_dapp.py --target https://oyster.synfutures.com/ \
        --subdomains sessions/$DOMAIN/crtsh.json \
        --output sessions/$DOMAIN/hypothesis/asymmetry.json

    python3 asymmetry_scanner_dapp.py --cross-program \
        --root-cause auth_provider_wildcard \
        --candidate-list sessions/_proactive/dapp_programs.json
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


SECURITY_HEADERS = {
    "x-frame-options",
    "content-security-policy",
    "strict-transport-security",
    "referrer-policy",
    "x-content-type-options",
    "permissions-policy",
}


@dataclass
class HostFingerprint:
    host: str
    url: str
    status_code: Optional[int]
    security_headers_present: List[str]
    security_headers_missing: List[str]
    bundle_url_pattern: Optional[str]      # e.g. "/assets/index-<hash>.js"
    bundle_signature: Optional[str]        # SHA-256 of bundle text head (8KB)
    privy_app_id: Optional[str]
    walletconnect_project_id: Optional[str]
    react_dapp_banner: bool
    notes: List[str] = field(default_factory=list)
    # Cross-Clone Differential axes (FDE Plan 4, Task 3) — populated best-effort in
    # fingerprint_host() from html+bundle text, or injected directly by a caller/fixture.
    raw_headers: Dict[str, str] = field(default_factory=dict)
    env_vars: Dict[str, str] = field(default_factory=dict)          # VITE_*/REACT_APP_*/NEXT_PUBLIC_* literals
    chain_id: Optional[str] = None
    eip712_domain: Optional[str] = None                              # EIP-712 verifyingContract address
    # path -> HTTP status. NOT populated by fingerprint_host() (would be active probing, out of
    # scope for a read+compare diff) — set by caller/fixture when authz data is available.
    api_probes: Dict[str, int] = field(default_factory=dict)


@dataclass
class CloneDiffRow:
    """One row of the Cross-Clone Differential table (clone_diff.md)."""
    axis: str            # env-diff | CSP/headers | API-authz | chain-deploy-diff
    prod: str
    clone_host: str
    delta: str
    diff_class: str


@dataclass
class AsymmetryFinding:
    finding_id: str
    description: str
    severity_hint: str
    hosts_involved: List[str]
    evidence: Dict[str, str] = field(default_factory=dict)


@dataclass
class AsymmetryReport:
    target: str
    primary_host: str
    hosts_scanned: List[HostFingerprint] = field(default_factory=list)
    asymmetries: List[AsymmetryFinding] = field(default_factory=list)
    hypotheses: List[str] = field(default_factory=list)
    clone_diff: List[CloneDiffRow] = field(default_factory=list)


_PRIVY_ID_RX = re.compile(r"clz[a-z0-9]{18,24}")
_WC_ID_RX = re.compile(r"projectId\s*[:=]\s*['\"]([a-f0-9]{32})['\"]")
_BUNDLE_URL_RX = re.compile(r"/(assets|static|_next/static)/([\w./-]+\.js)")
_ENV_VAR_RX = re.compile(
    r"[\"']?\b((?:VITE|REACT_APP|NEXT_PUBLIC)_[A-Z0-9_]+)[\"']?\s*[:=]\s*[\"']([^\"'\\\n]{0,200})[\"']"
)
_CHAIN_ID_RX = re.compile(r"\bchainId[\"']?\s*[:=]\s*[\"']?(0x[0-9a-fA-F]+|\d{1,10})\b")
_EIP712_VERIFYING_CONTRACT_RX = re.compile(r"verifyingContract[\"']?\s*[:=]\s*[\"'](0x[0-9a-fA-F]{40})[\"']")
_FRAME_ANCESTORS_RX = re.compile(r"frame-ancestors\s+([^;]+)", re.IGNORECASE)


def _fetch(url: str, timeout: float = 6.0) -> tuple[Optional[str], Dict[str, str], Optional[int]]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dapphunt-asymmetry/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(500_000)
            text = raw.decode("utf-8", errors="replace")
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return text, headers, resp.status
    except Exception:
        return None, {}, None


def _normalize_host(s: str) -> str:
    """Accept full URL or bare host; return scheme://host."""
    if s.startswith("http://") or s.startswith("https://"):
        parsed = urllib.parse.urlparse(s)
        return f"{parsed.scheme}://{parsed.netloc}"
    return f"https://{s}"


def _extract_bundle_pattern(html: str) -> Optional[str]:
    m = _BUNDLE_URL_RX.search(html)
    if not m:
        return None
    # Normalize hash → <hash>
    full = m.group(0)
    return re.sub(r"-[a-f0-9]{8,16}\.js", "-<hash>.js", full)


def _extract_bundle_signature(html: str, base: str) -> Optional[str]:
    """Fetch first 8KB of main bundle and return its sha256 hex."""
    m = _BUNDLE_URL_RX.search(html)
    if not m:
        return None
    bundle_path = m.group(0)
    full_url = urllib.parse.urljoin(base + "/", bundle_path.lstrip("/"))
    text, _, _ = _fetch(full_url)
    if not text:
        return None
    return hashlib.sha256(text[:8192].encode("utf-8")).hexdigest()


def _fetch_bundle_text(html: str, base: str) -> Optional[str]:
    """Fetch full text of the main JS bundle (separate fetch from
    _extract_bundle_signature's own — used for env/chainId/EIP-712 grep)."""
    m = _BUNDLE_URL_RX.search(html)
    if not m:
        return None
    bundle_path = m.group(0)
    full_url = urllib.parse.urljoin(base + "/", bundle_path.lstrip("/"))
    text, _, _ = _fetch(full_url)
    return text


def _grep_env_vars(text: str) -> Dict[str, str]:
    """Collect VITE_*/REACT_APP_*/NEXT_PUBLIC_* literal key/value pairs from html+bundle text."""
    found: Dict[str, str] = {}
    for m in _ENV_VAR_RX.finditer(text):
        found.setdefault(m.group(1), m.group(2))
    return found


def _grep_chain_id(text: str) -> Optional[str]:
    m = _CHAIN_ID_RX.search(text)
    return m.group(1) if m else None


def _grep_eip712_domain(text: str) -> Optional[str]:
    m = _EIP712_VERIFYING_CONTRACT_RX.search(text)
    return m.group(1) if m else None


def _extract_frame_ancestors(csp_header_value: Optional[str]) -> Optional[str]:
    """Pull the frame-ancestors directive value out of a raw CSP header string."""
    if not csp_header_value:
        return None
    m = _FRAME_ANCESTORS_RX.search(csp_header_value)
    return m.group(1).strip() if m else None


def fingerprint_host(url: str) -> HostFingerprint:
    fp = HostFingerprint(
        host=urllib.parse.urlparse(url).netloc,
        url=url,
        status_code=None,
        security_headers_present=[],
        security_headers_missing=[],
        bundle_url_pattern=None,
        bundle_signature=None,
        privy_app_id=None,
        walletconnect_project_id=None,
        react_dapp_banner=False,
    )
    html, headers, status = _fetch(url)
    fp.status_code = status
    fp.raw_headers = headers
    if not html:
        fp.notes.append(f"No response from {url}")
        return fp

    fp.security_headers_present = sorted(h for h in SECURITY_HEADERS if h in headers)
    fp.security_headers_missing = sorted(SECURITY_HEADERS - set(fp.security_headers_present))
    fp.bundle_url_pattern = _extract_bundle_pattern(html)
    fp.bundle_signature = _extract_bundle_signature(html, url.rstrip("/"))

    # Cross-Clone Differential axes: env-diff / chain-deploy-diff (grep html + bundle text)
    bundle_text = _fetch_bundle_text(html, url.rstrip("/"))
    grep_source = html + (bundle_text or "")
    fp.env_vars = _grep_env_vars(grep_source)
    fp.chain_id = _grep_chain_id(grep_source)
    fp.eip712_domain = _grep_eip712_domain(grep_source)

    pid = _PRIVY_ID_RX.search(html)
    if pid:
        fp.privy_app_id = pid.group(0)
    wc = _WC_ID_RX.search(html)
    if wc:
        fp.walletconnect_project_id = wc.group(1)

    # React dApp banner heuristic (`%c Future DApp %c v3.11.15` style)
    if re.search(r"(?:Future|Trade|Swap|Bridge|Stake)\s+(?:DApp|App|Protocol)", html, re.IGNORECASE):
        fp.react_dapp_banner = True

    return fp


def detect_asymmetries(hosts: List[HostFingerprint], primary_host: str) -> List[AsymmetryFinding]:
    findings: List[AsymmetryFinding] = []
    by_host = {h.host: h for h in hosts}
    primary = by_host.get(primary_host)
    if not primary:
        return findings

    counter = 1

    # 1. Same bundle hash but missing security headers somewhere
    if primary.bundle_signature:
        clones_missing_headers = [
            h for h in hosts
            if h.host != primary_host
            and h.bundle_signature == primary.bundle_signature
            and "x-frame-options" not in h.security_headers_present
            and not any("frame-ancestors" in headers_present for headers_present in h.security_headers_present)
        ]
        for clone in clones_missing_headers:
            findings.append(AsymmetryFinding(
                finding_id=f"A{counter:03d}",
                description=(
                    f"Subdomain `{clone.host}` ships an identical bundle to production `{primary_host}` "
                    f"(SHA-256 head match: {primary.bundle_signature[:16]}…) but lacks X-Frame-Options/CSP "
                    f"frame-ancestors. Iframe-rendering primitive available."
                ),
                severity_hint="high",
                hosts_involved=[primary_host, clone.host],
                evidence={
                    "primary_bundle_hash": primary.bundle_signature,
                    "clone_bundle_hash": clone.bundle_signature or "",
                    "primary_headers": ",".join(primary.security_headers_present),
                    "clone_headers": ",".join(clone.security_headers_present),
                    "clone_missing": ",".join(clone.security_headers_missing),
                },
            ))
            counter += 1

    # 2. Same auth provider (Privy/WalletConnect) on multiple hosts
    privy_groups: Dict[str, List[str]] = {}
    wc_groups: Dict[str, List[str]] = {}
    for h in hosts:
        if h.privy_app_id:
            privy_groups.setdefault(h.privy_app_id, []).append(h.host)
        if h.walletconnect_project_id:
            wc_groups.setdefault(h.walletconnect_project_id, []).append(h.host)

    for app_id, group_hosts in privy_groups.items():
        if len(group_hosts) >= 2:
            findings.append(AsymmetryFinding(
                finding_id=f"A{counter:03d}",
                description=(
                    f"Privy app `{app_id}` shared across {len(group_hosts)} hosts: {', '.join(group_hosts)}. "
                    f"Any of these hosts is a candidate clickjacking-or-phishing surface for the others."
                ),
                severity_hint="medium",
                hosts_involved=group_hosts,
                evidence={"privy_app_id": app_id},
            ))
            counter += 1

    for proj_id, group_hosts in wc_groups.items():
        if len(group_hosts) >= 2:
            findings.append(AsymmetryFinding(
                finding_id=f"A{counter:03d}",
                description=(
                    f"WalletConnect project `{proj_id}` shared across {len(group_hosts)} hosts. "
                    f"WC peer metadata may not distinguish between origins."
                ),
                severity_hint="low",
                hosts_involved=group_hosts,
                evidence={"walletconnect_project_id": proj_id},
            ))
            counter += 1

    # 3. Production hardened, sibling host unhardened (no bundle hash needed — purely header asymmetry)
    for h in hosts:
        if h.host == primary_host:
            continue
        if h.status_code != 200:
            continue
        # Has dApp signal (Privy/WC ID or bundle pattern) but missing critical headers
        is_dappish = bool(h.privy_app_id or h.walletconnect_project_id or h.bundle_url_pattern or h.react_dapp_banner)
        critical_missing = {"x-frame-options", "content-security-policy"} & set(h.security_headers_missing)
        if is_dappish and critical_missing:
            findings.append(AsymmetryFinding(
                finding_id=f"A{counter:03d}",
                description=(
                    f"Host `{h.host}` looks dApp-like (Privy/WC/bundle present) but is missing critical "
                    f"security headers: {', '.join(sorted(critical_missing))}."
                ),
                severity_hint="medium",
                hosts_involved=[h.host],
                evidence={
                    "missing_headers": ",".join(sorted(critical_missing)),
                    "privy_app_id": h.privy_app_id or "",
                    "walletconnect_project_id": h.walletconnect_project_id or "",
                },
            ))
            counter += 1

    return findings


# ── Cross-Clone Differential (FDE Plan 4, Task 3): env / CSP-headers / API-authz / chain-deploy ──

def _diff_env_vars(primary: HostFingerprint, clone: HostFingerprint) -> List[CloneDiffRow]:
    rows: List[CloneDiffRow] = []
    for key in sorted(set(primary.env_vars) | set(clone.env_vars)):
        pv = primary.env_vars.get(key)
        cv = clone.env_vars.get(key)
        if pv != cv:
            rows.append(CloneDiffRow(
                axis="env-diff",
                prod=f"{key}={pv if pv is not None else '<absent>'}",
                clone_host=clone.host,
                delta=f"{key}={cv if cv is not None else '<absent>'}",
                diff_class="env-drift",
            ))
    return rows


def _diff_headers(primary: HostFingerprint, clone: HostFingerprint) -> List[CloneDiffRow]:
    rows: List[CloneDiffRow] = []
    checks = [
        ("frame-ancestors",
         _extract_frame_ancestors(primary.raw_headers.get("content-security-policy")),
         _extract_frame_ancestors(clone.raw_headers.get("content-security-policy"))),
        ("x-frame-options",
         primary.raw_headers.get("x-frame-options"), clone.raw_headers.get("x-frame-options")),
        ("content-security-policy",
         primary.raw_headers.get("content-security-policy"), clone.raw_headers.get("content-security-policy")),
    ]
    for name, pv, cv in checks:
        if pv and not cv:
            rows.append(CloneDiffRow(
                axis="CSP/headers",
                prod=f"{name}:{pv}",
                clone_host=clone.host,
                delta=f"MISSING {name}",
                diff_class="clone-parity",
            ))
    return rows


def _diff_api_authz(primary: HostFingerprint, clone: HostFingerprint) -> List[CloneDiffRow]:
    """Compares status codes for /api/* paths present in BOTH fingerprints' api_probes.
    Read+compare only — this function never issues requests itself; api_probes is populated by
    the caller/fixture (e.g. a prior authz probe run), matching the white-hat observational constraint."""
    rows: List[CloneDiffRow] = []
    for path in sorted(set(primary.api_probes) & set(clone.api_probes)):
        pv = primary.api_probes[path]
        cv = clone.api_probes[path]
        if pv == cv:
            continue
        is_leak = pv in (401, 403) and cv == 200
        rows.append(CloneDiffRow(
            axis="API-authz",
            prod=f"{path} {pv}",
            clone_host=clone.host,
            delta=f"{cv} (leak)" if is_leak else str(cv),
            diff_class="object-authz" if is_leak else "authz-drift",
        ))
    return rows


def _diff_chain_deploy(primary: HostFingerprint, clone: HostFingerprint) -> List[CloneDiffRow]:
    rows: List[CloneDiffRow] = []
    if primary.chain_id and clone.chain_id and primary.chain_id != clone.chain_id:
        rows.append(CloneDiffRow(
            axis="chain-deploy-diff",
            prod=f"chainId={primary.chain_id}",
            clone_host=clone.host,
            delta=f"chainId={clone.chain_id}",
            diff_class="chain-mismatch",
        ))
    if primary.eip712_domain and clone.eip712_domain and primary.eip712_domain != clone.eip712_domain:
        rows.append(CloneDiffRow(
            axis="chain-deploy-diff",
            prod=f"verifyingContract={primary.eip712_domain}",
            clone_host=clone.host,
            delta=f"verifyingContract={clone.eip712_domain}",
            diff_class="chain-mismatch",
        ))
    return rows


def compute_clone_diffs(hosts: List[HostFingerprint], primary_host: str) -> List[CloneDiffRow]:
    """Four-axis semantic diff (env / CSP-headers / API-authz / chain-deploy) between the primary
    host and every other fingerprinted host. Read+compare only, no exploitation."""
    rows: List[CloneDiffRow] = []
    by_host = {h.host: h for h in hosts}
    primary = by_host.get(primary_host)
    if not primary:
        return rows
    for h in hosts:
        if h.host == primary_host:
            continue
        rows.extend(_diff_env_vars(primary, h))
        rows.extend(_diff_headers(primary, h))
        rows.extend(_diff_api_authz(primary, h))
        rows.extend(_diff_chain_deploy(primary, h))
    return rows


def clone_diff_to_markdown(target: str, rows: List[CloneDiffRow]) -> str:
    """Serialize Cross-Clone Differential rows into clone_diff.md format. Empty rows (no clones /
    single deploy) still produce a file — 'RESULT: N/A — single deploy' — so the Task-4 gate
    detector can distinguish 'ran, nothing to diff' from 'never ran'."""
    lines = [f"# Cross-Clone Differential — {target}"]
    if not rows:
        lines.append("RESULT: N/A — single deploy")
        return "\n".join(lines) + "\n"
    lines.append(f"RESULT: {len(rows)} deltas found")
    lines.append("")
    lines.append("| axis | prod | clone-host | delta | class |")
    lines.append("|-----|------|-----------|--------|-------|")
    for r in rows:
        lines.append(f"| {r.axis} | {r.prod} | {r.clone_host} | {r.delta} | {r.diff_class} |")
    return "\n".join(lines) + "\n"


def write_clone_diff_md(md_out, target: str, rows: List[CloneDiffRow]) -> Path:
    """Write clone_diff.md to the EXACT path given — full session path, never CWD-relative or
    rewritten. Task-4's gate detector looks for it at
    os.path.join(os.path.dirname(ledger_path), 'clone_diff.md'), so the caller MUST pass the full
    session path (e.g. sessions/$DOMAIN/clone_diff.md), and this function must honor it verbatim."""
    path = Path(md_out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(clone_diff_to_markdown(target, rows), encoding="utf-8")
    return path


def _load_subdomains(path: Path) -> List[str]:
    """crtsh_enum output formats vary; accept JSON array or {"subdomains": [...]}."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        # Plain newline list fallback
        return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if isinstance(data, list):
        return [str(x) for x in data]
    if isinstance(data, dict):
        for key in ("subdomains", "hosts", "results"):
            v = data.get(key)
            if isinstance(v, list):
                return [str(x) for x in v]
    return []


def scan(target: str, subdomains: List[str], deep_bundle: bool = False) -> AsymmetryReport:
    primary_url = _normalize_host(target)
    primary_host = urllib.parse.urlparse(primary_url).netloc

    candidates = {primary_url}
    for s in subdomains:
        candidates.add(_normalize_host(s))

    fingerprints: List[HostFingerprint] = []
    for url in sorted(candidates):
        fp = fingerprint_host(url)
        fingerprints.append(fp)

    asymmetries = detect_asymmetries(fingerprints, primary_host)

    report = AsymmetryReport(
        target=target,
        primary_host=primary_host,
        hosts_scanned=fingerprints,
        asymmetries=asymmetries,
    )
    report.hypotheses = [
        f"H[{f.finding_id}]: {f.description}" for f in asymmetries
    ]
    report.clone_diff = compute_clone_diffs(fingerprints, primary_host)
    return report


def cross_program_scan(candidate_list_path: Path, root_cause: str) -> dict:
    """Phase 12 cross-program variant scan stub.

    Reads a JSON list of candidate dApp programs and looks for shared auth
    provider IDs / bundle hashes across them.
    """
    if not candidate_list_path.exists():
        return {"error": f"candidate list not found: {candidate_list_path}"}
    try:
        candidates = json.loads(candidate_list_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": f"could not parse candidate list: {exc}"}

    if not isinstance(candidates, list):
        return {"error": "candidate list must be a JSON array of {name, url, platform}"}

    # Fingerprint each, group by auth provider ID
    by_privy: Dict[str, List[str]] = {}
    by_wc: Dict[str, List[str]] = {}
    fingerprints: List[HostFingerprint] = []

    for c in candidates:
        url = c.get("url") if isinstance(c, dict) else c
        if not url:
            continue
        fp = fingerprint_host(_normalize_host(url))
        fingerprints.append(fp)
        if fp.privy_app_id:
            by_privy.setdefault(fp.privy_app_id, []).append(fp.host)
        if fp.walletconnect_project_id:
            by_wc.setdefault(fp.walletconnect_project_id, []).append(fp.host)

    shared_findings = []
    for app_id, hosts in by_privy.items():
        if len(hosts) >= 2:
            shared_findings.append({
                "shared_id_type": "privy_app_id",
                "shared_id": app_id,
                "hosts": hosts,
                "hypothesis": (
                    f"Multiple programs share Privy app `{app_id}`. "
                    f"If the wildcard / allowed_domains policy on that app is permissive, "
                    f"a finding on one host may apply to all listed."
                ),
            })
    for proj_id, hosts in by_wc.items():
        if len(hosts) >= 2:
            shared_findings.append({
                "shared_id_type": "walletconnect_project_id",
                "shared_id": proj_id,
                "hosts": hosts,
                "hypothesis": (
                    f"Multiple programs share WC project `{proj_id}`. "
                    f"Worth checking metadata.url / origin trust handling on each."
                ),
            })

    return {
        "root_cause_filter": root_cause,
        "hosts_scanned": len(fingerprints),
        "shared_findings": shared_findings,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--target", help="Primary dApp URL")
    parser.add_argument("--subdomains", type=Path, help="JSON of subdomains (crtsh_enum output)")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--md-out", type=Path,
                         help="Full path to write the Cross-Clone Differential markdown "
                              "(e.g. sessions/$DOMAIN/clone_diff.md) — written EXACTLY as given, "
                              "never CWD-relative or rewritten")
    parser.add_argument("--quiet", action="store_true")

    # Cross-program mode
    parser.add_argument("--cross-program", action="store_true")
    parser.add_argument("--root-cause", default="auth_provider_wildcard")
    parser.add_argument("--candidate-list", type=Path)
    args = parser.parse_args(argv)

    if args.cross_program:
        if not args.candidate_list:
            parser.error("--cross-program requires --candidate-list")
        result = cross_program_scan(args.candidate_list, args.root_cause)
        payload = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload, encoding="utf-8")
        if not args.quiet:
            print(payload)
        return 0

    if not args.target:
        parser.error("--target required (or use --cross-program)")

    subdomains = _load_subdomains(args.subdomains) if args.subdomains else []
    report = scan(args.target, subdomains)
    payload = json.dumps(asdict(report), ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    if args.md_out:
        write_clone_diff_md(args.md_out, args.target, report.clone_diff)
    if not args.quiet:
        print(f"Primary host: {report.primary_host}")
        print(f"Hosts scanned: {len(report.hosts_scanned)}")
        print(f"Asymmetries: {len(report.asymmetries)}")
        for f in report.asymmetries:
            print(f"  [{f.severity_hint.upper():6}] {f.finding_id}  hosts={','.join(f.hosts_involved)}")
            print(f"           {f.description}")
    return 0 if not report.asymmetries else 1


if __name__ == "__main__":
    sys.exit(main())
