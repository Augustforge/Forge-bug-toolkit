#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Selftest for target_discovery_sources.py (Plan 9 T12 — autonomous candidate-pool collection).

OFFLINE (no network): all fetches are injected as fakes. Proves:
  1. Normalization of each source: field mapping + web3 filter (web2 dropped).
  2. Pagination of fetch_hackerone (links.next) / fetch_intigriti (offset/maxCount) + no creds → [].
  3. Anonymity fail-CLOSED: with a bad config NOT A SINGLE fetch (FIRING of the block — call counters = 0).
  4. baseline_to_anon_config maps not_logged_main → not_main_login.
  5. dedup + collect → rank_programs integration.

Run: py -3 -X utf8 scripts/web3/target_discovery_sources_selftest.py
"""
# Ensure UTF-8 stdout so the summary (arrows/checks) prints on any console (Windows cp1251, etc.).
import sys as _utf8_sys
try:
    _utf8_sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("tds", os.path.join(_HERE, "target_discovery_sources.py"))
tds = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tds)

results = []


def check(name, cond):
    results.append((name, bool(cond)))
    print("  [%s] %s" % ("PASS" if cond else "FAIL", name))


# ---------------------------------------------------------------------------
# Fixtures (formats per research-subagent data)
# ---------------------------------------------------------------------------

IMMUNEFI_RAW = [
    {  # web3 smart-contract program
        "project": "AlphaProto - Smart Contracts", "slug": "alphaproto",
        "maxBounty": 500000, "launchDate": "2026-06-01T00:00:00Z",
        "programType": ["Smart Contract"], "ecosystem": ["Solana"],  # real dump: a list
        "assets": [{"type": "smart_contract", "url": "https://github.com/x"}],
    },
    {  # web2-only (website) — must be dropped
        "project": "WebOnly Corp", "slug": "webonly", "maxBounty": 10000,
        "launchDate": "2026-01-01T00:00:00Z",
        "programType": ["Websites and Applications"],
        "assets": [{"type": "website", "url": "https://webonly.example"}],
    },
    {  # blockchain/DLT — web3
        "project": "ChainNode", "slug": "chainnode", "maxBounty": 250000,
        "launchDate": "2026-05-15T00:00:00Z", "programType": ["Blockchain/DLT"],
        "assets": [{"type": "blockchain_dlt"}],
    },
    "not-a-dict",  # fail-open: non-dict ignored
]

H1_PAGE1 = {
    "data": [
        {  # web3: asset_type SMART_CONTRACT
            "attributes": {"handle": "defiprog", "name": "DeFi Prog", "state": "public_mode"},
            "relationships": {"structured_scopes": {"data": [
                {"attributes": {"asset_type": "SMART_CONTRACT", "asset_identifier": "0xabc"}}]}},
        },
        {  # web2: URL only → drop
            "attributes": {"handle": "justweb", "name": "Just Web", "state": "public_mode"},
            "relationships": {"structured_scopes": {"data": [
                {"attributes": {"asset_type": "URL", "asset_identifier": "example.com"}}]}},
        },
    ],
    "links": {"next": "https://api.hackerone.com/v1/hackers/programs?page[number]=2"},
}
H1_PAGE2 = {
    "data": [
        {  # web3 by keyword in handle (asset_type unknown)
            "attributes": {"handle": "solana-vault", "name": "Vault", "state": "public_mode"},
            "relationships": {},
        },
    ],
    "links": {"next": None},
}

INTIGRITI_PAGE = {
    "maxCount": 2,
    "records": [
        {  # web3 by industry
            "name": "CryptoBridge", "handle": "cryptobridge", "id": "g1",
            "industry": "DeFi / Blockchain",
            "maxBounty": {"value": 75000, "currency": "USD"},
            "confidentialityLevel": {"id": 1, "value": "public"},
        },
        {  # web2 industry → drop
            "name": "Retail Shop", "handle": "retail", "id": "g2",
            "industry": "E-commerce",
            "maxBounty": {"value": 5000, "currency": "USD"},
            "confidentialityLevel": {"id": 1, "value": "public"},
        },
    ],
}


# ---------------------------------------------------------------------------
# 1. Normalization + web3 filter
# ---------------------------------------------------------------------------

print("-- normalize_immunefi (web3 filter + mapping)")
imm = tds.normalize_immunefi(IMMUNEFI_RAW)
imm_names = {c["name"] for c in imm}
check("web2 website program dropped", "WebOnly Corp" not in imm_names)
check("smart-contract program passed", "AlphaProto - Smart Contracts" in imm_names)
check("blockchain/DLT program passed", "ChainNode" in imm_names)
check("non-dict record ignored", len(imm) == 2)
alpha = next(c for c in imm if c["name"].startswith("AlphaProto"))
check("maxBounty → max_payout", alpha["max_payout"] == 500000)
check("launchDate → launched_ts (>0)", isinstance(alpha["launched_ts"], float) and alpha["launched_ts"] > 0)
check("Immunefi is_public=True", alpha["is_public"] is True)
check("source=immunefi", alpha["source"] == "immunefi")
check("ecosystem in tags", "solana" in alpha["tags"])

print("-- normalize_hackerone (web3 filter + poor factors)")
h1 = tds.normalize_hackerone((H1_PAGE1["data"] or []) + (H1_PAGE2["data"] or []))
h1_names = {c["name"] for c in h1}
check("web2 URL program dropped", "justweb" not in h1_names)
check("SMART_CONTRACT program passed", "defiprog" in h1_names)
check("web3-by-keyword (solana-vault) passed", "solana-vault" in h1_names)
dp = next(c for c in h1 if c["name"] == "defiprog")
check("H1 payout=None (no $ in the list)", dp["max_payout"] is None)
check("H1 launched_ts=None (no date)", dp["launched_ts"] is None)
check("H1 public_mode → is_public True", dp["is_public"] is True)

print("-- normalize_intigriti (web3 heuristic + payout)")
intg = tds.normalize_intigriti(INTIGRITI_PAGE["records"])
intg_names = {c["name"] for c in intg}
check("web2 industry dropped", "Retail Shop" not in intg_names)
check("DeFi industry passed", "CryptoBridge" in intg_names)
cb = next(c for c in intg if c["name"] == "CryptoBridge")
check("maxBounty.value → max_payout", cb["max_payout"] == 75000)
check("confidentialityLevel public → is_public True", cb["is_public"] is True)

print("-- intigriti non-USD currency → payout None (neutral)")
eur = tds.normalize_intigriti([{"name": "EurChain", "industry": "crypto",
                                "maxBounty": {"value": 100, "currency": "EUR"}}])
check("EUR payout zeroed to None", eur and eur[0]["max_payout"] is None)


# ---------------------------------------------------------------------------
# 2. fetch_* pagination + no creds → []
# ---------------------------------------------------------------------------

print("-- fetch_hackerone pagination + Basic auth")
h1_calls = {"n": 0, "auth": None}


def fake_h1_get(url, headers=None):
    h1_calls["n"] += 1
    h1_calls["auth"] = (headers or {}).get("Authorization")
    return H1_PAGE1 if "page[number]=2" not in url else H1_PAGE2


raw_h1 = tds.fetch_hackerone(fake_h1_get, "user", "tok")
check("H1 follows 2 pages (links.next)", h1_calls["n"] == 2)
check("H1 collected 3 programs", len(raw_h1) == 3)
check("H1 Basic auth header built", str(h1_calls["auth"]).startswith("Basic "))
check("H1 no creds → [] (without a call)", tds.fetch_hackerone(fake_h1_get, None, None) == [])

print("-- fetch_intigriti pagination + Bearer")
intg_calls = {"n": 0, "auth": None}


def fake_intg_get(url, headers=None):
    intg_calls["n"] += 1
    intg_calls["auth"] = (headers or {}).get("Authorization")
    return INTIGRITI_PAGE  # maxCount=2, records=2 → stop after 1 page


raw_intg = tds.fetch_intigriti(fake_intg_get, "tok")
check("Intigriti stopped by maxCount (1 page)", intg_calls["n"] == 1)
check("Intigriti Bearer header", str(intg_calls["auth"]).startswith("Bearer "))
check("Intigriti no token → []", tds.fetch_intigriti(fake_intg_get, None) == [])


# ---------------------------------------------------------------------------
# 3. Anonymity fail-CLOSED (FIRING: with a bad config — NOT A SINGLE fetch)
# ---------------------------------------------------------------------------

print("-- collect: anonymity fail-CLOSED (FIRING of the fetch block)")
BAD_CFG = {"vpn_active": True, "incognito": False, "not_main_login": True}
GOOD_CFG = {"vpn_active": True, "incognito": True, "not_main_login": True}

spy = {"http": 0, "immunefi": 0}


def spy_http(url, headers=None):
    spy["http"] += 1
    return H1_PAGE1


def spy_immunefi_loader():
    spy["immunefi"] += 1
    return IMMUNEFI_RAW


anon_bad, cand_bad = tds.collect(config=BAD_CFG, http_get=spy_http,
                                 env={"HACKERONE_USERNAME": "u", "HACKERONE_TOKEN": "t", "INTIGRITI_TOKEN": "x"},
                                 immunefi_loader=spy_immunefi_loader)
check("bad config → anon.ok False", anon_bad.ok is False)
check("bad config → 'incognito' in failed_checks", any("incognito" in f for f in anon_bad.failed_checks))
check("FIRING: NOT A SINGLE http-fetch on anon failure", spy["http"] == 0)
check("FIRING: immunefi_loader NOT called on anon failure", spy["immunefi"] == 0)
check("bad config → empty pool", cand_bad == [])

print("-- collect: good config → sources collected + dedup")
spy2 = {"http": 0, "immunefi": 0}


def spy2_http(url, headers=None):
    spy2["http"] += 1
    if "hackerone" in url:
        return H1_PAGE1 if "page[number]=2" not in url else H1_PAGE2
    if "intigriti" in url:
        return INTIGRITI_PAGE
    return None


def spy2_immunefi():
    spy2["immunefi"] += 1
    return IMMUNEFI_RAW


anon_ok, cand = tds.collect(config=GOOD_CFG, http_get=spy2_http,
                            env={"HACKERONE_USERNAME": "u", "HACKERONE_TOKEN": "t", "INTIGRITI_TOKEN": "x"},
                            immunefi_loader=spy2_immunefi)
check("good config → anon.ok True", anon_ok.ok is True)
check("immunefi_loader called", spy2["immunefi"] == 1)
check("http called (H1+Intigriti)", spy2["http"] >= 2)
srcset = {c["source"] for c in cand}
check("pool contains all 3 sources", srcset == {"immunefi", "hackerone", "intigriti"})
check("web2 dropped in all sources (no retail/webonly/justweb)",
      not ({"Retail Shop", "WebOnly Corp", "justweb"} & {c["name"] for c in cand}))

print("-- collect: dedup by (source,name)")
dupd = tds._dedup([{"source": "immunefi", "name": "X"}, {"source": "immunefi", "name": "x"},
                   {"source": "hackerone", "name": "X"}])
check("dedup collapsed immunefi X/x → 1, kept h1 X", len(dupd) == 2)

print("-- collect: source filter (immunefi only)")
_, only_imm = tds.collect(config=GOOD_CFG, sources=["immunefi"], http_get=spy2_http,
                          env={}, immunefi_loader=lambda: IMMUNEFI_RAW)
check("sources=[immunefi] → only immunefi in the pool", {c["source"] for c in only_imm} == {"immunefi"})


# ---------------------------------------------------------------------------
# 4. baseline_to_anon_config mapping
# ---------------------------------------------------------------------------

print("-- baseline_to_anon_config: not_logged_main → not_main_login")
cfg = tds.baseline_to_anon_config({"vpn_active": True, "incognito": True, "not_logged_main": True})
check("not_logged_main mapped to not_main_login", cfg.get("not_main_login") is True)
check("mapped config passes the anonymity gate", tds.anonymity_precondition(cfg).ok is True)
check("non-dict baseline → {}", tds.baseline_to_anon_config(None) == {})


# ---------------------------------------------------------------------------
# 5. collect → rank_programs integration
# ---------------------------------------------------------------------------

print("-- integration: collect → rank_programs (EV ranking of the pool)")
ranked = tds.rank_programs(cand, strong_patterns=["solana", "smart_contract"])
check("rank_programs ranked a non-empty pool", len(ranked) >= 3)
check("EV monotonically decreasing", all(ranked[i].ev >= ranked[i + 1].ev for i in range(len(ranked) - 1)))
check("top-EV is Immunefi (rich payout+fresh factors)", ranked[0].factors["payout"] > tds._td.UNKNOWN_PAYOUT)


# ---------------------------------------------------------------------------
print("")
passed = sum(1 for _, ok in results if ok)
total = len(results)
print("%d/%d target_discovery_sources selftest cases green" % (passed, total))
sys.exit(0 if passed == total else 1)
