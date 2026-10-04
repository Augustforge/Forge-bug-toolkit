#!/usr/bin/env python3
"""
fetch_program.py — Source fetcher for Solana programs.

Strategy:
1. Try Solscan API (verified programs)
2. Try SolanaFM API (alternative source)
3. Search GitHub via Anchor.toml [programs.mainnet] → repo
4. Fallback: program is unverified → flag for bytecode-only analysis

Usage:
  python3 fetch_program.py --address 9xQeWvG816bUx... --output sessions/X/
  python3 fetch_program.py --github-search "anchor pool" --output sessions/X/

Output: source_meta.json + cloned source (if available) in output dir.
"""
import argparse
import json
import sys
import subprocess
import urllib.request
import urllib.error
from pathlib import Path


SOLSCAN_API = "https://public-api.solscan.io/account/{addr}"
SOLANAFM_API = "https://api.solana.fm/v0/accounts/{addr}"


def http_get(url: str, timeout: int = 15) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "bbt-fetch/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if r.status == 200:
                return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"[!] HTTP {e.code} for {url}", file=sys.stderr)
    except Exception as e:
        print(f"[!] {e}", file=sys.stderr)
    return None


def try_solscan(addr: str) -> dict | None:
    return http_get(SOLSCAN_API.format(addr=addr))


def try_solanafm(addr: str) -> dict | None:
    return http_get(SOLANAFM_API.format(addr=addr))


def github_search_program(addr: str) -> str | None:
    """Search GitHub for repo containing this program ID in Anchor.toml."""
    query_url = f"https://api.github.com/search/code?q={addr}+filename:Anchor.toml"
    result = http_get(query_url)
    if result and result.get("total_count", 0) > 0:
        items = result.get("items", [])
        if items:
            return items[0].get("repository", {}).get("clone_url")
    return None


def clone_repo(repo_url: str, dest: Path) -> bool:
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(dest)],
            check=True,
            capture_output=True,
            timeout=120,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"[!] Clone failed: {e}", file=sys.stderr)
        return False


def main():
    ap = argparse.ArgumentParser(description="Fetch Solana program source")
    ap.add_argument("--address", help="Solana program address")
    ap.add_argument("--github-search", help="GitHub keyword search (fallback)")
    ap.add_argument("--output", required=True, help="Output directory")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    meta = {
        "address": args.address,
        "solscan_data": None,
        "solanafm_data": None,
        "github_repo": None,
        "source_cloned": False,
        "verified_on_chain": False,
        "source_path": None,
    }

    if args.address:
        if not args.quiet:
            print(f"[*] Querying Solscan for {args.address}...")
        meta["solscan_data"] = try_solscan(args.address)
        if not args.quiet:
            print(f"[*] Querying SolanaFM for {args.address}...")
        meta["solanafm_data"] = try_solanafm(args.address)

        if not args.quiet:
            print(f"[*] Searching GitHub for {args.address}...")
        repo_url = github_search_program(args.address)
        if repo_url:
            meta["github_repo"] = repo_url
            src_dir = out / "source"
            if not src_dir.exists():
                if clone_repo(repo_url, src_dir):
                    meta["source_cloned"] = True
                    meta["source_path"] = str(src_dir)

    if args.github_search and not meta["source_cloned"]:
        if not args.quiet:
            print(f"[*] GitHub keyword search: {args.github_search}")
        query_url = f"https://api.github.com/search/repositories?q={args.github_search}"
        gh_result = http_get(query_url)
        if gh_result and gh_result.get("items"):
            top = gh_result["items"][0]
            meta["github_repo"] = top.get("clone_url")

    (out / "source_meta.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")

    if not args.quiet:
        print(f"\n[+] Address:       {meta['address']}")
        print(f"[+] Solscan data:  {'yes' if meta['solscan_data'] else 'no'}")
        print(f"[+] SolanaFM data: {'yes' if meta['solanafm_data'] else 'no'}")
        print(f"[+] GitHub repo:   {meta['github_repo'] or 'not found'}")
        print(f"[+] Source cloned: {meta['source_cloned']}")
        if meta["source_path"]:
            print(f"[+] Source path:   {meta['source_path']}")
        if not meta["source_cloned"]:
            print(f"[!] No source available — use bytecode tier (scripts/sol/bytecode/)")
        print(f"[+] Meta saved:    {out / 'source_meta.json'}")


if __name__ == "__main__":
    main()
