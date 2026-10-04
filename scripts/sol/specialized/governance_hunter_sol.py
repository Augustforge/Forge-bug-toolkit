#!/usr/bin/env python3
"""
governance_hunter_sol.py — Squads + governance flow hunter.

Targets (Drift 2026 + broader):
- Squads multisig threshold drift
- Durable nonce in admin flows
- Zero-timelock detection
- Multisig approval revocation
- Upgrade authority transitions
- Admin key rotation safety
"""
import argparse, json, re, sys
from pathlib import Path

CHECKS = [
    ("durable_nonce_admin", re.compile(r"DurableNonce|advance_nonce|nonce_authority"), "Durable nonce in governance flow → pre-signed tx valid indefinitely (Drift 2026)"),
    ("zero_timelock", re.compile(r"timelock\s*[:=]\s*0|delay_seconds\s*[:=]\s*0"), "Timelock = 0 → admin ops instant. Add minimum delay."),
    ("threshold_config", re.compile(r"threshold\s*[:=]\s*(\d+)"), "Multisig threshold — verify ratio to total signers"),
    ("admin_change_no_timelock", re.compile(r"set_admin|change_admin|transfer_authority"), "Admin transition — verify timelock + multi-step (propose → accept) flow"),
    ("upgrade_authority", re.compile(r"upgrade_authority|set_upgrade"), "Upgrade authority change — verify multisig + timelock + delay"),
    ("approval_no_revoke", re.compile(r"approve\s*\(|sign_proposal"), "Approval mechanism — verify revocation possible before execution"),
    ("squads_v3_compat", re.compile(r"squads_v3|SquadsMultisig"), "Squads v3 — verify migration to v4 (audited extensively)"),
]


def scan_file(path):
    try: text = path.read_text(encoding="utf-8", errors="ignore")
    except: return []
    out = []
    lines = text.splitlines()
    for cid, regex, advice in CHECKS:
        for m in regex.finditer(text):
            ln = text[:m.start()].count("\n") + 1
            snip = lines[ln-1].strip()[:140] if ln <= len(lines) else ""
            severity = "critical" if cid in ("durable_nonce_admin", "zero_timelock") else "high"
            classification = "known_class" if cid in ("durable_nonce_admin", "zero_timelock") else "novel_instance"
            out.append({
                "class": "governance_specialized", "subclass": cid,
                "file": str(path), "line": ln, "snippet": snip,
                "advice": advice, "severity": severity, "classification": classification,
            })
    return out


def main():
    ap = argparse.ArgumentParser(description="Solana governance hunter")
    ap.add_argument("--target", required=True); ap.add_argument("--output", default=None); ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    target = Path(args.target)
    files = [target] if target.is_file() and target.suffix == ".rs" else list(target.rglob("*.rs")) if target.is_dir() else []
    if not files: print("[!] No .rs", file=sys.stderr); sys.exit(1)
    all_f = []
    for f in files:
        if "/target/" in str(f).replace("\\", "/"): continue
        all_f.extend(scan_file(f))
    if not args.quiet: print(f"[+] Governance findings: {len(all_f)}")
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "governance_findings.json").write_text(json.dumps(all_f, indent=2), encoding="utf-8")

if __name__ == "__main__": main()
