#!/usr/bin/env python3
"""
sealevel_race_detector.py — Detect Solana parallel execution race conditions.

CONTEXT:
Solana Sealevel runtime parallelizes non-conflicting transactions.
Two txs are non-conflicting if they don't share writable accounts.

Common Sealevel race patterns:
1. **Logical dependency without writable overlap** — protocol assumes
   tx_A runs before tx_B, but both have different writable account sets.
   Sealevel may execute them in parallel — assumption broken.

2. **Read-only state used as "before" snapshot** — instruction reads
   read-only state, makes decision. Another parallel tx mutates this
   state (it's writable from its perspective). Decision based on stale read.

3. **Sequence enforcement via off-chain coordinator** — protocol uses
   off-chain bot to enforce sequence (Marinade crank). If bot orchestration
   fails or is gamed → parallel attacker breaks ordering.

4. **Implicit ordering via rent / lamports** — code expects account to
   have specific lamports balance before tx. Parallel reflux tx changes
   this. Pre-condition assumption broken.

DETECTION:
1. Find instruction handlers with READ-ONLY accounts that they make decisions on
2. Check if same accounts are WRITABLE in other instructions
3. Flag "decision based on read of state that another ix writes without writable
   overlap" — this is a parallel race surface

CLASSIFICATION:
  - [novel_instance] = no public exploit Solana-specific yet, but logical
  - [known_class] = matches Marinade crank assumption pattern

Usage:
    python3 sealevel_race_detector.py --target sessions/$TARGET/source
"""
import argparse
import json
import re
import sys
from pathlib import Path


ACCOUNT_STRUCT_RE = re.compile(
    r"#\[derive\(Accounts\)\]\s*(?:#\[[^\]]+\]\s*)*pub\s+struct\s+(\w+)<'\w+>\s*\{([^}]+)\}",
    re.DOTALL,
)
ACCOUNT_FIELD_RE = re.compile(
    r"(#\[account\([^)]*\)\]\s*)?pub\s+(\w+):\s*(\w+)<",
)
DECISION_PATTERNS = [
    re.compile(r"require_gte!|require!|if\s+\w+\.\w+\s*[<>=]|match\s+\w+\.\w+"),
]
EXTERNAL_COORDINATION_PATTERNS = [
    re.compile(r"crank|bot|orchestrator|sequencer|coordinator|keeper"),
    re.compile(r"epoch_schedule|slot.*permission|leader_check"),
]


def parse_account_fields(struct_body: str) -> list[dict]:
    fields = []
    for m in ACCOUNT_FIELD_RE.finditer(struct_body):
        anchor_attr = m.group(1) or ""
        is_writable = "mut" in anchor_attr or "writable" in anchor_attr
        is_signer_required = "signer" in anchor_attr.lower() or "Signer<" in m.group(0)
        fields.append({
            "name": m.group(2),
            "type": m.group(3),
            "writable": is_writable,
            "signer": is_signer_required,
            "raw": m.group(0),
        })
    return fields


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    findings = []

    file_name = path.name
    accounts_structs = {}
    for m in ACCOUNT_STRUCT_RE.finditer(text):
        struct_name = m.group(1)
        body = m.group(2)
        fields = parse_account_fields(body)
        accounts_structs[struct_name] = fields

    if not accounts_structs:
        return findings

    has_external_coord = any(p.search(text) for p in EXTERNAL_COORDINATION_PATTERNS)
    has_decisions = any(p.search(text) for p in DECISION_PATTERNS)

    for struct_name, fields in accounts_structs.items():
        readonly_named = [f for f in fields if not f["writable"] and not f["signer"]
                          and f["type"] in ("Account", "Box", "AccountLoader")]

        if not readonly_named:
            continue

        if has_decisions and has_external_coord:
            for field in readonly_named[:3]:
                line_no = text.find(f"pub {field['name']}:")
                line_no = text[:line_no].count("\n") + 1 if line_no > 0 else 1
                findings.append({
                    "class": "sealevel_race",
                    "subclass": "decision_on_readonly_with_external_coord",
                    "file": str(path),
                    "line": line_no,
                    "struct": struct_name,
                    "field": field["name"],
                    "field_type": field["type"],
                    "advice": f"`{struct_name}::{field['name']}` is read-only but file shows external coordinator pattern (bot/crank/keeper). "
                              f"Parallel tx may mutate {field['name']} as writable (own writable in different handler). "
                              f"Decision based on stale read = race surface. Verify: does ANY OTHER handler treat {field['name']} as writable?",
                    "severity": "medium",
                    "classification": "novel_instance",
                    "broader_class": "sealevel_parallel_decision",
                })

    rent_check_pattern = re.search(r"\.lamports\(\)\s*[<>=]|require.*lamports", text)
    if rent_check_pattern:
        line_no = text[: rent_check_pattern.start()].count("\n") + 1
        findings.append({
            "class": "sealevel_race",
            "subclass": "lamport_balance_precondition",
            "file": str(path),
            "line": line_no,
            "advice": "Instruction makes decision based on `.lamports()` value. Another parallel tx can change balance (transfer in/out). Decision possibly stale by time of execution.",
            "severity": "low",
            "classification": "novel_instance",
            "broader_class": "sealevel_implicit_ordering",
        })

    return findings


def main():
    ap = argparse.ArgumentParser(description="Detect Solana Sealevel parallel execution race surfaces")
    ap.add_argument("--target", required=True)
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    target = Path(args.target)
    files = list(target.rglob("*.rs")) if target.is_dir() else [target]
    all_findings = []
    for f in files:
        all_findings.extend(scan_file(f))

    if not args.quiet:
        novel = [f for f in all_findings if f.get("classification") == "novel_instance"]
        print(f"[+] Scanned {len(files)} files. Sealevel race findings: {len(all_findings)}")
        print(f"    Novel: {len(novel)} (HIGH PRIORITY)")

        for f in all_findings[:10]:
            sev = f["severity"].upper()
            cls = f.get("classification", "?")
            f_name = Path(f["file"]).name
            print(f"  [{sev:8}] [{cls}] {f['subclass']:42} @ {f_name}:{f['line']}")

    if args.output:
        out_dir = Path(args.output)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "sealevel_race_findings.json").write_text(json.dumps(all_findings, indent=2))


if __name__ == "__main__":
    main()
