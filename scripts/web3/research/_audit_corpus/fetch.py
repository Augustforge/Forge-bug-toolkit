#!/usr/bin/env python3
"""
fetch.py — Download curated public audit reports + manage _known_findings.jsonl.

Usage:
  python3 fetch.py                          # download all (skip existing)
  python3 fetch.py --only verichains
  python3 fetch.py --list                   # list known findings
  python3 fetch.py --add-finding --auditor verichains ...
"""
import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

THIS_DIR = Path(__file__).parent
REPORTS_DIR = THIS_DIR / "reports"
KNOWN_FINDINGS = THIS_DIR / "_known_findings.jsonl"

# Curated public audit reports. All URLs published by auditors themselves.
# If a URL changed — update it here.
CORPUS = [
    {
        "auditor": "verichains",
        "filename": "2022-tsshock-binance-gg18.md",
        # Verichains published a technical writeup on their site; the PDF is not always stable.
        # We use a markdown mirror for grep-friendliness.
        "url": "https://www.verichains.io/tsshock/",
        "mode": "html-to-md",
        "tags": ["tss", "paillier", "key-extraction", "gg18"],
    },
    {
        "auditor": "kudelski",
        "filename": "2023-frost-security-review.pdf",
        "url": "https://research.kudelskisecurity.com/2023/07/04/frost-security-analysis/",
        "mode": "html-to-md",
        "tags": ["frost", "ed25519", "threshold"],
    },
    {
        "auditor": "trail-of-bits",
        "filename": "2023-zcash-zip-244.pdf",
        "url": "https://github.com/trailofbits/publications/raw/master/reviews/2023-04-zcash-zip-244-securityreview.pdf",
        "mode": "binary",
        "tags": ["zk", "consensus"],
    },
    {
        "auditor": "trail-of-bits",
        "filename": "2024-eigenlayer-review.pdf",
        "url": "https://github.com/trailofbits/publications/raw/master/reviews/2024-01-eigenlayer-securityreview.pdf",
        "mode": "binary",
        "tags": ["restaking", "avs", "slashing"],
    },
    {
        "auditor": "chainsecurity",
        "filename": "2023-eigenlayer-strategy.pdf",
        "url": "https://chainsecurity.com/wp-content/uploads/2023/11/ChainSecurity_EigenLayer_StrategyManager.pdf",
        "mode": "binary",
        "tags": ["restaking", "avs"],
    },
    {
        "auditor": "openzeppelin",
        "filename": "2024-arbitrum-bold.pdf",
        "url": "https://blog.openzeppelin.com/arbitrum-bold-protocol-audit",
        "mode": "html-to-md",
        "tags": ["l2", "fraud-proof"],
    },
]

USER_AGENT = "BBT-research/1.0 (educational security research)"


def fetch_one(entry: dict) -> dict:
    target_dir = REPORTS_DIR / entry["auditor"]
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / entry["filename"]
    result = {"auditor": entry["auditor"], "filename": entry["filename"]}

    if target.exists():
        result["action"] = "exists"
        result["size"] = target.stat().st_size
        return result

    try:
        req = urllib.request.Request(entry["url"], headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read()
        if entry["mode"] == "binary":
            target.write_bytes(body)
        else:
            # html-to-md: minimal extraction without external deps
            try:
                text = body.decode("utf-8", errors="ignore")
                target.write_text(text, encoding="utf-8")
            except Exception:
                target.write_bytes(body)
        result["action"] = "downloaded"
        result["size"] = len(body)
    except Exception as e:
        result["action"] = "failed"
        result["error"] = str(e)[:200]
    return result


def list_known() -> None:
    if not KNOWN_FINDINGS.exists():
        print("[info] _known_findings.jsonl empty")
        return
    n = 0
    for line in KNOWN_FINDINGS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            f = json.loads(line)
            print(f"  · [{f['auditor']}/{f['year']}] {f['id']} — {f['severity']} — "
                  f"{', '.join(f.get('class', []))[:60]}")
            n += 1
        except Exception:
            continue
    print(f"[info] {n} known finding(s)")


def add_finding(args) -> None:
    entry = {
        "id": args.id,
        "auditor": args.auditor,
        "year": args.year,
        "severity": args.severity,
        "class": args.classes.split(",") if args.classes else [],
        "target": args.target,
        "source_url": args.source_url,
        "fix_commit": args.fix_commit,
        "sibling_variants_warned": args.siblings.split(",") if args.siblings else [],
        "summary": args.summary,
        "added_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with KNOWN_FINDINGS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[ok] added {entry['id']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="Fetch only this auditor")
    ap.add_argument("--list", action="store_true", help="List known findings")
    ap.add_argument("--add-finding", action="store_true")
    # add-finding args
    ap.add_argument("--id")
    ap.add_argument("--auditor")
    ap.add_argument("--year", type=int)
    ap.add_argument("--severity", choices=["critical", "high", "medium", "low", "info"])
    ap.add_argument("--classes", help="comma-separated")
    ap.add_argument("--target")
    ap.add_argument("--source-url")
    ap.add_argument("--fix-commit", default="")
    ap.add_argument("--siblings", default="")
    ap.add_argument("--summary", default="")
    args = ap.parse_args()

    if args.list:
        list_known()
        return

    if args.add_finding:
        required = ["id", "auditor", "year", "severity"]
        missing = [r for r in required if not getattr(args, r.replace("-", "_"))]
        if missing:
            print(f"[err] --add-finding requires: {missing}", file=sys.stderr)
            sys.exit(1)
        add_finding(args)
        return

    repos = CORPUS if not args.only else [r for r in CORPUS if r["auditor"] == args.only]
    print(f"[info] fetching {len(repos)} audit report(s)")
    for entry in repos:
        r = fetch_one(entry)
        if r["action"] == "downloaded":
            print(f"  [ok] {r['auditor']}/{r['filename']} ({r['size']} bytes)")
        elif r["action"] == "exists":
            print(f"  [-] {r['auditor']}/{r['filename']} exists")
        else:
            print(f"  [!] {r['auditor']}/{r['filename']} — {r.get('error', '?')}")


if __name__ == "__main__":
    main()
