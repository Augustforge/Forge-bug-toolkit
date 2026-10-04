#!/usr/bin/env python3
"""
pyth_lazer_deep.py — Deep analyzer for Pyth Lazer (2024) oracle integrations.

CONTEXT:
Pyth Lazer = new push-based oracle from Pyth Network (introduced 2024).
Differences from legacy Pyth Pull:
- New account layout `PriceFeedV2`
- Different staleness semantics — slot-based, not timestamp-based
- Authenticated price updates instead of continuous streaming
- New ed25519 signature verification stage (more crypto surface)
- New trust model: signer authority instead of feed-specific
- Different fallback semantics on stale/halt

DEEP CHECKS:
1. **Slot-based staleness threshold**: `slot - update_slot > MAX_DELAY_SLOTS` check
   - Default unsafe = 0 (no check)
   - Recommended = 200 (~80s)
   - Detection: find PriceFeedV2 reads, check for slot delta validation

2. **Signature authority pinning**: Lazer accepts updates signed by authority pubkey.
   Code must verify authority **stays the same** between deploys (admin rotation).

3. **Confidence interval handling**: Lazer reports confidence — different format from Pull.
   Code must use it (price ± conf bounds), not just price.

4. **Cross-update consistency**: between sequential price reads in same tx, slot
   must monotonically increase. Otherwise replay.

5. **Drift Protocol v2 integration class** (`pyth_lazer_oracle.rs`):
   - 2026 surface, fresh code post-audit
   - Our prior scan found `pyth_lazer_storage @ pyth_lazer_oracle.rs:154` as NOVEL
   - This script focuses on depth there

DETECTION PATTERNS:
- `pyth_lazer` imports
- `PriceFeedV2` struct usage
- `update_slot` field access
- `lazer_authority` references

CLASSIFICATION:
  - [known_class] = Drift v2 integration pattern, Lazer SDK default footguns
  - [novel_instance] = a new integration where the check is missing

Usage:
    python3 pyth_lazer_deep.py --target sessions/$TARGET/source
"""
import argparse
import json
import re
import sys
from pathlib import Path


LAZER_IMPORTS = [
    re.compile(r"use\s+pyth_lazer\b"),
    re.compile(r"PriceFeedV2|LazerPriceFeed|pyth_lazer_sdk"),
]
LAZER_STORAGE_PATTERNS = [
    re.compile(r"pyth_lazer_storage|lazer_state|lazer_authority"),
]

SLOT_STALENESS_PATTERNS = [
    re.compile(r"(?:Clock::get|clock)\.slot\s*[-=<>]\s*\w*[._]?update_slot|update_slot\s*[-+<>]\s*[Cc]lock"),
    re.compile(r"slot_delta|slots?_since_update|max_age_slots|MAX_DELAY_SLOTS"),
    re.compile(r"is_recent_slot|recent_slot_check|stale_slot_check"),
]

AUTHORITY_PIN_PATTERNS = [
    re.compile(r"lazer_authority\s*==\s*\w+|require_keys_eq!\s*\(\s*\w*lazer_authority"),
    re.compile(r"trusted_signer|authority_pin|pin_authority"),
]

CONFIDENCE_USE_PATTERNS = [
    re.compile(r"\.confidence\b|\.conf\b"),
    re.compile(r"price.*[-+].*confidence|confidence.*price"),
    re.compile(r"price_lower_bound|price_upper_bound|price_range"),
]

CROSS_UPDATE_PATTERNS = [
    re.compile(r"last_read_slot|prev_slot|previous_update_slot"),
    re.compile(r"slot\s*>\s*last_|require.*slot.*>.*last"),
]


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    if not any(p.search(text) for p in LAZER_IMPORTS + LAZER_STORAGE_PATTERNS):
        return []

    findings = []
    has_slot_check = any(p.search(text) for p in SLOT_STALENESS_PATTERNS)
    has_authority_pin = any(p.search(text) for p in AUTHORITY_PIN_PATTERNS)
    has_confidence_use = any(p.search(text) for p in CONFIDENCE_USE_PATTERNS)
    has_cross_update = any(p.search(text) for p in CROSS_UPDATE_PATTERNS)

    primary_match = None
    for pattern in LAZER_IMPORTS + LAZER_STORAGE_PATTERNS:
        m = pattern.search(text)
        if m:
            primary_match = m
            break

    if not primary_match:
        return findings

    line_no = text[: primary_match.start()].count("\n") + 1

    if not has_slot_check:
        findings.append({
            "class": "pyth_lazer_deep",
            "subclass": "missing_slot_staleness_check",
            "file": str(path),
            "line": line_no,
            "advice": "Pyth Lazer integration without slot-based staleness validation. "
                     "Pull Pyth used publish_time, Lazer uses update_slot. "
                     "Must check `clock.slot - update_slot < MAX_DELAY_SLOTS` (~200 slots ≈ 80s). "
                     "Without this, attacker submits stale signed price → manipulation.",
            "severity": "critical",
            "classification": "known_class",
            "broader_class": "lazer_staleness",
            "attack_template": "lazer_stale_price_submission",
        })

    if not has_authority_pin:
        findings.append({
            "class": "pyth_lazer_deep",
            "subclass": "missing_authority_pin",
            "file": str(path),
            "line": line_no,
            "advice": "Lazer accepts price updates signed by an authority. Code must verify authority key is hardcoded or pinned in state — not trusted from instruction args. Otherwise attacker submits self-signed price.",
            "severity": "critical",
            "classification": "novel_instance",
            "broader_class": "lazer_authority_trust",
            "attack_template": "lazer_authority_substitution",
        })

    if not has_confidence_use:
        findings.append({
            "class": "pyth_lazer_deep",
            "subclass": "ignoring_confidence_interval",
            "file": str(path),
            "line": line_no,
            "advice": "Price loaded but confidence is not used. Wide-confidence update = suspicious data (market disruption, liquidity void). Must reject OR use price ± conf bounds.",
            "severity": "high",
            "classification": "known_class",
            "broader_class": "lazer_confidence",
        })

    if not has_cross_update:
        findings.append({
            "class": "pyth_lazer_deep",
            "subclass": "no_slot_monotonic_check",
            "file": str(path),
            "line": line_no,
            "advice": "Multi-read of Lazer price in a single tx without slot monotonic check. "
                     "Attacker reorders signed updates → reads same/older slot twice as 'fresh'. Replay surface.",
            "severity": "medium",
            "classification": "novel_instance",
            "broader_class": "lazer_replay",
        })

    drift_pattern = re.search(r"pyth_lazer_storage\s*:", text)
    if drift_pattern:
        line_no_drift = text[: drift_pattern.start()].count("\n") + 1
        findings.append({
            "class": "pyth_lazer_deep",
            "subclass": "drift_v2_integration_surface",
            "file": str(path),
            "line": line_no_drift,
            "advice": "Drift Protocol-style Lazer integration detected (`pyth_lazer_storage` field). "
                     "Drift v2 had a governance surface here (peripheral incident context). "
                     "Verify: 1) lazer_storage authority pinned 2) update_slot validated 3) confidence used.",
            "severity": "high",
            "classification": "known_class",
            "broader_class": "drift_v2_lazer_pattern",
        })

    return findings


def main():
    ap = argparse.ArgumentParser(description="Deep analyzer Pyth Lazer integrations")
    ap.add_argument("--target", required=True)
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
        critical = [f for f in all_findings if f["severity"] == "critical"]
        high = [f for f in all_findings if f["severity"] == "high"]
        novel = [f for f in all_findings if f.get("classification") == "novel_instance"]
        print(f"[+] Scanned {len(files)} files. Pyth Lazer findings: {len(all_findings)}")
        print(f"    Critical: {len(critical)}")
        print(f"    High:     {len(high)}")
        print(f"    Novel:    {len(novel)}")

        for f in (critical + high)[:10]:
            sev = f["severity"].upper()
            cls = f.get("classification", "?")
            f_name = Path(f["file"]).name
            print(f"  [{sev:8}] [{cls}] {f['subclass']:38} @ {f_name}:{f['line']}")

    if args.output:
        out_dir = Path(args.output)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "pyth_lazer_findings.json").write_text(json.dumps(all_findings, indent=2))


if __name__ == "__main__":
    main()
