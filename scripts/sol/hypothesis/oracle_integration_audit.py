#!/usr/bin/env python3
"""
oracle_integration_audit.py — Audit Solana oracle integration safety.

Solana protocols depend on Pyth, Switchboard, Pyth Lazer, or custom oracles.
Each has specific footguns:

1. **Pyth (legacy / Pull)**:
   - Staleness: must check `price.publish_time` against `clock.unix_timestamp`
   - Confidence interval: `price.conf` should be bounded (e.g., < 1% of price)
   - Status: `price.status == Trading` else stale/halted
   - Multiple price feeds: aggregation/median needed for resilience

2. **Pyth Lazer** (2024 introduction):
   - New account layout — `PriceFeedV2` instead of PriceAccount
   - Different staleness semantics
   - Solana Drift v2 has Pyth Lazer integration (`pyth_lazer_oracle.rs`)

3. **Switchboard**:
   - `AggregatorAccountData.latest_confirmed_round.result`
   - History buffer: ensure result.std_deviation within bounds
   - On-Demand vs Streaming: different staleness models

4. **Custom oracles** (e.g. validator-set-derived prices):
   - Often weakest link
   - Verify identity of feed sources via PDA/Authority

DETECTION:
1. Find Pyth/Switchboard/Lazer imports
2. Trace where price/value is consumed
3. Check for staleness validation (publish_time vs clock)
4. Check for confidence/std_dev bounds
5. Check for halted-status detection
6. Check for multi-feed aggregation

CLASSIFICATION:
  - [known_class] = matches historical oracle manipulation exploit (Mango 2022, etc.)
  - [novel_instance] = oracle integration without one of the safety checks

USAGE:
    python3 oracle_integration_audit.py --target sessions/$TARGET/source
    python3 oracle_integration_audit.py --target ./src --output sessions/$TARGET/deep/hypothesis/
"""
import argparse
import json
import re
import sys
from pathlib import Path


PYTH_IMPORTS = [
    re.compile(r"use\s+pyth_sdk_solana"),
    re.compile(r"use\s+pyth_sdk"),
    re.compile(r"pyth_solana_receiver"),
    re.compile(r"pyth_lazer"),
]
SWITCHBOARD_IMPORTS = [
    re.compile(r"use\s+switchboard_v2"),
    re.compile(r"use\s+switchboard_on_demand"),
    re.compile(r"AggregatorAccountData"),
]

PRICE_LOAD_PATTERNS = {
    "pyth_load_price": re.compile(r"load_price\s*\(\s*&?\s*\w+"),
    "pyth_get_price_unchecked": re.compile(r"get_price_unchecked\s*\(\s*\)"),
    "pyth_get_price_no_older_than": re.compile(r"get_price_no_older_than"),
    "pyth_get_price_no_newer_than": re.compile(r"get_price_no_newer_than"),
    "switchboard_get_result": re.compile(r"latest_confirmed_round\.result|get_result\s*\(\s*\)"),
    "switchboard_std_dev": re.compile(r"std_deviation"),
}

STALENESS_CHECK_PATTERNS = [
    re.compile(r"publish_time"),
    re.compile(r"timestamp\s*[<>=]"),
    re.compile(r"clock\.unix_timestamp"),
    re.compile(r"slot.*-.*last"),
    re.compile(r"staleness|stale_threshold|MAX_AGE|max_age"),
    re.compile(r"get_price_no_older_than"),
    re.compile(r"is_recent|is_fresh"),
]

CONFIDENCE_CHECK_PATTERNS = [
    re.compile(r"\.conf\b"),
    re.compile(r"confidence|conf_interval"),
    re.compile(r"std_deviation"),
    re.compile(r"price.*conf.*\*|conf.*price.*<|conf.*\/.*price"),
]

HALT_CHECK_PATTERNS = [
    re.compile(r"PriceStatus::Trading|status\s*==\s*PriceStatus::Trading"),
    re.compile(r"is_trading|trading_status"),
    re.compile(r"\.status\b"),
]

AGGREGATION_PATTERNS = [
    re.compile(r"median|average|aggregate"),
    re.compile(r"multiple_feeds|feed_set|oracle_set"),
    re.compile(r"twap|TWAP"),
]


def detect_oracle_usage(text: str) -> dict:
    pyth_uses = sum(1 for p in PYTH_IMPORTS if p.search(text))
    sb_uses = sum(1 for p in SWITCHBOARD_IMPORTS if p.search(text))
    return {
        "pyth_imported": pyth_uses > 0,
        "switchboard_imported": sb_uses > 0,
        "pyth_lazer_imported": "pyth_lazer" in text,
    }


def find_price_loads(text: str) -> list[dict]:
    loads = []
    for category, pattern in PRICE_LOAD_PATTERNS.items():
        for m in pattern.finditer(text):
            line_no = text[: m.start()].count("\n") + 1
            loads.append({"category": category, "line": line_no, "snippet": m.group(0)})
    return loads


def check_safety_patterns(text: str, patterns: list, near_pos: int = -1, window: int = 1000) -> bool:
    if near_pos < 0:
        return any(p.search(text) for p in patterns)
    region = text[max(0, near_pos - window): near_pos + window]
    return any(p.search(region) for p in patterns)


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    findings = []

    usage = detect_oracle_usage(text)
    if not (usage["pyth_imported"] or usage["switchboard_imported"]):
        return findings

    loads = find_price_loads(text)
    if not loads:
        if usage["pyth_imported"] or usage["switchboard_imported"]:
            findings.append({
                "class": "oracle_integration",
                "subclass": "oracle_imported_but_no_loads",
                "file": str(path),
                "line": 1,
                "advice": "Oracle SDK imported but no price loads detected. Confirm via deeper trace.",
                "severity": "info",
                "classification": "novel_instance",
                "broader_class": "oracle_dependency_drift",
            })
        return findings

    has_global_staleness = check_safety_patterns(text, STALENESS_CHECK_PATTERNS)
    has_global_confidence = check_safety_patterns(text, CONFIDENCE_CHECK_PATTERNS)
    has_global_halt = check_safety_patterns(text, HALT_CHECK_PATTERNS)
    has_aggregation = check_safety_patterns(text, AGGREGATION_PATTERNS)

    for load in loads:
        load_pos = text.find(load["snippet"])
        local_staleness = check_safety_patterns(text, STALENESS_CHECK_PATTERNS, load_pos)
        local_confidence = check_safety_patterns(text, CONFIDENCE_CHECK_PATTERNS, load_pos)
        local_halt = check_safety_patterns(text, HALT_CHECK_PATTERNS, load_pos)

        unchecked = load["category"] in ("pyth_get_price_unchecked", "pyth_load_price")
        no_age = load["category"] not in ("pyth_get_price_no_older_than",)

        if unchecked and not (local_staleness or has_global_staleness):
            findings.append({
                "class": "oracle_integration",
                "subclass": "missing_staleness_check",
                "file": str(path),
                "line": load["line"],
                "snippet": load["snippet"],
                "advice": "Oracle price loaded via `get_price_unchecked` or `load_price` without staleness verification. "
                          "Stale price = manipulation surface (Mango 2022 class).",
                "severity": "critical",
                "classification": "known_class",
                "broader_class": "oracle_staleness_gap",
            })

        if not (local_confidence or has_global_confidence):
            findings.append({
                "class": "oracle_integration",
                "subclass": "missing_confidence_check",
                "file": str(path),
                "line": load["line"],
                "snippet": load["snippet"],
                "advice": "Price loaded without confidence interval validation. Wide-confidence price = suspicious data, must be rejected or confidence-bounded.",
                "severity": "high",
                "classification": "known_class",
                "broader_class": "oracle_confidence_gap",
            })

        if not (local_halt or has_global_halt) and usage["pyth_imported"]:
            findings.append({
                "class": "oracle_integration",
                "subclass": "missing_halt_check",
                "file": str(path),
                "line": load["line"],
                "snippet": load["snippet"],
                "advice": "Pyth price loaded without status check (Trading vs Halted/Unknown). Halted oracle = stale data, enables manipulation.",
                "severity": "high",
                "classification": "novel_instance",
                "broader_class": "oracle_status_gap",
            })

    if loads and not has_aggregation:
        findings.append({
            "class": "oracle_integration",
            "subclass": "single_feed_no_aggregation",
            "file": str(path),
            "line": loads[0]["line"],
            "advice": f"{len(loads)} price loads, no median/aggregate/TWAP pattern detected. Single-feed dependency = single point of failure.",
            "severity": "medium",
            "classification": "novel_instance",
            "broader_class": "oracle_resilience_gap",
        })

    if usage["pyth_lazer_imported"]:
        findings.append({
            "class": "oracle_integration",
            "subclass": "pyth_lazer_in_use",
            "file": str(path),
            "line": loads[0]["line"] if loads else 1,
            "advice": "Pyth Lazer (newer 2024 oracle) integration detected. Lazer has different staleness/account-layout semantics — manual review required. Drift v2 had recent surface area here.",
            "severity": "high",
            "classification": "novel_instance",
            "broader_class": "oracle_new_integration",
        })

    return findings


def main():
    ap = argparse.ArgumentParser(description="Audit Solana oracle integration safety")
    ap.add_argument("--target", required=True, help="Source dir or file")
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"[!] target not found: {target}", file=sys.stderr)
        sys.exit(1)

    files = list(target.rglob("*.rs")) if target.is_dir() else [target]
    all_findings = []
    for f in files:
        all_findings.extend(scan_file(f))

    if not args.quiet:
        print(f"[+] Scanned {len(files)} files. Oracle findings: {len(all_findings)}")
        critical = [f for f in all_findings if f["severity"] == "critical"]
        high = [f for f in all_findings if f["severity"] == "high"]
        novel = [f for f in all_findings if f.get("classification") == "novel_instance"]
        known = [f for f in all_findings if f.get("classification") == "known_class"]
        print(f"    Critical: {len(critical)}")
        print(f"    High:     {len(high)}")
        print(f"    Novel:    {len(novel)} (HIGH PRIORITY)")
        print(f"    Known:    {len(known)} (matches historical exploit pattern)")

        for f in critical[:10]:
            sev = f["severity"].upper()
            cls = f.get("classification", "?")
            f_path = Path(f["file"]).name
            print(f"  [{sev:8}] [{cls}] {f['subclass']:35} @ {f_path}:{f['line']}")

    if args.output:
        out_dir = Path(args.output)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "oracle_integration_findings.json").write_text(json.dumps(all_findings, indent=2))


if __name__ == "__main__":
    main()
