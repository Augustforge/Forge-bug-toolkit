#!/usr/bin/env python3
"""
failure_analysis.py — Classify rejected/disputed bounty reports, grow
failure_modes.md corpus, detect recurring patterns.

Usage:
  python3 failure_analysis.py classify --reason "Already disclosed in audit" --finding-id F003
  python3 failure_analysis.py classify --crm-id R007                          # auto-load from CRM
  python3 failure_analysis.py recurring                                       # find 3+ pattern occurrences
  python3 failure_analysis.py list                                            # show all entries

Storage: scripts/_methodology/failure_modes.md (markdown, append-only)
"""
import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

THIS_DIR = Path(__file__).parent
FAILURES_MD = THIS_DIR / "failure_modes.md"
REPO_ROOT = THIS_DIR.parent.parent
CRM_FILE = REPO_ROOT / "sessions" / "_crm" / "reports.jsonl"

CLASSIFICATION_RULES = [
    ("already-known", [
        r"\balready\s+(known|disclosed|reported|patched|fixed)\b",
        r"\bduplicate\s+of\s+(audit|disclosure|finding)\b",
        r"\bin\s+(the\s+)?audit\s+report\b",
    ]),
    ("intended-behavior", [
        r"\bintended\s+(behavior|behaviour|design)\b",
        r"\bby\s+design\b",
        r"\bworking\s+as\s+intended\b",
        r"\bnot\s+a\s+(bug|vulnerability)\b",
    ]),
    ("out-of-scope", [
        r"\bout\s+of\s+scope\b",
        r"\bnot\s+in\s+scope\b",
        r"\bnot\s+covered\s+by\s+(the\s+)?(program|bounty)\b",
    ]),
    ("insufficient-PoC", [
        r"\bno\s+(working\s+)?(PoC|proof[\-\s]of[\-\s]concept)\b",
        r"\bunable\s+to\s+reproduce\b",
        r"\bproof\s+of\s+concept\s+(missing|required|insufficient)\b",
    ]),
    ("not-exploitable", [
        r"\bnot\s+exploitable\b",
        r"\bno\s+(real|actual)\s+(impact|exploit|attack)\b",
        r"\btheoretical\b",
    ]),
    ("duplicate", [
        r"\bduplicate\b",
        r"\bsame\s+as\s+(report|submission)\s+\d+\b",
    ]),
    ("severity-downgrade", [
        r"\bseverity\s+(downgrade|adjusted|reduced|lowered)\b",
        r"\b(claimed|reported)\s+as\s+\w+\s+but\s+actually\s+\w+\b",
    ]),
]


def classify_reason(text: str) -> str:
    """Match reason text against classification rules. Returns code or 'unknown'."""
    t = text.lower()
    for code, patterns in CLASSIFICATION_RULES:
        for p in patterns:
            if re.search(p, t):
                return code
    return "unknown"


def load_crm_report(crm_id: str) -> dict | None:
    if not CRM_FILE.exists():
        return None
    for line in CRM_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
            if r.get("id") == crm_id:
                return r
        except Exception:
            continue
    return None


def parse_existing_entries() -> list[dict]:
    """Re-parse failure_modes.md entries section to detect recurring."""
    if not FAILURES_MD.exists():
        return []
    text = FAILURES_MD.read_text(encoding="utf-8")
    if "## Entries" not in text:
        return []
    body = text.split("## Entries", 1)[1]
    entries = []
    for block in re.split(r"\n###\s+", body):
        if not block.strip() or block.lstrip().startswith("<!"):
            continue
        d = {}
        for line in block.splitlines():
            m = re.match(r"-\s+\*\*(\w[\w\-\s]*)\*\*:?\s*(.*)", line.strip())
            if m:
                d[m.group(1).lower().strip().replace(" ", "_")] = m.group(2).strip()
        if d:
            entries.append(d)
    return entries


def append_entry(entry: dict) -> None:
    """Append a classified failure entry to failure_modes.md."""
    if not FAILURES_MD.exists():
        FAILURES_MD.write_text("# Failure Modes Log\n\n## Entries\n\n", encoding="utf-8")
    section = []
    title = entry.get("title") or f"{entry.get('classification', 'unknown')} — {entry.get('timestamp', '')}"
    section.append(f"### {title}")
    for key in ["classification", "crm_id", "finding_id", "target", "reason", "root_cause_class", "lesson"]:
        v = entry.get(key)
        if v:
            section.append(f"- **{key.replace('_', ' ')}**: {v}")
    section.append(f"- **timestamp**: {entry.get('timestamp', '')}")
    section.append("")
    with FAILURES_MD.open("a", encoding="utf-8") as f:
        f.write("\n".join(section) + "\n")


def cmd_classify(args):
    reason_text = args.reason or ""
    crm_data = None
    if args.crm_id:
        crm_data = load_crm_report(args.crm_id)
        if not crm_data:
            print(f"[err] CRM report {args.crm_id} not found", file=sys.stderr)
            sys.exit(1)
        reason_text = reason_text or crm_data.get("status_reason", "") or crm_data.get("notes", "")

    if not reason_text:
        print("[err] need --reason text or --crm-id with status_reason", file=sys.stderr)
        sys.exit(1)

    classification = classify_reason(reason_text)
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "classification": classification,
        "reason": reason_text[:300],
        "crm_id": args.crm_id or "",
        "finding_id": args.finding_id or (crm_data or {}).get("finding") or "",
        "target": (crm_data or {}).get("target") or args.target or "",
        "root_cause_class": args.root_cause_class or "",
        "lesson": args.lesson or "",
    }
    append_entry(entry)
    print(f"[ok] classified as: {classification}")
    print(f"[ok] appended to: {FAILURES_MD}")
    if classification == "unknown":
        print("[hint] classification = unknown; rerun with --root-cause-class and --lesson for manual entry")


def cmd_recurring(args):
    entries = parse_existing_entries()
    if not entries:
        print("[i] failure_modes.md has no entries yet")
        return
    by_class = Counter(e.get("classification", "?") for e in entries)
    by_root = Counter(e.get("root_cause_class", "") for e in entries if e.get("root_cause_class"))

    print(f"Total entries: {len(entries)}")
    print("\nBy classification:")
    for k, n in by_class.most_common():
        marker = " ⚠️ RECURRING (≥3)" if n >= 3 else ""
        print(f"  {k}: {n}{marker}")

    if by_root:
        print("\nBy root_cause_class (manually-tagged):")
        for k, n in by_root.most_common():
            marker = " ⚠️ RECURRING (≥3)" if n >= 3 else ""
            print(f"  {k}: {n}{marker}")

    print("\nRecommendations for recurring patterns:")
    for k, n in by_class.most_common():
        if n < 3:
            continue
        rec = {
            "already-known": "Add mandatory Solodit search before submission. Update threat_intel.md with patterns this protocol's audit covered.",
            "intended-behavior": "Read project's OWN tests before submission. Update relevant checklist with an 'is this in tests?' check.",
            "out-of-scope": "Auto-load Immunefi scope in the J-2 phase via immunefi_scope.py. Block submission if out of scope.",
            "insufficient-PoC": "J5 (fork PoC) is a mandatory phase gate. Do not submit without a working test.",
            "not-exploitable": "Adversarial-actor prompt mandatory in J0 (bonded_actor_threat / read_as_attacker).",
            "duplicate": "Add exploit_race_monitor pre-submission check. Submit faster.",
            "severity-downgrade": "Auto-fit severity calibration per platform (Immunefi vs HackerOne vs Sherlock).",
        }.get(k, "Manual review needed.")
        print(f"  → {k}: {rec}")


def cmd_list(args):
    entries = parse_existing_entries()
    if not entries:
        print("[i] empty")
        return
    for i, e in enumerate(entries, 1):
        print(f"{i}. [{e.get('classification', '?')}] {e.get('crm_id', '')} {e.get('finding_id', '')} — {e.get('reason', '')[:80]}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("classify", help="Classify a rejection reason")
    p.add_argument("--reason", help="Free text rejection reason")
    p.add_argument("--crm-id", help="CRM report id (loads from sessions/_crm/reports.jsonl)")
    p.add_argument("--finding-id")
    p.add_argument("--target")
    p.add_argument("--root-cause-class", help="Manual tag: e.g., 'tss_validator_extraction', 'oracle_lies'")
    p.add_argument("--lesson", help="Free-text lesson to record")

    sub.add_parser("recurring", help="Show recurring patterns + recommendations")
    sub.add_parser("list", help="List all entries")

    args = ap.parse_args()
    {"classify": cmd_classify, "recurring": cmd_recurring, "list": cmd_list}[args.cmd](args)


if __name__ == "__main__":
    main()
