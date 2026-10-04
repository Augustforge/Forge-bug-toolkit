#!/usr/bin/env python3
"""
Self-improving Knowledge Base.

Toolkit personalizes itself based on the researcher's verified findings.
Each confirmed bug → entry in KB → boost confidence on similar future patterns.
Each false positive → reduce weight.
Each accepted bounty → strong signal pattern works in this niche.

Storage: ~/.bbt/kb/findings.jsonl (append-only)

Operations:
- record       — add a new verified finding to the KB
- record-fp    — add a false positive
- record-paid  — mark a bounty as paid + amount
- search       — find similar patterns in the KB
- weights      — print current confidence multipliers per (vuln_type, target_kind)
- suggest      — based on history, suggest custom Slither detectors
- stats        — show overall learning statistics

Usage:
    python3 _knowledge_base.py record --finding-id F003 --session sessions/example.com
    python3 _knowledge_base.py search --vuln reentrancy --target-kind defi
    python3 _knowledge_base.py weights
    python3 _knowledge_base.py suggest
"""

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

KB_DIR = Path.home() / ".bbt" / "kb"
KB_DIR.mkdir(parents=True, exist_ok=True)
KB_FILE = KB_DIR / "findings.jsonl"
WEIGHTS_FILE = KB_DIR / "weights.json"
TM_FILE = KB_DIR / "threat_models.jsonl"


def append(entry: dict):
    with KB_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_all() -> list[dict]:
    if not KB_FILE.exists():
        return []
    return [json.loads(l) for l in KB_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_finding_from_session(session_dir: Path, finding_id: str) -> dict:
    for fname in ["scan_summary.json", "web3_summary.json"]:
        f = session_dir / fname
        if not f.exists():
            continue
        try:
            data = json.loads(f.read_text())
            for finding in data.get("findings", []):
                if finding.get("id") == finding_id:
                    return finding
        except Exception:
            pass
    return {}


def detect_target_kind(session_dir: Path) -> str:
    """Heuristic: defi-lending / amm / nft / web2 / cms / api / etc."""
    for fname in ["fingerprint_summary.json", "fetch_summary.json"]:
        f = session_dir / fname
        if not f.exists():
            continue
        try:
            data = json.loads(f.read_text())
            text = json.dumps(data).lower()
            if any(k in text for k in ["uniswap", "amm", "swap"]):
                return "defi-amm"
            if any(k in text for k in ["aave", "compound", "lend", "borrow"]):
                return "defi-lending"
            if any(k in text for k in ["nft", "erc721", "erc1155"]):
                return "nft"
            if any(k in text for k in ["bridge", "layerzero", "wormhole"]):
                return "bridge"
            if any(k in text for k in ["wordpress", "drupal", "magento"]):
                return "cms"
            if "api" in text:
                return "web2-api"
        except Exception:
            pass
    return "unknown"


def cmd_record(args):
    session = Path(args.session)
    finding = load_finding_from_session(session, args.finding_id)
    if not finding:
        sys.exit(f"Finding {args.finding_id} not found in {session}")
    target_kind = detect_target_kind(session)
    entry = {
        "kb_id": f"kb_{int(time.time() * 1000)}",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "verified",
        "session": str(session),
        "target_kind": target_kind,
        "vulnerability": finding.get("vulnerability"),
        "severity": finding.get("severity"),
        "swc_id": finding.get("swc_id"),
        "tools_flagged": finding.get("tools_flagged", []),
        "finding_excerpt": (finding.get("description") or "")[:300],
    }
    append(entry)
    print(f"[+] Recorded verified finding {entry['kb_id']}")
    print(f"    Vuln: {entry['vulnerability']} | Target: {target_kind}")


def cmd_record_fp(args):
    entry = {
        "kb_id": f"kb_{int(time.time() * 1000)}",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "false_positive",
        "vulnerability": args.vuln,
        "tool": args.tool,
        "reason": args.reason or "",
    }
    append(entry)
    print(f"[+] Recorded FP {entry['kb_id']}")


def cmd_record_paid(args):
    entries = read_all()
    target = next((e for e in entries if e.get("kb_id") == args.kb_id), None)
    if not target:
        sys.exit(f"KB entry {args.kb_id} not found")
    paid_entry = {
        **target,
        "kb_id": f"{target['kb_id']}_paid",
        "status": "paid",
        "bounty_amount_usd": args.amount,
        "platform": args.platform,
        "paid_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    append(paid_entry)
    print(f"[+] Marked {args.kb_id} as paid: ${args.amount} on {args.platform}")


def cmd_search(args):
    entries = read_all()
    matches = []
    for e in entries:
        if args.vuln and args.vuln.lower() not in (e.get("vulnerability") or "").lower():
            continue
        if args.target_kind and args.target_kind != e.get("target_kind"):
            continue
        if args.status and args.status != e.get("status"):
            continue
        matches.append(e)
    print(json.dumps(matches[-args.limit:], indent=2, ensure_ascii=False))
    print(f"\n[+] {len(matches)} matches", file=sys.stderr)


def compute_weights(entries: list[dict]) -> dict:
    """Confidence weights per (vuln_type, target_kind)."""
    verified = Counter()
    fps = Counter()
    paid_amount = defaultdict(float)

    for e in entries:
        vuln = e.get("vulnerability", "unknown")
        target = e.get("target_kind", "unknown")
        key = f"{vuln}::{target}"
        if e.get("status") == "verified":
            verified[key] += 1
        elif e.get("status") == "false_positive":
            fps[key] += 1
        elif e.get("status") == "paid":
            paid_amount[key] += e.get("bounty_amount_usd", 0) or 0
            verified[key] += 1

    weights = {}
    for key in set(verified) | set(fps):
        v = verified[key]
        f = fps[key]
        total = v + f
        if total < 1:
            continue
        confirm_rate = v / total
        money = paid_amount[key]
        weight = 1.0 + (confirm_rate - 0.5) * 0.6  # 0.7 - 1.3 base range
        if money > 0:
            weight *= 1 + min(money / 10_000, 1.0) * 0.5
        weights[key] = round(weight, 3)
    return weights


def cmd_weights(args):
    entries = read_all()
    weights = compute_weights(entries)
    WEIGHTS_FILE.write_text(json.dumps(weights, indent=2, ensure_ascii=False))
    print(json.dumps(weights, indent=2, ensure_ascii=False))
    print(f"\n[+] Saved to {WEIGHTS_FILE}", file=sys.stderr)


def cmd_suggest(args):
    entries = read_all()
    by_pattern = Counter()
    for e in entries:
        if e.get("status") in ("verified", "paid"):
            key = (e.get("vulnerability"), e.get("target_kind"))
            by_pattern[key] += 1

    suggestions = []
    for (vuln, target), count in by_pattern.most_common():
        if count >= 3:
            suggestions.append({
                "vulnerability": vuln,
                "target_kind": target,
                "occurrences": count,
                "recommendation": (
                    f"Custom Slither detector or checklist for {vuln} "
                    f"in context {target} — found {count} times. "
                    f"Create `scripts/web3/detectors/personal_{vuln.replace('-', '_')}_{target.replace('-', '_')}.py`"
                ),
            })

    if not suggestions:
        print("[i] Not enough data yet — keep hunting, the KB is accumulating")
    else:
        print(json.dumps(suggestions, indent=2, ensure_ascii=False))
        print(f"\n[+] {len(suggestions)} suggestions", file=sys.stderr)


def cmd_stats(args):
    entries = read_all()
    if not entries:
        print("[i] KB empty")
        return
    by_status = Counter(e.get("status") for e in entries)
    by_vuln = Counter(e.get("vulnerability") for e in entries
                      if e.get("status") in ("verified", "paid"))
    by_target = Counter(e.get("target_kind") for e in entries)
    total_paid = sum(e.get("bounty_amount_usd", 0) or 0 for e in entries
                     if e.get("status") == "paid")

    print(f"Total entries:      {len(entries)}")
    print(f"By status:          {dict(by_status)}")
    print(f"Total bounty paid:  ${total_paid:,.0f}")
    print(f"\nTop verified vulns:")
    for vuln, count in by_vuln.most_common(10):
        print(f"  {vuln}: {count}")
    print(f"\nBy target kind:")
    for target, count in by_target.most_common():
        print(f"  {target}: {count}")


def cmd_record_threat_model(args):
    """Map a case (URL or finding-id) to a threat-model YAML id."""
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "case": args.case,
        "model_id": args.model,
        "note": args.note or "",
    }
    with TM_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[ok] recorded case={args.case} → model={args.model}")
    print(f"[ok] file: {TM_FILE}")


def cmd_promote_to_findings_db(args):
    """Bridge: promote a KB finding into findings_db with structured record."""
    import subprocess
    repo_root = Path(__file__).resolve().parent.parent
    add_finding_py = repo_root / "scripts" / "web3" / "findings_db" / "add_finding.py"
    if not add_finding_py.exists():
        print(f"[err] add_finding.py not found at {add_finding_py}", file=sys.stderr)
        sys.exit(1)

    # Verify kb_id exists in KB
    entries = read_all()
    kb_entry = next((e for e in entries if e.get("kb_id") == args.kb_id), None)
    if not kb_entry:
        print(f"[err] KB entry {args.kb_id} not found", file=sys.stderr)
        sys.exit(1)

    severity = args.severity or kb_entry.get("severity", "medium").lower()
    cls = args.cls or kb_entry.get("vulnerability", "unknown")
    text = args.text or kb_entry.get("finding_excerpt", "") or f"Promoted from KB entry {args.kb_id}"

    cmd = ["python3", str(add_finding_py), "--kb-id", args.kb_id,
           "--severity", severity, "--class", cls, "--text", text]
    if args.threat_models:
        cmd.extend(["--threat-models", args.threat_models])
    if args.auto_review:
        cmd.append("--auto-review")
    print(f"[run] {' '.join(cmd[:6])} ... [text:{len(text)} chars]")
    sys.exit(subprocess.call(cmd))


def cmd_apply_threat_models(args):
    """Convenience wrapper — invokes scripts/web3/threat_models/apply.py."""
    import subprocess
    repo_root = Path(__file__).resolve().parent.parent
    apply_py = repo_root / "scripts" / "web3" / "threat_models" / "apply.py"
    if not apply_py.exists():
        print(f"[err] apply.py not found at {apply_py}", file=sys.stderr)
        sys.exit(1)
    cmd = ["python3", str(apply_py), "--target", args.target]
    if args.quick:
        cmd.append("--quick")
    if args.protocol_class:
        cmd.extend(["--protocol-class", args.protocol_class])
    if args.tags:
        cmd.extend(["--tags", args.tags])
    if args.output:
        cmd.extend(["--output", args.output])
    print(f"[run] {' '.join(cmd)}")
    sys.exit(subprocess.call(cmd))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("record")
    p.add_argument("--finding-id", required=True)
    p.add_argument("--session", required=True)

    p = sub.add_parser("record-fp")
    p.add_argument("--vuln", required=True)
    p.add_argument("--tool", required=True)
    p.add_argument("--reason")

    p = sub.add_parser("record-paid")
    p.add_argument("--kb-id", required=True)
    p.add_argument("--amount", type=float, required=True)
    p.add_argument("--platform", required=True)

    p = sub.add_parser("search")
    p.add_argument("--vuln")
    p.add_argument("--target-kind")
    p.add_argument("--status")
    p.add_argument("--limit", type=int, default=20)

    sub.add_parser("weights")
    sub.add_parser("suggest")
    sub.add_parser("stats")

    p = sub.add_parser("record-threat-model", help="Map a case (URL or finding-id) to a threat-model YAML id")
    p.add_argument("--case", required=True, help="Case identifier (writeup URL or finding-id)")
    p.add_argument("--model", required=True, help="threat_model id (matches YAML id field)")
    p.add_argument("--note", help="Optional note")

    p = sub.add_parser("apply-threat-models", help="Run threat_models/apply.py on a session")
    p.add_argument("--target", required=True, help="Session dir (sessions/$TARGET)")
    p.add_argument("--quick", action="store_true", help="Filter severity_floor >= medium")
    p.add_argument("--protocol-class")
    p.add_argument("--tags", help="Comma-separated tags")
    p.add_argument("--output", help="Override output path")

    p = sub.add_parser("promote", help="Bridge KB finding → findings_db with pre-review")
    p.add_argument("--kb-id", required=True, help="KB entry to promote")
    p.add_argument("--to", required=True, choices=["findings_db"], help="Target DB")
    p.add_argument("--severity", choices=["low", "medium", "high", "critical"])
    p.add_argument("--class", dest="cls", help="Override class (default: vuln type from KB)")
    p.add_argument("--text", help="Override text (default: KB excerpt)")
    p.add_argument("--threat-models", help="Comma-separated threat_model IDs to link")
    p.add_argument("--auto-review", action="store_true", help="Auto-invoke peer_review after promote")

    args = ap.parse_args()

    cmd_map = {
        "record": cmd_record, "record-fp": cmd_record_fp, "record-paid": cmd_record_paid,
        "search": cmd_search, "weights": cmd_weights, "suggest": cmd_suggest,
        "stats": cmd_stats,
        "record-threat-model": cmd_record_threat_model,
        "apply-threat-models": cmd_apply_threat_models,
        "promote": cmd_promote_to_findings_db,
    }
    cmd_map[args.cmd](args)


if __name__ == "__main__":
    main()
