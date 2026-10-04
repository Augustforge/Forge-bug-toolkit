#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Source adapters for proactive /deephunt discovery (Plan 9 T12 — autonomous candidate-pool collection).

Makes the proactive mode truly hands-off: it collects candidate programs from three platforms on its own and
normalizes them into the program-schema consumed by `target_discovery.rank_programs`. Previously the pool was
assembled by hand (subagent/Playwright); now — from APIs/public dumps without CF.

THREE SOURCES (all without Cloudflare, pure Python):
  • immunefi   — community JSON dump (Immunefi has no official API), via the existing immunefi_scope.py.
                 RICH: payout (maxBounty) + launchDate + programType/assets (web3 tag) → strong EV factors.
  • hackerone  — GET /v1/hackers/programs (Basic auth). POOR: /programs does NOT return $-payout or launch date
                 at the list level → payout/freshness degrade to neutral (UNKNOWN_PAYOUT / FRESHNESS_UNKNOWN).
                 web3 filter by structured_scopes[].asset_type (exact enum name not confirmed → several
                 candidates + keyword fallback on asset_identifier).
  • intigriti  — GET /external/researcher/v1/programs (Bearer). MEDIUM: maxBounty.value is present, no date,
                 no direct web3 field → heuristic filter (industry/name keyword). Platform limitation.

⚠️ THINK≠ACT: READ-ONLY access to public/authenticated program lists. No active testing/mutation.
🔒 Anonymity precondition (fail-CLOSED) is reused from target_discovery: collect() does NOT perform a single
   fetch until config passes. The baseline key `not_logged_main` maps to the expected `not_main_login`.

fail-open on a broken source record (degrades to neutral), fail-closed on anonymity (never lets anything
through when unclear). All fetches are injected (http_get / immunefi_loader) → selftest without network.

CLI (via target_discovery.py --live), but the module is tested standalone with an offline fixture.
"""

import argparse
import base64
import importlib.util
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load_sibling(name):
    """Import a sibling module by file name (robust to running from any CWD)."""
    spec = importlib.util.spec_from_file_location(name, os.path.join(_HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_td = _load_sibling("target_discovery")
_immunefi = _load_sibling("immunefi_scope")

anonymity_precondition = _td.anonymity_precondition
rank_programs = _td.rank_programs
AnonResult = _td.AnonResult


# ---------------------------------------------------------------------------
# .env / baseline reading (values are NOT printed)
# ---------------------------------------------------------------------------

def _env_path():
    return os.path.join(_HERE, "..", "..", ".env")


def load_env(path=None):
    """Mini .env parser (KEY=VALUE). fail-open: no file → empty dict."""
    p = path or _env_path()
    out = {}
    try:
        with open(p, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return out


def baseline_to_anon_config(baseline):
    """opsec_baseline.json → config for anonymity_precondition.

    baseline uses `not_logged_main`; anonymity_precondition expects `not_main_login` — we map it,
    otherwise the fail-closed gate always fails and the proactive mode is dead. Any ambiguity is left as is →
    the gate decides on its own (fail-closed).
    """
    if not isinstance(baseline, dict):
        return {}
    return {
        "vpn_active": baseline.get("vpn_active"),
        "incognito": baseline.get("incognito"),
        # baseline name → gate name
        "not_main_login": baseline.get("not_main_login", baseline.get("not_logged_main")),
    }


def load_baseline_config(path=None):
    """Read opsec_baseline.json and return the anon-config. fail-open → {} (gate fails = closed)."""
    p = path or os.path.join(_HERE, "..", "..", "opsec_baseline.json")
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return baseline_to_anon_config(json.load(fh))
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# default http_get (production; a fake is injected in tests)
# ---------------------------------------------------------------------------

def _default_http_get(url, headers=None, timeout=30):
    """requests.get(url).json() or None. fail-open: any error/non-200 → None."""
    try:
        import requests
        r = requests.get(url, headers=headers or {}, timeout=timeout)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# web3 filters (drop web2 — deephunt is contracts only)
# ---------------------------------------------------------------------------

_WEB3_KEYWORDS = (
    "smart contract", "smartcontract", "blockchain", "dlt", "defi", "web3", "crypto",
    "solidity", "solana", "anchor", "move", "sui", "aptos", "evm", "protocol", "onchain",
    "on-chain", "bridge", "vault", "staking", "rollup", "l2", "zk",
)


def _text_has_web3(*parts):
    joined = " ".join(str(p or "").lower() for p in parts)
    return any(kw in joined for kw in _WEB3_KEYWORDS)


# ---------------------------------------------------------------------------
# Immunefi (rich source — via the existing immunefi_scope.load_projects)
# ---------------------------------------------------------------------------

def _immunefi_is_web3(p):
    """programType contains Smart Contract/Blockchain OR assets[].type is web3.

    Immunefi is ~entirely web3: if there are no signal fields at all — treat as web3 (fallback), so that
    the absence of a field doesn't throw out the whole pool.
    """
    pt = p.get("programType")
    if isinstance(pt, str):
        pt = [pt]
    joined = " ".join(str(x).lower() for x in (pt or []))
    if "smart contract" in joined or "blockchain" in joined or "dlt" in joined:
        return True
    assets = p.get("assets") or []
    for a in assets:
        if isinstance(a, dict) and str(a.get("type", "")).lower() in ("smart_contract", "blockchain_dlt"):
            return True
    # neither programType nor web3 assets found
    if pt or assets:
        return False  # fields are present but there is no web3 signal → web2/other
    return True       # no fields at all → Immunefi is web3 by nature


def normalize_immunefi(projects):
    """Immunefi community records → program-schema. Web3 programs only."""
    out = []
    for p in (projects or []):
        if not isinstance(p, dict):
            continue
        if not _immunefi_is_web3(p):
            continue
        pt = p.get("programType")
        if isinstance(pt, str):
            pt = [pt]
        tags = [str(x).lower() for x in (pt or [])]
        eco = p.get("ecosystem")            # real dump: a list, e.g. ["Solana"]
        if isinstance(eco, str):
            eco = [eco]
        for e in (eco or []):
            tags.append(str(e).lower())
        for a in (p.get("assets") or []):
            if isinstance(a, dict) and a.get("type"):
                tags.append(str(a.get("type")).lower())
        out.append({
            "name": p.get("project") or p.get("slug") or "?",
            "max_payout": p.get("maxBounty"),
            "launched_ts": _immunefi._parse_ts(p.get("launchDate") or p.get("date")) or None,
            "reports_count": 0,          # Immunefi doesn't expose this publicly
            "is_public": True,           # community dump = public programs only
            "tags": sorted(set(t for t in tags if t)),
            "url": _immunefi._scope_url(p),
            "source": "immunefi",
        })
    return out


def fetch_immunefi(loader=None):
    """List of Immunefi programs (raw). loader is injected in tests; by default — load_projects()."""
    ld = loader or _immunefi.load_projects
    try:
        return ld() or []
    except Exception:
        return []


# ---------------------------------------------------------------------------
# HackerOne (poor — no $-payout/date at the list level)
# ---------------------------------------------------------------------------

_H1_SC_ASSET = ("SMART_CONTRACT", "SMARTCONTRACT", "SMART CONTRACTS", "BLOCKCHAIN")


def _h1_is_web3(attrs, scopes):
    """web3 if asset_type is among the smart-contract candidates OR a keyword in identifier/handle/name.

    The exact asset_type enum name for contracts is not confirmed by the docs → several candidates + fallback.
    """
    for s in (scopes or []):
        sa = s.get("attributes", s) if isinstance(s, dict) else {}
        at = str(sa.get("asset_type", "")).upper()
        if at in _H1_SC_ASSET:
            return True
        if _text_has_web3(sa.get("asset_identifier"), sa.get("instruction")):
            return True
    return _text_has_web3(attrs.get("handle"), attrs.get("name"), attrs.get("policy"))


def normalize_hackerone(raw_programs):
    """H1 /programs records → program-schema. Web3 only. payout/date absent → None (neutral)."""
    out = []
    for item in (raw_programs or []):
        if not isinstance(item, dict):
            continue
        attrs = item.get("attributes") or {}
        # structured_scopes may arrive in relationships (if requested) — best-effort
        rel = item.get("relationships") or {}
        scopes = (((rel.get("structured_scopes") or {}).get("data")) or [])
        if not _h1_is_web3(attrs, scopes):
            continue
        state = str(attrs.get("state", "")).lower()
        out.append({
            "name": attrs.get("handle") or attrs.get("name") or "?",
            "max_payout": None,          # /programs doesn't return $ at the list level
            "launched_ts": None,         # no launch date in the basic response
            "reports_count": 0,
            "is_public": ("public" in state) or (attrs.get("state") is None),
            "tags": [t for t in ["hackerone", str(attrs.get("state") or "").lower()] if t],
            "url": "https://hackerone.com/" + str(attrs.get("handle") or ""),
            "source": "hackerone",
        })
    return out


def fetch_hackerone(http_get, username, token, max_pages=10, page_size=100):
    """GET /v1/hackers/programs (Basic auth), follows links.next. No creds → []."""
    if not username or not token:
        return []
    cred = base64.b64encode(("%s:%s" % (username, token)).encode("utf-8")).decode("ascii")
    headers = {"Authorization": "Basic " + cred, "Accept": "application/json"}
    url = "https://api.hackerone.com/v1/hackers/programs?page[size]=%d" % page_size
    out, pages = [], 0
    while url and pages < max_pages:
        data = http_get(url, headers=headers)
        if not isinstance(data, dict):
            break
        out.extend(data.get("data") or [])
        url = (data.get("links") or {}).get("next")
        pages += 1
    return out


# ---------------------------------------------------------------------------
# Intigriti (medium — maxBounty present, no date/web3 field)
# ---------------------------------------------------------------------------

def _intigriti_max_payout(rec):
    mb = rec.get("maxBounty")
    if isinstance(mb, dict):
        # MoneyViewModel {value, currency}; take value only if currency is USD/empty (otherwise neutral)
        cur = str(mb.get("currency") or "").upper()
        if cur in ("", "USD", "$"):
            return mb.get("value")
        return None
    if isinstance(mb, (int, float)):
        return mb
    return None


def _intigriti_is_web3(rec):
    return _text_has_web3(rec.get("industry"), rec.get("name"), rec.get("handle"))


def normalize_intigriti(records):
    """Intigriti overview records → program-schema. web3 by heuristic (the platform gives no direct field)."""
    out = []
    for rec in (records or []):
        if not isinstance(rec, dict):
            continue
        if not _intigriti_is_web3(rec):
            continue
        conf = rec.get("confidentialityLevel")
        if isinstance(conf, dict):
            conf = conf.get("value")
        conf_s = str(conf or "").lower()
        tags = [t for t in ["intigriti", str(rec.get("industry") or "").lower()] if t]
        out.append({
            "name": rec.get("name") or rec.get("handle") or "?",
            "max_payout": _intigriti_max_payout(rec),
            "launched_ts": None,         # overview doesn't return dates
            "reports_count": 0,
            "is_public": ("public" in conf_s) or (conf is None),
            "tags": tags,
            "url": "https://app.intigriti.com/researcher/programs/" + str(rec.get("handle") or rec.get("id") or ""),
            "source": "intigriti",
        })
    return out


def fetch_intigriti(http_get, token, limit=500, max_pages=10):
    """GET /external/researcher/v1/programs (Bearer), paginates by offset/maxCount. No token → []."""
    if not token:
        return []
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    out, offset, pages = [], 0, 0
    while pages < max_pages:
        url = "https://api.intigriti.com/external/researcher/v1/programs?limit=%d&offset=%d" % (limit, offset)
        data = http_get(url, headers=headers)
        if not isinstance(data, dict):
            break
        recs = data.get("records") or []
        out.extend(recs)
        pages += 1
        maxc = data.get("maxCount") or 0
        offset += len(recs)
        if not recs or offset >= maxc:
            break
    return out


# ---------------------------------------------------------------------------
# Orchestrator: anonymity → fetch → normalize → merge/dedup
# ---------------------------------------------------------------------------

_ALL_SOURCES = ("immunefi", "hackerone", "intigriti")


def _dedup(candidates):
    """Remove duplicates by (source, name.lower) — keep the first."""
    seen, out = set(), []
    for c in candidates:
        key = (c.get("source"), str(c.get("name", "")).lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def collect(sources=None, config=None, http_get=None, env=None, immunefi_loader=None):
    """Collect the candidate pool. fail-CLOSED on anonymity: until config passes — NOT A SINGLE fetch.

    Returns (AnonResult, list[program_dict]). anon.ok=False → ([], gate-fail): the caller must
    report what is wrong and not dig. A single source that failed/has no creds degrades to [], without
    breaking the others (fail-open per-source).
    """
    anon = anonymity_precondition(config)
    if not anon.ok:
        return anon, []

    srcs = [s.lower() for s in (sources or _ALL_SOURCES)]
    http_get = http_get or _default_http_get
    env = env if env is not None else load_env()

    candidates = []
    if "immunefi" in srcs:
        candidates.extend(normalize_immunefi(fetch_immunefi(loader=immunefi_loader)))
    if "hackerone" in srcs:
        raw = fetch_hackerone(http_get, env.get("HACKERONE_USERNAME"), env.get("HACKERONE_TOKEN"))
        candidates.extend(normalize_hackerone(raw))
    if "intigriti" in srcs:
        raw = fetch_intigriti(http_get, env.get("INTIGRITI_TOKEN"))
        candidates.extend(normalize_intigriti(raw))

    return anon, _dedup(candidates)


# ---------------------------------------------------------------------------
# CLI (--live: autonomous collection under the anonymity baseline → EV ranking)
# ---------------------------------------------------------------------------

def _main(argv=None):
    ap = argparse.ArgumentParser(
        description="Autonomous collection + EV ranking of candidate programs (Immunefi/HackerOne/Intigriti).")
    ap.add_argument("--live", action="store_true",
                    help="real collection from the network (under the anonymity baseline); without it — help only")
    ap.add_argument("--sources", default="immunefi,hackerone,intigriti",
                    help="sources, comma-separated (default: all three)")
    ap.add_argument("--patterns", default="",
                    help="strong un-dup classes, comma-separated (e.g. solana,amm,oracle)")
    ap.add_argument("--out", help="where to save the raw candidate pool (JSON) — e.g. sessions/_discovery/programs.json")
    ap.add_argument("--json", action="store_true", help="output the ranking as JSON")
    args = ap.parse_args(argv)

    if not args.live:
        print("--live is required for real collection. Example:\n"
              "  py -3 -X utf8 scripts/web3/target_discovery_sources.py --live "
              "--patterns solana,amm --out sessions/_discovery/programs.json",
              file=sys.stderr)
        return 1

    cfg = load_baseline_config()
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    anon, candidates = collect(sources=sources, config=cfg)
    if not anon.ok:
        print("🔒 anonymity precondition FAILED (no fetch performed): %s"
              % "; ".join(anon.failed_checks), file=sys.stderr)
        print("Read-only proactive mode REQUIRES an anonymous identity. Check opsec_baseline.json "
              "(vpn_active/incognito/not_logged_main).", file=sys.stderr)
        return 2

    if not candidates:
        print("Pool is empty: collection ran (anon ok), but the sources returned 0 web3 programs. "
              "Causes: network/CF on the Immunefi dump, no H1/Intigriti creds in .env, or the filter dropped everything. "
              "This means 'recon not collected', NOT 'no targets' — complete the sources.", file=sys.stderr)
        return 3

    if args.out:
        try:
            outp = args.out
            os.makedirs(os.path.dirname(outp), exist_ok=True)
            with open(outp, "w", encoding="utf-8") as fh:
                json.dump(candidates, fh, ensure_ascii=False, indent=2)
            print("pool (%d programs) saved → %s" % (len(candidates), args.out), file=sys.stderr)
        except Exception as exc:
            print("could not save the pool: %s" % exc, file=sys.stderr)

    strong = [p.strip() for p in args.patterns.split(",") if p.strip()]
    ranked = rank_programs(candidates, strong_patterns=strong or None)

    if args.json:
        print(json.dumps([s.to_dict() for s in ranked], ensure_ascii=False, indent=2))
    else:
        print("EV     payout fresh crowd patt  source     name")
        for s in ranked:
            f = s.factors
            src = next((c.get("source") for c in candidates if (c.get("name") or c.get("url")) == s.name), "?")
            print("%.4f %.3f  %.3f %.3f %.3f %-10s %s" % (
                s.ev, f["payout"], f["freshness"], f["crowd"], f["pattern"], src, s.name))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
