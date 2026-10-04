#!/usr/bin/env python3
"""
fetch.py — Clones/updates public TSS/MPC implementations for cross-diff.

Usage:
  python3 fetch.py                # clone all (skip existing)
  python3 fetch.py --update       # git pull existing repos
  python3 fetch.py --only binance-tss-lib
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

THIS_DIR = Path(__file__).parent
REPOS_DIR = THIS_DIR / "repos"
LAST_FETCH = THIS_DIR / "_last_fetch.json"

# Curated TSS/MPC implementations.
# pinned_sha = None means HEAD; specific SHA used for pre-incident snapshots.
CORPUS = [
    {
        "name": "binance-tss-lib",
        "url": "https://github.com/bnb-chain/tss-lib.git",
        "pinned_sha": None,
        "primitive": "gg18-gg20",
        "lang": "go",
    },
    {
        "name": "coinbase-kryptology",
        "url": "https://github.com/coinbase/kryptology.git",
        "pinned_sha": None,
        "primitive": "gg20-frost",
        "lang": "go",
    },
    {
        "name": "zengo-multi-party-ecdsa",
        "url": "https://github.com/ZenGo-X/multi-party-ecdsa.git",
        "pinned_sha": None,
        "primitive": "gg18",
        "lang": "rust",
    },
    {
        "name": "thorchain-go-tss",
        "url": "https://gitlab.com/thorchain/tss/go-tss.git",
        # WARNING: post-incident pin for diff reference. Update SHA after fix landed.
        "pinned_sha": None,
        "primitive": "gg20",
        "lang": "go",
    },
    {
        "name": "nomad-tss-engine",
        "url": "https://github.com/nomad-xyz/tss-engine.git",
        "pinned_sha": None,
        "primitive": "gg20",
        "lang": "rust",
    },
    {
        "name": "taurus-frost-go",
        "url": "https://github.com/taurushq-io/frost-ed25519.git",
        "pinned_sha": None,
        "primitive": "frost",
        "lang": "go",
    },
]


def run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=300)
        return r.returncode, (r.stdout + r.stderr)[-2000:]
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except FileNotFoundError:
        return 127, "git not found"


def clone_or_update(entry: dict, update: bool) -> dict:
    target = REPOS_DIR / entry["name"]
    result = {"name": entry["name"], "primitive": entry["primitive"], "lang": entry["lang"]}

    if target.exists() and update:
        rc, out = run(["git", "fetch", "--depth", "200"], cwd=target)
        if rc == 0:
            rc, out = run(["git", "reset", "--hard", "origin/HEAD"], cwd=target)
        result["action"] = "updated"
        result["rc"] = rc
    elif target.exists():
        result["action"] = "skipped (exists)"
        result["rc"] = 0
    else:
        REPOS_DIR.mkdir(parents=True, exist_ok=True)
        rc, out = run(["git", "clone", "--depth", "200", entry["url"], str(target)])
        result["action"] = "cloned"
        result["rc"] = rc
        if rc != 0:
            result["error"] = out
            return result

    if entry.get("pinned_sha"):
        rc, _ = run(["git", "checkout", entry["pinned_sha"]], cwd=target)
        result["pinned"] = entry["pinned_sha"]

    rc, out = run(["git", "rev-parse", "HEAD"], cwd=target)
    if rc == 0:
        result["head_sha"] = out.strip()
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="git pull existing")
    ap.add_argument("--only", help="Clone only this repo by name")
    args = ap.parse_args()

    repos = CORPUS if not args.only else [r for r in CORPUS if r["name"] == args.only]
    if args.only and not repos:
        print(f"[err] no repo named {args.only}", file=sys.stderr)
        sys.exit(1)

    results = []
    for entry in repos:
        print(f"[*] {entry['name']} ({entry['primitive']}, {entry['lang']})")
        r = clone_or_update(entry, args.update)
        print(f"    {r['action']} (rc={r.get('rc')})")
        if r.get("head_sha"):
            print(f"    HEAD={r['head_sha'][:12]}")
        if r.get("error"):
            print(f"    [!] {r['error'][:200]}")
        results.append(r)

    LAST_FETCH.write_text(json.dumps({
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "results": results,
    }, indent=2), encoding="utf-8")
    print(f"[ok] manifest: {LAST_FETCH}")


if __name__ == "__main__":
    main()
