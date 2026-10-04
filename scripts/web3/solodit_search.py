#!/usr/bin/env python3
"""
Solodit pattern matcher — search 30k+ historical audit findings.

Solodit (https://solodit.cyfrin.io) aggregates findings from major audit firms:
Trail of Bits, OpenZeppelin, Spearbit, ConsenSys Diligence, Code4rena, Sherlock.

For each finding in our scan we search for similar historical findings.
Match = strong signal that this is a real bug + we can reference past disclosures.

Usage:
    python3 solodit_search.py --query "reentrancy in withdraw" --output ./out
    python3 solodit_search.py --enrich web3_summary.json
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

GRAPHQL = "https://solodit.cyfrin.io/api/graphql"

QUERY = """
query SearchFindings($q: String!, $limit: Int!) {
  search(query: $q, limit: $limit) {
    items {
      id
      title
      severity
      summary
      project
      protocol
      auditFirm
      reportUrl
      tags
      date
    }
    totalCount
  }
}
"""


def search_solodit(query: str, limit: int = 10) -> list[dict]:
    """Try GraphQL endpoint, fallback to web search if API not available."""
    try:
        r = requests.post(
            GRAPHQL,
            json={"query": QUERY, "variables": {"q": query, "limit": limit}},
            headers={"Content-Type": "application/json", "User-Agent": "BBT/1.0"},
            timeout=20,
        )
        if r.status_code == 200:
            data = r.json()
            return data.get("data", {}).get("search", {}).get("items", [])
    except Exception as e:
        print(f"  GraphQL failed: {e}", file=sys.stderr)

    # Fallback to web search (HTML scraping placeholder)
    return web_search_fallback(query, limit)


def web_search_fallback(query: str, limit: int) -> list[dict]:
    """Fallback when GraphQL is not available — placeholder, returns empty.
    For full implementation: use Solodit's REST search endpoint or scrape HTML."""
    return [{
        "_note": "Solodit API not reachable — manual search recommended",
        "_url": f"https://solodit.cyfrin.io/?q={query.replace(' ', '+')}",
    }]


def build_query(finding: dict) -> str:
    """Build Solodit search query from finding."""
    parts = []
    vuln = finding.get("vulnerability", "")
    parts.append(vuln.replace("-", " "))
    if finding.get("function"):
        parts.append(finding["function"])
    return " ".join(parts).strip()


def enrich_summary(summary_path: Path) -> dict:
    """Enrich web3_summary.json with Solodit matches per finding."""
    summary = json.loads(summary_path.read_text())
    findings = summary.get("findings", [])

    for f in findings[:20]:  # rate limit — top 20
        sev = f.get("severity", "")
        if sev not in ("critical", "high", "medium"):
            continue
        query = build_query(f)
        if not query:
            continue
        print(f"[*] Solodit search: {query[:60]}")
        matches = search_solodit(query, limit=5)
        f["solodit_matches"] = matches
        time.sleep(1)

    return summary


def load_threat_models() -> list[dict]:
    """Load all threat_models/*.yaml for F5 classification."""
    try:
        import yaml
    except ImportError:
        print("[warn] PyYAML not installed — classify-against-models unavailable", file=sys.stderr)
        return []
    repo_root = Path(__file__).resolve().parents[2]
    tm_dir = repo_root / "scripts" / "web3" / "threat_models"
    if not tm_dir.is_dir():
        return []
    out = []
    for yml in sorted(tm_dir.glob("*.yaml")):
        if yml.name.startswith("_"):
            continue
        try:
            data = yaml.safe_load(yml.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "id" in data:
                out.append(data)
        except Exception:
            continue
    return out


def model_match_score(model: dict, finding: dict) -> int:
    """Crude keyword scoring of finding text against model tags + name."""
    tags = set(t.lower() for t in (model.get("applies_when") or {}).get("tags", []))
    pc = set((model.get("applies_when") or {}).get("protocol_class", []))
    text_blob = " ".join(str(v).lower() for k, v in finding.items()
                          if isinstance(v, str))
    title_blob = (model.get("name", "") + " " + model.get("id", "")).lower()
    score = 0
    for tag in tags:
        if tag in text_blob:
            score += 2
    for word in title_blob.split():
        if len(word) > 3 and word in text_blob:
            score += 1
    return score


def classify_against_models(findings: list[dict], models: list[dict],
                            min_score: int = 3) -> dict[str, list[dict]]:
    """Returns {model_id: [findings_that_match]}."""
    out = {m["id"]: [] for m in models}
    for f in findings:
        for m in models:
            if model_match_score(m, f) >= min_score:
                out[m["id"]].append({
                    "title": f.get("title", "")[:120],
                    "severity": f.get("severity"),
                    "url": f.get("reportUrl"),
                })
    return out


def suggest_new_models(findings: list[dict], models: list[dict],
                        cluster_threshold: int = 5) -> list[dict]:
    """Findings that match NO model — cluster by simple keyword fingerprint."""
    from collections import Counter

    unmatched = []
    for f in findings:
        if not any(model_match_score(m, f) >= 3 for m in models):
            unmatched.append(f)
    print(f"[info] {len(unmatched)} findings without a matching threat_model")

    fingerprints = Counter()
    for f in unmatched:
        txt = " ".join(str(v).lower() for v in f.values() if isinstance(v, str))
        words = re.findall(r"\b[a-z]{5,}\b", txt)
        stop = {"audit", "finding", "report", "issue", "vulnerab", "smart", "contract"}
        keys = tuple(sorted(set(w for w in words if w not in stop))[:3])
        if keys:
            fingerprints[keys] += 1

    candidates = []
    for keys, n in fingerprints.most_common(20):
        if n >= cluster_threshold:
            candidates.append({"keywords": list(keys), "count": n,
                                "suggestion": f"Consider new threat_model: tags=[{', '.join(keys)}]"})
    return candidates


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", help="Direct search query")
    ap.add_argument("--enrich", help="Path to web3_summary.json to enrich")
    ap.add_argument("--output")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--classify-against-models", action="store_true",
                    help="F5: classify Solodit findings against threat_models/*.yaml")
    ap.add_argument("--suggest-new-models", action="store_true",
                    help="F5: cluster unmatched findings, suggest new threat_models")
    args = ap.parse_args()

    if args.classify_against_models or args.suggest_new_models:
        query = args.query or "vulnerability"
        results = search_solodit(query, args.limit if args.limit > 50 else 100)
        models = load_threat_models()
        print(f"[info] {len(results)} findings, {len(models)} threat_models loaded")

        if args.classify_against_models:
            classified = classify_against_models(results, models)
            for mid, hits in classified.items():
                if hits:
                    print(f"\n=== {mid} ({len(hits)} matches) ===")
                    for h in hits[:5]:
                        print(f"  [{h.get('severity', '?')}] {h.get('title', '')}")
                else:
                    print(f"\n=== {mid}: 0 matches ===")
            if args.output:
                Path(args.output).write_text(
                    json.dumps(classified, indent=2, ensure_ascii=False),
                    encoding="utf-8")
                print(f"\n[ok] {args.output}")

        if args.suggest_new_models:
            suggestions = suggest_new_models(results, models)
            print("\n=== Suggested new threat_models (5+ unmatched findings clustered) ===")
            for s in suggestions:
                print(f"  - keywords={s['keywords']} count={s['count']}")
                print(f"    → {s['suggestion']}")
        return

    if args.query:
        results = search_solodit(args.query, args.limit)
        out = json.dumps({"query": args.query, "results": results},
                         indent=2, ensure_ascii=False)
        if args.output:
            Path(args.output).write_text(out)
        print(out)
        return

    if args.enrich:
        path = Path(args.enrich)
        enriched = enrich_summary(path)
        out_path = Path(args.output) if args.output else path
        out_path.write_text(json.dumps(enriched, indent=2, ensure_ascii=False))
        match_count = sum(
            len(f.get("solodit_matches", [])) for f in enriched.get("findings", [])
        )
        print(f"[+] Enriched {len(enriched.get('findings', []))} findings, "
              f"{match_count} total Solodit matches")
        return

    ap.error("Need --query, --enrich, --classify-against-models, or --suggest-new-models")


if __name__ == "__main__":
    main()
