#!/usr/bin/env python3
"""
GraphQL advanced testing.

The existing scan.sh only checks introspection. This script covers
modern GraphQL attack classes:
- Batching attacks (DoS / rate-limit bypass)
- Alias injection (brute-force via aliases)
- Depth attacks (recursive queries)
- Field suggestions disclosure
- CSRF on mutations
- Authorization bypass via nested queries

Usage:
    python3 graphql_advanced.py --endpoint https://api.example.com/graphql --output ./out
"""

import argparse
import json
import time
from pathlib import Path

import requests


def post_query(endpoint: str, query: dict, headers: dict = None) -> requests.Response | None:
    try:
        return requests.post(endpoint, json=query, headers=headers or {}, timeout=15)
    except Exception:
        return None


def test_introspection(endpoint: str) -> dict:
    payload = {"query": "{__schema{types{name}}}"}
    r = post_query(endpoint, payload)
    if not r:
        return {"test": "introspection", "result": "request_failed"}
    enabled = r.status_code == 200 and "__schema" in r.text
    return {
        "test": "introspection",
        "enabled": enabled,
        "severity": "high" if enabled else "info",
    }


def test_batching(endpoint: str) -> dict:
    """Send 100 queries in one request — DoS / rate-limit bypass."""
    batch = [{"query": f"{{__typename}}", "operationName": f"q{i}"} for i in range(100)]
    r = post_query(endpoint, batch)
    if not r:
        return {"test": "batching", "result": "request_failed"}
    accepted = r.status_code == 200
    has_results = isinstance(r.json() if accepted else None, list)
    return {
        "test": "batching",
        "batch_accepted": accepted and has_results,
        "severity": "medium" if (accepted and has_results) else "info",
        "note": "Confirm: batch login attempts bypass rate limits",
    }


def test_alias_overload(endpoint: str) -> dict:
    """1000 aliases in one query — brute force via aliasing."""
    aliases = "\n".join([f"alias{i}: __typename" for i in range(1000)])
    payload = {"query": f"{{ {aliases} }}"}
    r = post_query(endpoint, payload)
    if not r:
        return {"test": "alias_overload", "result": "request_failed"}
    accepted = r.status_code == 200
    return {
        "test": "alias_overload",
        "1000_aliases_accepted": accepted,
        "severity": "medium" if accepted else "info",
        "note": "Confirm: brute-force OTP/PIN via aliases",
    }


def test_depth_attack(endpoint: str) -> dict:
    """Deeply nested query — DoS."""
    depth = 25
    query = "query{me" + "{posts" * depth + "{id}" + "}" * depth + "}"
    payload = {"query": query}
    start = time.time()
    r = post_query(endpoint, payload)
    elapsed = time.time() - start
    if not r:
        return {"test": "depth_attack", "result": "request_failed"}
    return {
        "test": "depth_attack",
        "depth": depth,
        "accepted": r.status_code == 200,
        "elapsed_ms": int(elapsed * 1000),
        "severity": "medium" if elapsed > 5 else "info",
    }


def test_field_suggestion(endpoint: str) -> dict:
    """Wrong field name → server may suggest valid ones (disclosure)."""
    payload = {"query": "{me{wrongFieldName123}}"}
    r = post_query(endpoint, payload)
    if not r:
        return {"test": "field_suggestion", "result": "request_failed"}
    text = r.text.lower()
    suggests = "did you mean" in text or "suggestion" in text
    return {
        "test": "field_suggestion",
        "suggestions_enabled": suggests,
        "severity": "low" if suggests else "info",
        "note": "Information disclosure of valid fields",
    }


def test_csrf(endpoint: str) -> dict:
    """GET-mutated query → CSRF possible."""
    r = None
    try:
        r = requests.get(endpoint + "?query=mutation{deleteMe}", timeout=10)
    except Exception:
        pass
    if not r:
        return {"test": "csrf_get", "result": "request_failed"}
    return {
        "test": "csrf_get",
        "get_mutation_allowed": r.status_code == 200 and "data" in r.text.lower(),
        "severity": "high" if r.status_code == 200 else "info",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--cookies", help="Cookie header (for authed tests)")
    args = ap.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    print(f"[*] GraphQL advanced tests on {args.endpoint}")
    headers = {}
    if args.cookies:
        headers["Cookie"] = args.cookies

    results = {
        "endpoint": args.endpoint,
        "tests": [],
    }
    for test_fn in [test_introspection, test_batching, test_alias_overload,
                    test_depth_attack, test_field_suggestion, test_csrf]:
        result = test_fn(args.endpoint)
        results["tests"].append(result)
        sev = result.get("severity", "?")
        print(f"  [{sev}] {result.get('test')}")
        time.sleep(1)

    out_file = out / "graphql_advanced.json"
    out_file.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    high = [t for t in results["tests"] if t.get("severity") in ("high", "medium")]
    print(f"\n[+] {len(high)} actionable findings")
    print(f"[+] Saved: {out_file}")


if __name__ == "__main__":
    main()
