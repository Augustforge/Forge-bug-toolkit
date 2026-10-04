#!/usr/bin/env python3
"""
_check_active_targets.py — Refresh _active_targets.md with fresh DeFiLlama new
+ GitHub trending data filtered by primitive keywords.

Usage:
  python3 _check_active_targets.py                       # refresh + write
  python3 _check_active_targets.py --primitive zk_vm     # only update one section
  python3 _check_active_targets.py --dry-run             # print, don't write
"""
import argparse
import json
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

THIS_DIR = Path(__file__).parent
TARGETS_MD = THIS_DIR / "_active_targets.md"

PRIMITIVE_KEYWORDS = {
    "zk_vm": ["zkvm", "risc0", "sp1-zkvm", "succinct", "jolt", "boojum", "zksync", "scroll", "linea", "taiko", "zkevm"],
    "restaking_avs": ["restaking", "eigenlayer", "avs", "symbiotic", "karak", "altlayer", "lagrange"],
    "mpc_threshold": ["tss", "mpc", "frost", "threshold-signature", "threshold-bls", "gg24"],
    "da_layer": ["celestia", "eigenda", "avail", "data-availability"],
    "intent_solver": ["uniswapx", "cowswap", "across-protocol", "1inch-fusion", "intent-based"],
    "post_quantum": ["post-quantum", "kyber", "dilithium", "ml-kem", "ml-dsa", "sphincs"],
    "dag_consensus": ["sui-blockchain", "aptos", "mysticeti", "bullshark", "blockstm", "narwhal"],
}


def fetch_defillama_new(limit: int = 50, window_days: int = 365,
                         category_filter: str | None = None) -> list[dict]:
    """Best-effort fetch DeFiLlama protocols.

    By default 365-day window — wide enough for emerging primitives that took
    >90 days to gain traction (mature restaking, intent solvers, etc.).
    For genuinely "new this quarter" — pass window_days=90 explicitly.

    Optional category_filter: substring match against DeFiLlama's `category` field.
    """
    if requests is None:
        return []
    try:
        r = requests.get("https://api.llama.fi/protocols", timeout=20)
        if r.status_code != 200:
            return []
        data = r.json()
        cutoff = time.time() - window_days * 86400
        recent = [p for p in data if p.get("listedAt") and p["listedAt"] > cutoff]
        if category_filter:
            cf = category_filter.lower()
            recent = [p for p in recent if cf in str(p.get("category", "")).lower()]
        recent.sort(key=lambda p: p.get("tvl", 0) or 0, reverse=True)
        return recent[:limit]
    except Exception as e:
        print(f"[warn] DeFiLlama fetch failed: {e}", file=sys.stderr)
        return []


def fetch_github_trending(language: str = "rust") -> list[dict]:
    """GitHub trending by language. Note: GitHub trending API is unofficial."""
    if requests is None:
        return []
    try:
        url = f"https://api.github.com/search/repositories?q=language:{language}+created:>{time.strftime('%Y-%m-%d', time.gmtime(time.time() - 180*86400))}&sort=stars&order=desc"
        r = requests.get(url, headers={"User-Agent": "BBT-research/1.0"}, timeout=20)
        if r.status_code != 200:
            return []
        return r.json().get("items", [])[:30]
    except Exception as e:
        print(f"[warn] GitHub fetch failed: {e}", file=sys.stderr)
        return []


def match_primitive(text: str, primitive: str) -> bool:
    keywords = PRIMITIVE_KEYWORDS.get(primitive, [])
    t = text.lower()
    return any(k in t for k in keywords)


def classify_protocols(protocols: list[dict], primitives: list[str]) -> dict[str, list[dict]]:
    out = {p: [] for p in primitives}
    for proto in protocols:
        blob = " ".join(str(v) for k, v in proto.items() if isinstance(v, (str, list))).lower()
        for p in primitives:
            if match_primitive(blob, p):
                out[p].append(proto)
    return out


def render_section(primitive: str, items: list[dict]) -> list[str]:
    lines = [f"### {primitive} (auto-refreshed)"]
    if not items:
        lines.append("- (no new protocols matching keywords in last 90 days)")
    else:
        for it in items[:10]:
            name = it.get("name") or it.get("full_name") or "?"
            url = it.get("url") or it.get("html_url") or "?"
            tvl = it.get("tvl")
            if tvl:
                lines.append(f"- **{name}** — {url} (TVL ${tvl:,.0f})")
            else:
                stars = it.get("stargazers_count")
                lines.append(f"- **{name}** — {url}" + (f" (★ {stars})" if stars else ""))
    lines.append("")
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--primitive", help="Refresh only one primitive section")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if requests is None:
        print("[err] requests library required. Skipping refresh.", file=sys.stderr)
        sys.exit(1)

    primitives = [args.primitive] if args.primitive else list(PRIMITIVE_KEYWORDS.keys())
    print(f"[info] refreshing {len(primitives)} primitive section(s)")

    window_days = 365                                     # widened default
    print(f"[info] fetching DeFiLlama new (window={window_days}d)...")
    llama = fetch_defillama_new(window_days=window_days)
    print(f"  → {len(llama)} protocols")

    print("[info] fetching GitHub trending Rust + Go + TypeScript repos...")
    github_repos = []
    for lang in ["rust", "go", "typescript"]:
        github_repos.extend(fetch_github_trending(lang))
        time.sleep(2)
    print(f"  → {len(github_repos)} trending repos")

    all_items = llama + github_repos
    classified = classify_protocols(all_items, primitives)

    refresh_block = [f"## Auto-refreshed sections — {time.strftime('%Y-%m-%d')}", ""]
    for p in primitives:
        refresh_block.extend(render_section(p, classified[p]))

    if args.dry_run:
        print("\n".join(refresh_block))
        return

    existing = TARGETS_MD.read_text(encoding="utf-8") if TARGETS_MD.exists() else ""
    if "## Auto-refreshed sections —" in existing:
        before, _ = existing.split("## Auto-refreshed sections —", 1)
        new = before + "\n".join(refresh_block) + "\n"
    else:
        new = existing.rstrip() + "\n\n" + "\n".join(refresh_block) + "\n"
    TARGETS_MD.write_text(new, encoding="utf-8")
    print(f"[ok] {TARGETS_MD}")


if __name__ == "__main__":
    main()
