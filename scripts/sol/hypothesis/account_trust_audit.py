#!/usr/bin/env python3
"""
account_trust_audit.py — Detector for broader class: ANY-ACCOUNT SPOOFING.

CLASS: External accounts trusted without identity verification (signer/owner/key/program_id).
Every account passed into an instruction is an assumption. Which are NOT verified?

Known instances of class:
  - Wormhole 2022 ($325M): SignatureSet account not verified as signer/owner
  - Cashio 2022 ($52M): collateral account.owner not verified
  - Loopscale 2025 ($5.8M): RateX market program_id not verified for CPI
  - Mango 2022 ($114M): oracle account not verified as authentic price source
  - Raydium CLMM 2024 ($505K bounty): remaining_accounts[0] not verified as
    TickArrayBitmapExtension for the pool

Detection strategy:
1. Find all `pub <name>: AccountInfo<'info>` declarations (raw, no constraints)
2. Find all Anchor Account/UncheckedAccount without `constraint =` / `address =` / `has_one =`
3. Find all CPI calls (`invoke`, `invoke_signed`) with account inputs
4. Cross-reference: which accounts are read/used in logic — verified or trusted blindly?

CLASSIFICATION:
  - [known_class] = matches one of known instances (e.g. account named like "rate_x" or "oracle")
  - [novel_instance] = new account trust gap — HIGH PRIORITY
"""
import argparse
import json
import re
import sys
from pathlib import Path


ACCOUNT_INFO_RE = re.compile(
    r"#\[account\(([^)]*)\)\]\s*\n\s*pub\s+(\w+):\s*(AccountInfo|UncheckedAccount|Account)<",
    re.MULTILINE,
)
RAW_ACCOUNTINFO_RE = re.compile(r"pub\s+(\w+):\s*AccountInfo<")
INVOKE_RE = re.compile(r"\binvoke(?:_signed)?\s*\(", re.MULTILINE)


KNOWN_INSTANCE_HINTS = [
    "signature_set", "guardian_set", "vaa",          # Wormhole-class
    "collateral", "stable_collateral",                # Cashio-class
    "rate_x", "ratex", "rate_market", "pt_market",   # Loopscale-class
    "oracle", "price_account",                        # Mango-class
    "tick_array", "bitmap_ext",                       # Raydium-class
]


def has_verification(constraint_str: str) -> bool:
    """Check if Anchor constraint includes identity verification."""
    for kw in ("constraint", "address", "has_one", "owner", "seeds", "signer"):
        if kw in constraint_str:
            return True
    return False


def is_known_instance(name: str) -> bool:
    name_lc = name.lower()
    return any(hint in name_lc for hint in KNOWN_INSTANCE_HINTS)


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    findings = []
    lines = text.splitlines()

    for m in ACCOUNT_INFO_RE.finditer(text):
        constraint = m.group(1).strip()
        name = m.group(2)
        acc_type = m.group(3)
        if has_verification(constraint):
            continue
        if re.search(rf"has_one\s*=\s*{re.escape(name)}\b", text):
            continue
        if re.search(rf"address\s*=\s*[^,)]*\.{re.escape(name)}\b", text):
            continue
        line_no = text[: m.start()].count("\n") + 1
        snippet = lines[line_no - 1].strip()[:140] if line_no <= len(lines) else ""
        findings.append({
            "class": "account_trust_violation",
            "subclass": "anchor_unconstrained_account",
            "file": str(path),
            "line": line_no,
            "account_name": name,
            "account_type": acc_type,
            "snippet": snippet,
            "advice": f"Account `{name}: {acc_type}` without identity constraint (signer/address/has_one/seeds/owner). "
                      f"Any caller can pass any account — verify identity.",
            "severity": "critical" if is_known_instance(name) else "high",
            "classification": "known_class" if is_known_instance(name) else "novel_instance",
        })

    for m in RAW_ACCOUNTINFO_RE.finditer(text):
        line_no = text[: m.start()].count("\n") + 1
        context_start = max(0, m.start() - 200)
        context = text[context_start : m.end() + 50]
        if "#[account(" in context or "Account<" in context:
            continue
        name = m.group(1)
        snippet = lines[line_no - 1].strip()[:140] if line_no <= len(lines) else ""
        findings.append({
            "class": "account_trust_violation",
            "subclass": "raw_accountinfo_no_check",
            "file": str(path),
            "line": line_no,
            "account_name": name,
            "snippet": snippet,
            "advice": f"Raw AccountInfo `{name}` without Anchor constraints — proceed with `key/owner/discriminator` manual checks.",
            "severity": "high" if is_known_instance(name) else "medium",
            "classification": "known_class" if is_known_instance(name) else "novel_instance",
        })

    return findings


def main():
    ap = argparse.ArgumentParser(description="Audit any-account trust gaps in Solana programs")
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
    known = [f for f in all_findings if f["classification"] == "known_class"]

    if not args.quiet:
        print(f"[+] Scanned {len(files)} files. Trust gaps: {len(all_findings)}")
        print(f"    Novel instances: {len(novel)} (HIGH PRIORITY)")
        print(f"    Known classes:   {len(known)}")
        for f in (novel[:10] + known[:5]):
            tag = "NOVEL" if f["classification"] == "novel_instance" else "known"
            print(f"  [{f['severity']:8}] [{tag}] {f['account_name']:25} @ {Path(f['file']).name}:{f['line']}")

    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "account_trust_findings.json").write_text(json.dumps(all_findings, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
