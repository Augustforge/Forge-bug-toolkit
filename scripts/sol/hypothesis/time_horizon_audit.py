#!/usr/bin/env python3
"""
time_horizon_audit.py — Detector for broader class: ATTACKER-CONTROLLED TIME HORIZONS.

CLASS: where attacker can extend validity of their inputs or signed payloads
indefinitely. Not only durable nonces — also timestamp deadlines, oracle
TTLs, signed message expiry, admin operation timelocks.

Known instances of class:
  - Drift Protocol 2026 ($285M): durable nonces + zero-timelock multisig →
    pre-signed txs valid indefinitely → admin takeover
  - Generic: signed permits without deadline → infinite replay window
  - Oracle staleness without strict TTL → stale price exploitation
"""
import argparse
import json
import re
import sys
from pathlib import Path


DURABLE_NONCE_HINTS = re.compile(r"DurableNonce|advance_nonce_account|nonce_account", re.IGNORECASE)
DEADLINE_HINTS = re.compile(r"deadline|expires?_at|valid_until|expiry", re.IGNORECASE)
TIMELOCK_HINTS = re.compile(r"timelock|time_lock|delay_seconds|min_delay", re.IGNORECASE)
TIMESTAMP_CHECK_RE = re.compile(r"(?:Clock::get|clock\.unix_timestamp)\s*[<>=!]")
ZERO_DELAY_RE = re.compile(r"(?:min_delay|timelock|delay)\s*[=:]\s*0\b")
ORACLE_STALENESS_RE = re.compile(r"(?:price_age|staleness|last_updated|published_at)\s*[<>]")


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    findings = []
    lines = text.splitlines()

    for m in DURABLE_NONCE_HINTS.finditer(text):
        line_no = text[: m.start()].count("\n") + 1
        snippet = lines[line_no - 1].strip()[:140] if line_no <= len(lines) else ""
        findings.append({
            "class": "time_horizon_extension",
            "subclass": "durable_nonce_usage",
            "file": str(path),
            "line": line_no,
            "snippet": snippet,
            "advice": "Durable nonce makes pre-signed tx valid indefinitely. "
                      "Combined with multisig without timelock = Drift-class attack surface. "
                      "Verify revocation mechanism + timelock present.",
            "severity": "critical",
            "classification": "known_class",
        })

    for m in ZERO_DELAY_RE.finditer(text):
        line_no = text[: m.start()].count("\n") + 1
        snippet = lines[line_no - 1].strip()[:140] if line_no <= len(lines) else ""
        findings.append({
            "class": "time_horizon_extension",
            "subclass": "zero_timelock",
            "file": str(path),
            "line": line_no,
            "snippet": snippet,
            "advice": "Timelock/delay = 0 → admin ops execute immediately. "
                      "Combined with pre-signed approval = Drift-class attack surface.",
            "severity": "high",
            "classification": "known_class",
        })

    for m in DEADLINE_HINTS.finditer(text):
        line_no = text[: m.start()].count("\n") + 1
        context = text[max(0, m.start() - 200): m.end() + 200]
        if not TIMESTAMP_CHECK_RE.search(context):
            snippet = lines[line_no - 1].strip()[:140] if line_no <= len(lines) else ""
            findings.append({
                "class": "time_horizon_extension",
                "subclass": "deadline_no_check",
                "file": str(path),
                "line": line_no,
                "snippet": snippet,
                "advice": "Deadline field declared but no `Clock::get` enforcement found nearby. "
                          "Signed payload can be replayed after the deadline.",
                "severity": "medium",
                "classification": "novel_instance",
            })

    oracle_uses = re.findall(r"price|oracle|feed", text, re.IGNORECASE)
    has_staleness_check = bool(ORACLE_STALENESS_RE.search(text))
    if oracle_uses and not has_staleness_check:
        first_oracle = re.search(r"price|oracle|feed", text, re.IGNORECASE)
        if first_oracle:
            line_no = text[: first_oracle.start()].count("\n") + 1
            findings.append({
                "class": "time_horizon_extension",
                "subclass": "oracle_no_staleness",
                "file": str(path),
                "line": line_no,
                "advice": "Price/oracle references found, but no staleness check (publish time vs current time). "
                          "Stale oracle data can be exploited.",
                "severity": "high",
                "classification": "novel_instance",
            })

    return findings


def main():
    ap = argparse.ArgumentParser(description="Audit attacker-controlled time horizons")
    ap.add_argument("--target", required=True)
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    target = Path(args.target)
    files = [target] if target.is_file() and target.suffix == ".rs" else list(target.rglob("*.rs")) if target.is_dir() else []
    if not files:
        print(f"[!] No .rs files: {target}", file=sys.stderr)
        sys.exit(1)

    all_findings = []
    for f in files:
        if "/target/" in str(f).replace("\\", "/") or "/test" in str(f).replace("\\", "/").lower():
            continue
        all_findings.extend(scan_file(f))

    novel = [f for f in all_findings if f["classification"] == "novel_instance"]
    if not args.quiet:
        print(f"[+] Time horizon findings: {len(all_findings)} (novel: {len(novel)})")
        by_subclass = {}
        for f in all_findings:
            by_subclass[f["subclass"]] = by_subclass.get(f["subclass"], 0) + 1
        for k, v in by_subclass.items():
            print(f"  {k:30} {v}")

    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "time_horizon_findings.json").write_text(json.dumps(all_findings, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
