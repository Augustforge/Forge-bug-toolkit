#!/usr/bin/env python3
"""
Proactive target discovery — Immunefi, HackerOne, Bugcrowd, Shodan, DeFiLlama.
Finds fresh programs, immature targets, open databases.

Usage:
    python3 proactive.py --output ./out
    python3 proactive.py --output ./out --source immunefi
"""

import argparse
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import requests

SHODAN_KEY = os.getenv("SHODAN_API_KEY", "")
HELIUS_KEY = os.getenv("HELIUS_API_KEY", "")


_SOLANA_CHAIN_KEYWORDS = frozenset([
    "solana", "anchor", "sol", "marinade", "jito", "phoenix", "openbook",
    "raydium", "orca", "kamino", "marginfi", "drift", "jupiter", "sanctum",
    "loopscale", "squads", "pump.fun", "helius", "spl", "neon", "eclipse",
    "sonic", "magicblock", "metaplex", "bonk", "tensor",
])


def detect_program_chain(name: str, description: str = "", chains_field: list | None = None) -> str:
    """Detect whether a bounty program target is EVM, Solana, or web2 from textual signals."""
    if chains_field:
        for c in chains_field:
            c_lower = str(c).lower()
            if "solana" in c_lower:
                return "solana"
    text = (name + " " + description).lower()
    if any(kw in text for kw in _SOLANA_CHAIN_KEYWORDS):
        return "solana"
    web3_evm = ["ethereum", "evm", "solidity", "uniswap", "aave", "compound",
                "polygon", "arbitrum", "optimism", "base", "bsc"]
    if any(kw in text for kw in web3_evm):
        return "evm"
    return "unknown"


def fetch_immunefi() -> list[dict]:
    """Immunefi programs via community-maintained unofficial mirror (updated hourly).
    Source: infosec-us-team/Immunefi-Bug-Bounty-Programs-Unofficial
    """
    try:
        r = requests.get(
            "https://raw.githubusercontent.com/infosec-us-team/"
            "Immunefi-Bug-Bounty-Programs-Unofficial/main/projects.json",
            timeout=30,
        )
        if r.status_code != 200:
            return [{"error": f"immunefi-mirror HTTP {r.status_code}"}]
        data = r.json()
        programs = []
        for b in (data if isinstance(data, list) else [])[:50]:
            assets = b.get("assets", [])
            max_bounty = b.get("maximumBounty") or b.get("maxBounty")
            project = b.get("project") or b.get("title", "?")
            ecosystem = b.get("ecosystem") or b.get("chains") or []
            chain = detect_program_chain(project, b.get("description", ""), ecosystem)
            programs.append({
                "platform": "immunefi",
                "project": project,
                "chain": chain,
                "ecosystem": ecosystem,
                "max_bounty": max_bounty,
                "assets_count": len(assets),
                "kyc_required": b.get("kycRequired", False),
                "url": b.get("url") or f"https://immunefi.com/bug-bounty/{b.get('project', '')}/",
                "launch_date": b.get("launchDate", ""),
            })
        return programs
    except Exception as e:
        return [{"error": str(e)}]


_WEB3_KEYWORDS = frozenset([
    "blockchain", "defi", "crypto", "web3", "ethereum", "solidity", "nft",
    "token", "bitcoin", "evm", "dao", "protocol", "swap", "bridge", "vault",
    "staking", "yield", "dex", "amm", "lending", "wallet", "coinbase",
    "binance", "uniswap", "aave", "compound", "chainlink", "polygon",
    "arbitrum", "optimism", "solana", "avalanche", "cosmos", "tron",
    "layer2", "l2", "zk", "rollup", "metaverse", "gamefi", "p2e",
])


def _is_web3(name: str, handle: str = "", urls: list[str] | None = None) -> bool:
    text = (name + " " + handle + " " + " ".join(urls or [])).lower()
    return any(kw in text for kw in _WEB3_KEYWORDS)


def fetch_hackerone_programs() -> list[dict]:
    """HackerOne programs via arkadiyt/bounty-targets-data. Web3 tagged."""
    try:
        r = requests.get(
            "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/main/data/hackerone_data.json",
            timeout=30,
        )
        if r.status_code != 200:
            return [{"error": f"hackerone HTTP {r.status_code}"}]
        data = r.json()
        programs = []
        for p in data:
            if not p.get("offers_bounties"):
                continue
            in_scope = p.get("targets", {}).get("in_scope", [])
            max_bounty = 0
            for scope in in_scope:
                val = scope.get("bounty_max") or 0
                try:
                    if int(val) > max_bounty:
                        max_bounty = int(val)
                except (TypeError, ValueError):
                    pass
            scope_urls = [s.get("asset_identifier", "") for s in in_scope]
            handle = p.get("handle", "")
            name = p.get("name", handle)
            programs.append({
                "platform": "hackerone",
                "handle": handle,
                "name": name,
                "max_bounty": max_bounty or None,
                "response_efficiency": p.get("response_efficiency_percentage"),
                "scopes_count": len(in_scope),
                "is_web3": _is_web3(name, handle, scope_urls),
                "url": f"https://hackerone.com/{handle}",
            })
        programs.sort(key=lambda x: (x["is_web3"], x.get("max_bounty") or 0), reverse=True)
        return programs[:60]
    except Exception as e:
        return [{"error": str(e)}]


def fetch_defillama_new() -> list[dict]:
    """New DeFi protocols from the last week."""
    try:
        r = requests.get("https://api.llama.fi/protocols", timeout=30)
        if r.status_code != 200:
            return [{"error": f"defillama HTTP {r.status_code}"}]
        protocols = r.json()
        cutoff = (datetime.utcnow() - timedelta(days=14)).timestamp()
        new = [p for p in protocols
               if p.get("listedAt", 0) > cutoff]
        return [
            {
                "name": p.get("name"),
                "category": p.get("category"),
                "tvl": p.get("tvl", 0),
                "url": p.get("url"),
                "audits": p.get("audits", "0"),
                "audit_links": p.get("audit_links", []),
                "listed_at": datetime.fromtimestamp(p.get("listedAt", 0)).isoformat()
                             if p.get("listedAt") else None,
            }
            for p in new[:30]
        ]
    except Exception as e:
        return [{"error": str(e)}]


def shodan_open_dbs() -> list[dict]:
    """Open databases via Shodan."""
    if not SHODAN_KEY:
        return [{"error": "SHODAN_API_KEY not set"}]
    queries = [
        'product:"MongoDB" -authentication',
        'product:"Elasticsearch" port:9200',
        'product:"Redis" -auth',
        'product:"CouchDB"',
    ]
    results = []
    for q in queries:
        try:
            r = requests.get(
                "https://api.shodan.io/shodan/host/count",
                params={"key": SHODAN_KEY, "query": q},
                timeout=20,
            )
            if r.status_code == 200:
                results.append({"query": q, "total": r.json().get("total", 0)})
        except Exception as e:
            results.append({"query": q, "error": str(e)})
    return results


def fetch_bugcrowd_programs() -> list[dict]:
    """Bugcrowd programs via arkadiyt/bounty-targets-data. Web3 tagged."""
    try:
        r = requests.get(
            "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/main/data/bugcrowd_data.json",
            timeout=30,
        )
        if r.status_code != 200:
            return [{"error": f"bugcrowd HTTP {r.status_code}"}]
        data = r.json()
        programs = []
        for p in data:
            name = p.get("name", "")
            url = p.get("url", "")
            in_scope = p.get("targets", {}).get("in_scope", [])
            scope_urls = [s.get("target", "") for s in in_scope]
            programs.append({
                "platform": "bugcrowd",
                "name": name,
                "max_payout": p.get("max_payout"),
                "safe_harbor": p.get("safe_harbor"),
                "scopes_count": len(in_scope),
                "is_web3": _is_web3(name, "", [url] + scope_urls),
                "url": url,
            })
        programs.sort(key=lambda x: (x["is_web3"], x.get("max_payout") or 0), reverse=True)
        return programs[:60]
    except Exception as e:
        return [{"error": str(e)}]


def fetch_yeswehack() -> list[dict]:
    """YesWeHack — a public API without authentication."""
    try:
        r = requests.get(
            "https://api.yeswehack.com/programs",
            params={"page": 1, "nb_items_per_page": 50},
            headers={"User-Agent": "BBT/1.0"},
            timeout=30,
        )
        if r.status_code != 200:
            return [{"error": f"yeswehack HTTP {r.status_code}"}]
        items = r.json().get("items", [])
        return [
            {
                "platform": "yeswehack",
                "title": p.get("title"),
                "slug": p.get("slug"),
                "bounty_min": p.get("bounty_reward_min"),
                "bounty_max": p.get("bounty_reward_max"),
                "scopes_count": p.get("scopes_count"),
                "type": p.get("type"),
                "url": f"https://yeswehack.com/programs/{p.get('slug', '')}",
            }
            for p in items[:30]
        ]
    except Exception as e:
        return [{"error": str(e)}]


def fetch_intigriti() -> list[dict]:
    """Intigriti — via arkadiyt/bounty-targets-data (updated hourly)."""
    try:
        r = requests.get(
            "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/main/data/intigriti_data.json",
            timeout=30,
        )
        if r.status_code != 200:
            return [{"error": f"intigriti-mirror HTTP {r.status_code}"}]
        data = r.json()
        return [
            {
                "platform": "intigriti",
                "title": p.get("name") or p.get("handle"),
                "handle": p.get("handle"),
                "max_bounty": p.get("max_bounty"),
                "confidentiality": p.get("confidentiality_level"),
                "url": p.get("url"),
                "targets_count": len(p.get("targets", {}).get("in_scope", [])),
            }
            for p in data[:30]
        ]
    except Exception as e:
        return [{"error": str(e)}]


def fetch_hackenproof(days_fresh: int = 14) -> list[dict]:
    """HackenProof — Web3 focus. Cloudflare-protected site.
    Strategy:
    1. Try cloudscraper (pip install cloudscraper) — bypasses CF v1/v2
    2. Fallback: /activities-api/programs/weekly — 10 weekly picks, no CF block
    3. Manual fallback: https://hackenproof.com/programs?sort=updated_at-desc
    """
    def _parse_programs(programs: list, days_fresh: int) -> list[dict]:
        cutoff = datetime.utcnow() - timedelta(days=days_fresh)
        results = []
        for p in programs:
            updated_str = (p.get("updated_at") or p.get("updatedAt") or "").strip()
            # HackenProof uses "DD Mon YYYY" format in some endpoints
            try:
                from datetime import datetime as dt
                try:
                    upd = dt.fromisoformat(updated_str.replace("Z", "+00:00")).replace(tzinfo=None)
                except ValueError:
                    upd = dt.strptime(updated_str, "%d %b %Y")
                if upd < cutoff:
                    continue
            except Exception:
                pass  # no date → include
            mb = p.get("max_bounty") or p.get("maxBounty") or p.get("critical_reward") or ""
            try:
                mb = int(float(str(mb).replace(",", "").replace("$", "")))
            except (ValueError, TypeError):
                mb = None
            slug = p.get("slug") or p.get("id") or ""
            tags = p.get("labels", {})
            blockchain = (p.get("blockchain") or
                          tags.get("project_types", []) or
                          tags.get("types", []))
            results.append({
                "platform": "hackenproof",
                "name": p.get("title") or p.get("name") or slug,
                "max_bounty": mb,
                "updated_at": updated_str[:10],
                "blockchain": blockchain,
                "kyc_required": p.get("kyc_required", False),
                "url": (f"https://hackenproof.com/programs/{slug}" if slug
                        else "https://hackenproof.com/programs?sort=updated_at-desc"),
            })
        results.sort(key=lambda x: (x.get("max_bounty") or 0), reverse=True)
        return results[:30]

    _BROWSER = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36"),
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://hackenproof.com/programs",
    }

    # 1. Try cloudscraper (handles Cloudflare JS challenge)
    try:
        import cloudscraper
        scraper = cloudscraper.create_scraper()
        r = scraper.get(
            "https://hackenproof.com/api/hackers/programs",
            params={"page": 1, "per_page": 50,
                    "sort[type]": "updated_at", "sort[direction]": "desc"},
            headers={"Accept": "application/json"},
            timeout=30,
        )
        if r.status_code == 200:
            data = r.json()
            programs = (data if isinstance(data, list)
                        else data.get("programs") or data.get("data") or [])
            if programs:
                return _parse_programs(programs, days_fresh)
    except ImportError:
        pass  # cloudscraper not installed
    except Exception:
        pass

    # 2. Fallback: /activities-api/programs/weekly — works without CF bypass
    try:
        r2 = requests.get(
            "https://hackenproof.com/activities-api/programs/weekly",
            headers=_BROWSER, timeout=20,
        )
        if r2.status_code == 200:
            data2 = r2.json()
            programs2 = data2.get("programs", []) if isinstance(data2, dict) else data2
            if programs2:
                parsed = _parse_programs(programs2, days_fresh=9999)  # weekly picks, no date filter
                if parsed:
                    parsed[0]["note"] = "weekly-picks only (10 programs) — install cloudscraper for full list"
                    return parsed
    except Exception:
        pass

    return [{"error": "HackenProof blocked (Cloudflare). pip install cloudscraper to fix.",
             "fallback": "https://hackenproof.com/programs?sort=updated_at-desc",
             "note": "Manual check: sort by 'Last updated' desc"}]


def fetch_sherlock(days_fresh: int = 365) -> list[dict]:
    """Sherlock — DeFi audit contests + bug bounties.
    Primary: GitHub API org sherlock-audit (repo = contest, always has source).
    Fallback: audits.sherlock.xyz REST.
    """
    gh_token = os.getenv("GITHUB_TOKEN", "")
    gh_headers = {"Accept": "application/vnd.github.v3+json"}
    if gh_token:
        gh_headers["Authorization"] = f"token {gh_token}"

    results = []
    try:
        # Primary: GitHub org — each public repo is an audit/bounty contest
        r = requests.get(
            "https://api.github.com/orgs/sherlock-audit/repos",
            params={"type": "public", "sort": "created", "direction": "desc", "per_page": 50},
            headers=gh_headers,
            timeout=30,
        )
        if r.status_code == 200:
            repos = r.json()
            cutoff = datetime.utcnow() - timedelta(days=days_fresh)
            for repo in repos:
                created_str = repo.get("created_at", "")
                try:
                    created_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    if created_dt < cutoff:
                        continue
                except Exception:
                    pass

                name = repo.get("name", "")
                desc = repo.get("description") or ""
                # Exclude meta/template repos
                if name in (".", "judging", ".github") or "template" in name.lower():
                    continue

                # Bug bounty repos typically have "bug-bounty" in name
                is_bounty = "bug-bounty" in name.lower() or "bugbounty" in name.lower()
                results.append({
                    "platform": "sherlock",
                    "name": name,
                    "type": "bug-bounty" if is_bounty else "audit-contest",
                    "description": desc[:120],
                    "github": repo.get("html_url", ""),
                    "stars": repo.get("stargazers_count", 0),
                    "created_at": created_str[:10],
                    "url": f"https://audits.sherlock.xyz/contests/{name}" if not is_bounty
                           else "https://audits.sherlock.xyz/bug-bounties",
                    "quick_scan_ready": True,  # there is always a public GitHub
                })

            if results:
                results.sort(key=lambda x: x["type"] == "bug-bounty", reverse=True)
                return results[:30]

        # Fallback: try REST endpoints
        for url in [
            "https://audits.sherlock.xyz/api/contests",
            "https://audits.sherlock.xyz/api/bug-bounties",
        ]:
            try:
                r2 = requests.get(url,
                                  headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
                                  timeout=20)
                if r2.status_code == 200:
                    data = r2.json()
                    contests = (data if isinstance(data, list)
                                else data.get("data") or data.get("contests", []))
                    for c in contests[:30]:
                        github = c.get("github") or c.get("repo_url") or ""
                        results.append({
                            "platform": "sherlock",
                            "name": c.get("title") or c.get("name") or "?",
                            "type": (c.get("type") or "contest").lower(),
                            "status": c.get("status", ""),
                            "max_reward": c.get("max_reward") or c.get("prize_pool"),
                            "github": github,
                            "quick_scan_ready": bool(github),
                            "url": f"https://audits.sherlock.xyz/contests/{c.get('id', '')}",
                        })
                    if results:
                        return results[:30]
            except Exception:
                pass

        return [{"error": "all sherlock endpoints failed",
                 "fallback": "https://audits.sherlock.xyz/bug-bounties"}]
    except Exception as e:
        return [{"error": str(e), "fallback": "https://audits.sherlock.xyz/bug-bounties"}]


def fetch_standoff365() -> list[dict]:
    """Standoff 365 — a Russian platform by Positive Technologies. Scraping."""
    try:
        r = requests.get(
            "https://bugbounty.standoff365.com/api/v1/programs",
            headers={"User-Agent": "BBT/1.0", "Accept": "application/json"},
            timeout=30,
        )
        if r.status_code == 200:
            try:
                data = r.json()
                return [
                    {
                        "platform": "standoff365",
                        "title": p.get("name"),
                        "max_bounty": p.get("max_reward"),
                        "url": p.get("url"),
                    }
                    for p in (data if isinstance(data, list) else data.get("programs", []))
                ][:30]
            except Exception:
                return [{"error": "standoff365 returned non-JSON; needs Playwright scraping"}]
        return [{"error": f"standoff365 HTTP {r.status_code}"}]
    except Exception as e:
        return [{"error": str(e)}]


def fetch_solana_deploys(days_fresh: int = 7) -> list[dict]:
    """Fresh Solana program deployments via Helius enhanced RPC.

    Strategy:
    1. Pull recent verified programs via SolanaFM (public API, no key)
    2. Cross-reference with Anchor IDL registry for framework detection
    3. Filter by deployment age

    Fallback: just return a stub directing to Solscan UI when no key.
    """
    if not HELIUS_KEY:
        return [{
            "platform": "solana_deploys",
            "note": "HELIUS_API_KEY not set. Set it for live program-deployment feed.",
            "fallback": "https://solscan.io/leaderboard/program",
            "alt_fallback": "https://solanafm.com/analytics/programs",
        }]

    try:
        url = f"https://api.helius.xyz/v0/addresses/programs/recent?api-key={HELIUS_KEY}"
        r = requests.get(url, timeout=30)
        if r.status_code != 200:
            return [{"error": f"helius HTTP {r.status_code}", "fallback": "https://solscan.io/leaderboard/program"}]
        data = r.json()
        cutoff = (datetime.utcnow() - timedelta(days=days_fresh)).timestamp()
        results = []
        for prog in (data if isinstance(data, list) else data.get("programs", []))[:50]:
            deployed_at = prog.get("deployedAt") or prog.get("firstSlotTimestamp") or 0
            if deployed_at and deployed_at < cutoff:
                continue
            results.append({
                "platform": "solana_deploys",
                "program_id": prog.get("address") or prog.get("programId"),
                "chain": "solana",
                "deployed_at": deployed_at,
                "verified": prog.get("verified", False),
                "framework": prog.get("framework", "unknown"),
                "url": f"https://solscan.io/account/{prog.get('address', '')}",
            })
        return results[:30]
    except Exception as e:
        return [{"error": str(e), "fallback": "https://solscan.io/leaderboard/program"}]


def fetch_sec3_audit_comps() -> list[dict]:
    """Sec3 audit competitions (Sherlock-style for Solana). RSS-based since no public API."""
    try:
        r = requests.get(
            "https://www.sec3.dev/blog/rss.xml",
            headers={"User-Agent": "BBT/1.0"},
            timeout=20,
        )
        if r.status_code == 200:
            text = r.text
            import re
            entries = re.findall(r"<item>(.*?)</item>", text, re.DOTALL)
            results = []
            for entry in entries[:20]:
                title_m = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
                link_m = re.search(r"<link>(.*?)</link>", entry, re.DOTALL)
                pub_m = re.search(r"<pubDate>(.*?)</pubDate>", entry, re.DOTALL)
                title = (title_m.group(1) if title_m else "").strip()
                link = (link_m.group(1) if link_m else "").strip()
                pub = (pub_m.group(1) if pub_m else "").strip()
                title_lower = title.lower()
                is_audit_comp = any(kw in title_lower for kw in ["audit", "contest", "competition", "vulnerability", "exploit"])
                if not is_audit_comp:
                    continue
                results.append({
                    "platform": "sec3_audit_comp",
                    "title": title,
                    "chain": "solana",
                    "published": pub[:25],
                    "url": link,
                })
            return results
        return [{"error": f"sec3 HTTP {r.status_code}",
                 "fallback": "https://www.sec3.dev/blog"}]
    except Exception as e:
        return [{"error": str(e), "fallback": "https://www.sec3.dev/blog"}]


def fetch_bizone() -> list[dict]:
    """BI.ZONE Bug Bounty — a Russian platform. Fully JS-rendered."""
    return [{
        "platform": "bizone",
        "note": "Site is JS-rendered. Use Playwright/puppeteer for scraping.",
        "url": "https://bugbounty.bi.zone/companies",
    }]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    ap.add_argument("--source", choices=["immunefi", "hackerone", "bugcrowd",
                                          "yeswehack", "intigriti", "hackenproof",
                                          "sherlock", "standoff365", "bizone",
                                          "defillama", "shodan",
                                          "solana_deploys", "sec3", "all"],
                    default="all")
    ap.add_argument("--chain-filter", choices=["evm", "solana", "all"], default="all",
                    help="Filter Immunefi/DeFiLlama results by chain")
    args = ap.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    results = {"timestamp": datetime.utcnow().isoformat() + "Z"}

    if args.source in ("immunefi", "all"):
        print("[*] Fetching Immunefi programs...")
        results["immunefi"] = fetch_immunefi()
        print(f"    → {len(results['immunefi'])} programs")

    if args.source in ("hackerone", "all"):
        print("[*] Fetching HackerOne programs...")
        results["hackerone"] = fetch_hackerone_programs()
        print(f"    → {len(results['hackerone'])} programs")

    if args.source in ("bugcrowd", "all"):
        print("[*] Fetching Bugcrowd programs...")
        results["bugcrowd"] = fetch_bugcrowd_programs()
        print(f"    → {len(results['bugcrowd'])} programs")

    if args.source in ("yeswehack", "all"):
        print("[*] Fetching YesWeHack programs...")
        results["yeswehack"] = fetch_yeswehack()
        print(f"    → {len(results['yeswehack'])} programs")

    if args.source in ("intigriti", "all"):
        print("[*] Fetching Intigriti programs (via bounty-targets-data)...")
        results["intigriti"] = fetch_intigriti()
        print(f"    → {len(results['intigriti'])} programs")

    if args.source in ("hackenproof", "all"):
        print("[*] Fetching HackenProof programs (Web3-focused, fresh 14d)...")
        results["hackenproof"] = fetch_hackenproof()
        print(f"    → {len(results['hackenproof'])} fresh programs")

    if args.source in ("sherlock", "all"):
        print("[*] Fetching Sherlock bug bounties + active contests...")
        results["sherlock"] = fetch_sherlock()
        ready = sum(1 for p in results["sherlock"] if p.get("quick_scan_ready"))
        print(f"    → {len(results['sherlock'])} programs ({ready} with public GitHub = quick-scan ready)")

    if args.source in ("standoff365", "all"):
        print("[*] Fetching Standoff 365 programs (RU segment)...")
        results["standoff365"] = fetch_standoff365()
        print(f"    → {len(results['standoff365'])} entries")

    if args.source in ("bizone", "all"):
        print("[*] Fetching BI.ZONE programs (RU segment)...")
        results["bizone"] = fetch_bizone()
        print(f"    → {len(results['bizone'])} entries (JS-rendered)")

    if args.source in ("defillama", "all"):
        print("[*] Fetching DeFiLlama new protocols...")
        results["defillama_new"] = fetch_defillama_new()
        print(f"    → {len(results['defillama_new'])} new protocols")

    if args.source in ("shodan", "all"):
        print("[*] Querying Shodan for exposed DBs...")
        results["shodan_open_dbs"] = shodan_open_dbs()

    if args.source in ("solana_deploys", "all"):
        print("[*] Fetching fresh Solana program deployments...")
        results["solana_deploys"] = fetch_solana_deploys()
        print(f"    -> {len(results['solana_deploys'])} entries")

    if args.source in ("sec3", "all"):
        print("[*] Fetching Sec3 audit competitions...")
        results["sec3_audit_comps"] = fetch_sec3_audit_comps()
        print(f"    -> {len(results['sec3_audit_comps'])} entries")

    if args.chain_filter != "all":
        if "immunefi" in results:
            results["immunefi"] = [
                p for p in results["immunefi"]
                if p.get("chain") == args.chain_filter or "error" in p
            ]
            print(f"[*] Filtered immunefi to chain={args.chain_filter}: {len(results['immunefi'])} programs")

    summary = out / "proactive.json"
    summary.write_text(json.dumps(results, indent=2, default=str))

    print(f"[+] Saved to {summary}")


if __name__ == "__main__":
    main()
