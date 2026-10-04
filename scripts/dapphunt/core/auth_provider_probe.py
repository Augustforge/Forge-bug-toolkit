#!/usr/bin/env python3
"""
auth_provider_probe.py — Dump publicly readable auth-provider configs for a dApp.

Background:
On 2026-05-20 we found that `https://auth.privy.io/api/v1/apps/<id>` returns
the FULL app config (allowed_domains, frame-ancestors, OAuth providers) when
given the right `privy-app-id` header — no authentication required. This kind
of accidentally-public config endpoint exists across every embedded-wallet /
auth-provider SaaS. This script probes the known ones and dumps their configs.

Providers covered (extend as needed):
- Privy
- Magic
- Web3Auth
- Dynamic Labs
- ThirdWeb
- AppKit / Reown / WalletConnect Cloud
- (Generic: Frontend-discoverable config pattern via bundle scan)

Each provider has its own endpoint format. We attempt all relevant ones for
any app/project ID we find in the dApp's main bundle.

Usage:
    python3 auth_provider_probe.py --target https://oyster.synfutures.com/ \
        --output sessions/$DOMAIN/auth_provider_config.json
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
from typing import Dict, List, Optional, Tuple


# ──────────────────────────────────────────────────────────────────────────
# App-ID discovery patterns per provider
# ──────────────────────────────────────────────────────────────────────────

_APP_ID_PATTERNS: Dict[str, str] = {
    # Privy app IDs are 24-char base62-like starting with `clz` (cuid format)
    "privy": r"\bcl[a-z0-9]{20,26}\b",
    # Magic publishable keys: `pk_live_XXXX` or `pk_test_XXXX`
    "magic": r"\bpk_(?:live|test)_[A-Za-z0-9]{16,40}\b",
    # WalletConnect / Reown project IDs are 32 hex chars
    "walletconnect": r"projectId\s*[:=]\s*['\"]([a-f0-9]{32})['\"]",
    # Web3Auth client IDs look like long base64ish strings; require context
    "web3auth": r"web3authClientId\s*[:=]\s*['\"]([A-Za-z0-9_\-]{20,})['\"]",
    # Dynamic environmentId is a UUID
    "dynamic": r"environmentId\s*[:=]\s*['\"]([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})['\"]",
    # ThirdWeb clientId is 32 hex (uppercase often)
    "thirdweb": r"thirdwebClientId\s*[:=]\s*['\"]([A-Za-z0-9]{32})['\"]",
}


@dataclass
class ProviderConfig:
    provider: str
    app_id: str
    endpoint_probed: str
    status_code: Optional[int]
    config_json: Optional[dict]
    allowed_domains: List[str] = field(default_factory=list)
    frame_ancestors: List[str] = field(default_factory=list)
    oauth_providers: List[str] = field(default_factory=list)
    wildcards_detected: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass
class AuthProbeReport:
    target: str
    providers_detected: List[str] = field(default_factory=list)
    configs: Dict[str, List[ProviderConfig]] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


def _fetch(url: str, headers: Optional[Dict[str, str]] = None, timeout: float = 8.0, max_bytes: int = 5_000_000) -> Tuple[Optional[bytes], Dict[str, str], Optional[int]]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dapphunt-auth-probe/1.0"})
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(max_bytes)
            hdrs = {k.lower(): v for k, v in resp.headers.items()}
            return raw, hdrs, resp.status
    except urllib.error.HTTPError as e:
        try:
            raw = e.read(200_000)
        except Exception:
            raw = b""
        return raw, {}, e.code
    except Exception:
        return None, {}, None


def _fetch_bundle_text(target: str) -> str:
    """Fetch HTML and concatenate top 3 JS bundles for app-ID scanning."""
    raw, _, _ = _fetch(target)
    if not raw:
        return ""
    html = raw.decode("utf-8", errors="replace")
    text_parts = [html]
    # Find script srcs
    parsed = urllib.parse.urlparse(target)
    base = f"{parsed.scheme}://{parsed.netloc}"
    src_rx = re.compile(r"<script[^>]+src=['\"]([^'\"]+)['\"]", re.IGNORECASE)
    srcs = src_rx.findall(html)
    # Prefer main app bundles (index-*.js convention from Vite/Webpack), then by length
    def _bundle_rank(u: str) -> tuple:
        lower = u.lower()
        # Lower tuple sorts earlier — so True/0 priority for `index`, last for vendor/polyfill
        return (
            0 if "/index-" in lower or "/main-" in lower or "/app-" in lower else 1,
            1 if "vendor" in lower or "polyfill" in lower or "runtime" in lower else 0,
            -len(u),
        )
    ranked = sorted(set(srcs), key=_bundle_rank)
    for src in ranked[:5]:
        if src.startswith("//"):
            full = f"{parsed.scheme}:{src}"
        elif src.startswith("/"):
            full = f"{base}{src}"
        elif src.startswith("http"):
            full = src
        else:
            full = urllib.parse.urljoin(target, src)
        raw, _, _ = _fetch(full)
        if raw:
            text_parts.append(raw.decode("utf-8", errors="replace"))
    return "\n".join(text_parts)


def _discover_app_ids(text: str) -> Dict[str, List[str]]:
    found: Dict[str, List[str]] = {}
    for provider, pattern in _APP_ID_PATTERNS.items():
        ids = re.findall(pattern, text)
        # Some patterns return groups, others return full matches
        flat = []
        for item in ids:
            if isinstance(item, tuple):
                flat.extend(x for x in item if x)
            else:
                flat.append(item)
        unique = sorted(set(flat))
        if unique:
            found[provider] = unique
    return found


# ──────────────────────────────────────────────────────────────────────────
# Per-provider probe handlers
# ──────────────────────────────────────────────────────────────────────────

def probe_privy(app_id: str) -> ProviderConfig:
    """Privy: GET /api/v1/apps/{app_id} with header `privy-app-id: {app_id}`."""
    endpoint = f"https://auth.privy.io/api/v1/apps/{app_id}"
    raw, _, status = _fetch(endpoint, headers={"privy-app-id": app_id})
    cfg = ProviderConfig(provider="privy", app_id=app_id, endpoint_probed=endpoint, status_code=status, config_json=None)

    if not raw or status != 200:
        cfg.notes.append(f"Privy probe returned status {status}; no config dumped.")
        return cfg
    try:
        data = json.loads(raw)
        cfg.config_json = data
        # Extract relevant fields
        for key in ("allowed_domains", "allowedDomains", "allowed_origins", "trustedDomains"):
            if key in data and isinstance(data[key], list):
                cfg.allowed_domains.extend(str(x) for x in data[key])
        # OAuth providers
        oauth = data.get("oauth_providers") or data.get("loginMethods")
        if isinstance(oauth, list):
            for entry in oauth:
                if isinstance(entry, str):
                    cfg.oauth_providers.append(entry)
                elif isinstance(entry, dict):
                    name = entry.get("name") or entry.get("provider") or entry.get("type")
                    if name:
                        cfg.oauth_providers.append(str(name))
        # Wildcards
        for d in cfg.allowed_domains:
            if "*" in d:
                cfg.wildcards_detected.append(d)
    except Exception as exc:
        cfg.notes.append(f"Privy response could not be parsed as JSON: {exc}")
    return cfg


def probe_magic(app_id: str) -> ProviderConfig:
    """Magic: GET /v1/api/magic_client/details with key in header."""
    endpoint = "https://api.magic.link/v1/api/magic_client/details"
    raw, _, status = _fetch(endpoint, headers={"x-magic-api-key": app_id})
    cfg = ProviderConfig(provider="magic", app_id=app_id, endpoint_probed=endpoint, status_code=status, config_json=None)
    if not raw or status not in (200, 201):
        cfg.notes.append(f"Magic probe returned status {status}.")
        return cfg
    try:
        data = json.loads(raw)
        cfg.config_json = data
        # Magic returns app config under data.{config}; structure varies
        client = data.get("data") if isinstance(data, dict) else None
        if isinstance(client, dict):
            for key in ("allowedDomains", "allowed_domains", "domain_allowlist"):
                if key in client and isinstance(client[key], list):
                    cfg.allowed_domains.extend(str(x) for x in client[key])
        for d in cfg.allowed_domains:
            if "*" in d:
                cfg.wildcards_detected.append(d)
    except Exception as exc:
        cfg.notes.append(f"Magic response parse error: {exc}")
    return cfg


def probe_walletconnect(project_id: str) -> ProviderConfig:
    """WalletConnect / Reown Cloud: project metadata via Cloud API."""
    # Public read endpoint pattern (varies; we try a few)
    candidates = [
        f"https://api.web3modal.com/getProject?projectId={project_id}",
        f"https://cloud.walletconnect.com/api/v1/projects/{project_id}",
        f"https://api.reown.com/projects/{project_id}",
    ]
    last_status = None
    last_endpoint = candidates[0]
    cfg = ProviderConfig(provider="walletconnect", app_id=project_id, endpoint_probed=candidates[0], status_code=None, config_json=None)
    for ep in candidates:
        raw, _, status = _fetch(ep)
        last_status = status
        last_endpoint = ep
        if raw and status in (200, 201):
            try:
                data = json.loads(raw)
                cfg.config_json = data
                cfg.endpoint_probed = ep
                cfg.status_code = status
                # Look for metadata URLs / allowed origins
                blob = json.dumps(data)
                for w in re.findall(r"\*\.[a-z0-9-]+(?:\.[a-z0-9-]+)+", blob, re.IGNORECASE):
                    cfg.wildcards_detected.append(w)
                return cfg
            except Exception:
                continue
    cfg.endpoint_probed = last_endpoint
    cfg.status_code = last_status
    cfg.notes.append(f"WalletConnect probes returned {last_status}; no public config retrieved.")
    return cfg


def probe_web3auth(client_id: str) -> ProviderConfig:
    """Web3Auth: project config endpoint."""
    endpoint = f"https://api.openlogin.com/projects/{client_id}"
    raw, _, status = _fetch(endpoint)
    cfg = ProviderConfig(provider="web3auth", app_id=client_id, endpoint_probed=endpoint, status_code=status, config_json=None)
    if not raw or status != 200:
        cfg.notes.append(f"Web3Auth probe returned status {status}.")
        return cfg
    try:
        data = json.loads(raw)
        cfg.config_json = data
        blob = json.dumps(data)
        for w in re.findall(r"\*\.[a-z0-9-]+(?:\.[a-z0-9-]+)+", blob, re.IGNORECASE):
            cfg.wildcards_detected.append(w)
    except Exception as exc:
        cfg.notes.append(f"Web3Auth response parse error: {exc}")
    return cfg


def probe_dynamic(env_id: str) -> ProviderConfig:
    """Dynamic Labs: environment config."""
    endpoint = f"https://app.dynamicauth.com/api/v0/environments/{env_id}"
    raw, _, status = _fetch(endpoint)
    cfg = ProviderConfig(provider="dynamic", app_id=env_id, endpoint_probed=endpoint, status_code=status, config_json=None)
    if not raw or status != 200:
        cfg.notes.append(f"Dynamic probe returned status {status}.")
        return cfg
    try:
        data = json.loads(raw)
        cfg.config_json = data
        blob = json.dumps(data)
        for w in re.findall(r"\*\.[a-z0-9-]+(?:\.[a-z0-9-]+)+", blob, re.IGNORECASE):
            cfg.wildcards_detected.append(w)
    except Exception as exc:
        cfg.notes.append(f"Dynamic response parse error: {exc}")
    return cfg


def probe_thirdweb(client_id: str) -> ProviderConfig:
    """ThirdWeb: client config endpoint (sometimes public)."""
    endpoint = f"https://api.thirdweb.com/v1/clients/{client_id}"
    raw, _, status = _fetch(endpoint)
    cfg = ProviderConfig(provider="thirdweb", app_id=client_id, endpoint_probed=endpoint, status_code=status, config_json=None)
    if not raw or status != 200:
        cfg.notes.append(f"ThirdWeb probe returned status {status}.")
        return cfg
    try:
        data = json.loads(raw)
        cfg.config_json = data
        blob = json.dumps(data)
        for w in re.findall(r"\*\.[a-z0-9-]+(?:\.[a-z0-9-]+)+", blob, re.IGNORECASE):
            cfg.wildcards_detected.append(w)
    except Exception as exc:
        cfg.notes.append(f"ThirdWeb response parse error: {exc}")
    return cfg


_PROBE_DISPATCH = {
    "privy": probe_privy,
    "magic": probe_magic,
    "walletconnect": probe_walletconnect,
    "web3auth": probe_web3auth,
    "dynamic": probe_dynamic,
    "thirdweb": probe_thirdweb,
}


def probe(target: str) -> AuthProbeReport:
    report = AuthProbeReport(target=target)
    bundle_text = _fetch_bundle_text(target)
    if not bundle_text:
        report.notes.append(f"Could not fetch any bundle text from {target}.")
        return report

    discovered = _discover_app_ids(bundle_text)
    report.providers_detected = sorted(discovered.keys())

    for provider, ids in discovered.items():
        report.configs[provider] = []
        probe_fn = _PROBE_DISPATCH.get(provider)
        if not probe_fn:
            continue
        for app_id in ids:
            cfg = probe_fn(app_id)
            report.configs[provider].append(cfg)

    # Aggregate wildcards across all providers as a quick scan hint
    all_wildcards = []
    for cfgs in report.configs.values():
        for c in cfgs:
            all_wildcards.extend(c.wildcards_detected)
    if all_wildcards:
        report.notes.append(f"Wildcards found across providers: {sorted(set(all_wildcards))}")
    else:
        report.notes.append("No wildcards detected in any probed config.")

    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    report = probe(args.target)
    # Convert nested dataclasses for JSON
    serializable = {
        "target": report.target,
        "providers_detected": report.providers_detected,
        "configs": {
            provider: [asdict(c) for c in configs]
            for provider, configs in report.configs.items()
        },
        "notes": report.notes,
    }
    payload = json.dumps(serializable, ensure_ascii=False, indent=2, default=str)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")

    if not args.quiet:
        print(f"Target: {report.target}")
        print(f"Providers detected: {', '.join(report.providers_detected) or '(none)'}")
        for provider, configs in report.configs.items():
            for c in configs:
                wc = f" [WILDCARDS: {','.join(c.wildcards_detected)}]" if c.wildcards_detected else ""
                print(f"  {provider}: {c.app_id} → {c.status_code}{wc}")
        for n in report.notes:
            print(f"  note: {n}")

    has_wildcard = any(c.wildcards_detected for cfgs in report.configs.values() for c in cfgs)
    return 0 if not has_wildcard else 1


if __name__ == "__main__":
    sys.exit(main())
