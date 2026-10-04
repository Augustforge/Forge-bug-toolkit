#!/usr/bin/env python3
"""
token2022_hook_composability.py — Composability hazard detector for protocols
which accept Token-2022 mints (and especially transfer hooks).

CONTEXT:
Token-2022 (Token Extensions) program has multiple extensions. The most
dangerous for composability:
- **Transfer Hooks** — callback program executed at every transfer_checked.
  Hook may CPI back to caller (Token-2022 reentrancy).
- **Confidential Transfers** — encrypted balances + ZK proofs.
- **Interest-bearing** — token supply changes over time.
- **Transfer Fees** — recipient receives less than sender sends.
- **Freeze authority + non-transferable**.

Protocols which accept arbitrary token mints can be attacked if they
trust Token-2022 mint without extension-aware checks:
1. Recipient gets less than sender sent (fee) → accounting drift
2. Hook callbacks call back into protocol mid-transfer → reentrancy
3. Interest accrual changes balance silently → invariant broken
4. Confidential transfer balances unreadable → trust assumption breaks

DETECTION:
1. Find places accepting `mint: Account<Mint>` or Token-2022 references
2. Check if extension parsing/validation present
3. Flag: protocol accepting arbitrary tokens without extension checks
4. Specific danger zones:
   - LP/AMM protocols
   - Lending protocols
   - Vault protocols
   - Bridge protocols

CLASSIFICATION:
  - [known_class] = matches Token-2022 transfer hook reentrancy import
  - [novel_instance] = new composability surface

Usage:
    python3 token2022_hook_composability.py --target sessions/$TARGET/source
"""
import argparse
import json
import re
import sys
from pathlib import Path


TOKEN2022_REFS = [
    re.compile(r"token_2022|Token2022|spl_token_2022|TokenExtension"),
    re.compile(r"TOKEN_2022_PROGRAM_ID"),
    re.compile(r"TransferHook|transfer_hook"),
]
EXTENSION_VALIDATION_PATTERNS = [
    re.compile(r"get_extension|extension_data|ExtensionType"),
    re.compile(r"check_extensions|validate_extensions|extension_supported"),
    re.compile(r"reject_token_2022|require_legacy_token|require_token_program"),
]
TRANSFER_CHECKED_PATTERNS = [
    re.compile(r"transfer_checked|transfer_checked_with_fee"),
]
HOOK_CALLBACK_VULNERABLE = [
    re.compile(r"transfer_checked.*signer_seeds|transfer_checked_with_signer"),
]
AMOUNT_ASSUMPTION_PATTERNS = [
    re.compile(r"amount\s*-=\s*\w+|amount\.checked_sub|to\.balance.*\+="),
]
FEE_AWARE_PATTERNS = [
    re.compile(r"transfer_fee|FeeAmount|fee_recipient"),
    re.compile(r"actual_received|net_amount|post_transfer_balance"),
]


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    uses_token2022 = any(p.search(text) for p in TOKEN2022_REFS)
    if not uses_token2022:
        return []

    findings = []
    primary = next((p.search(text) for p in TOKEN2022_REFS if p.search(text)), None)
    line_no = text[: primary.start()].count("\n") + 1 if primary else 1

    has_extension_validation = any(p.search(text) for p in EXTENSION_VALIDATION_PATTERNS)
    has_transfer_checked = any(p.search(text) for p in TRANSFER_CHECKED_PATTERNS)
    has_hook_pattern = any(p.search(text) for p in HOOK_CALLBACK_VULNERABLE)
    has_amount_assumption = any(p.search(text) for p in AMOUNT_ASSUMPTION_PATTERNS)
    has_fee_awareness = any(p.search(text) for p in FEE_AWARE_PATTERNS)

    if not has_extension_validation:
        findings.append({
            "class": "token2022_composability",
            "subclass": "no_extension_validation",
            "file": str(path),
            "line": line_no,
            "advice": "Token-2022 mint accepted without extension-type validation. "
                     "Protocol may break if mint has unexpected extensions (transfer_fee, transfer_hook, "
                     "non_transferable, interest_bearing). At minimum: parse Mint::Extensions, reject "
                     "unsupported types OR handle each explicitly.",
            "severity": "high",
            "classification": "known_class",
            "broader_class": "token2022_extension_blindness",
        })

    if has_transfer_checked and has_amount_assumption and not has_fee_awareness:
        findings.append({
            "class": "token2022_composability",
            "subclass": "transfer_fee_unaware",
            "file": str(path),
            "line": line_no,
            "advice": "Uses transfer_checked + arithmetic assuming exact amount transferred. "
                     "Token-2022 transfer_fee extension makes recipient receive LESS than sender sent. "
                     "Accounting drift: `vault.balance += amount` but vault actually gets `amount - fee`.",
            "severity": "high",
            "classification": "known_class",
            "broader_class": "token2022_fee_drift",
            "attack_template": "token2022_fee_griefing",
        })

    if has_transfer_checked and has_hook_pattern:
        findings.append({
            "class": "token2022_composability",
            "subclass": "transfer_hook_reentrancy_surface",
            "file": str(path),
            "line": line_no,
            "advice": "transfer_checked CPI + signer_seeds pattern. Token-2022 transfer hooks "
                     "execute attacker-controlled program mid-transfer — REENTRANCY surface "
                     "(unprecedented in Solana pre-2024). Hook may call back into caller protocol, "
                     "read/mutate state during half-completed transfer.",
            "severity": "critical",
            "classification": "known_class",
            "broader_class": "token2022_hook_reentrancy",
            "attack_template": "token2022_transfer_hook_reentrancy",
        })

    if uses_token2022:
        findings.append({
            "class": "token2022_composability",
            "subclass": "token2022_acceptance_review",
            "file": str(path),
            "line": line_no,
            "advice": "Protocol accepts Token-2022. Comprehensive review needed: "
                     "1) which extensions allowed/rejected, 2) fee-aware accounting, "
                     "3) hook reentrancy guards, 4) interest-bearing supply changes, "
                     "5) confidential transfer support semantics, 6) freeze authority awareness.",
            "severity": "info",
            "classification": "novel_instance",
            "broader_class": "token2022_review_marker",
        })

    return findings


def main():
    ap = argparse.ArgumentParser(description="Token-2022 composability hazard detector")
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
        critical = [f for f in all_findings if f["severity"] == "critical"]
        high = [f for f in all_findings if f["severity"] == "high"]
        print(f"[+] Scanned {len(files)} files. Token-2022 findings: {len(all_findings)}")
        print(f"    Critical: {len(critical)}")
        print(f"    High:     {len(high)}")

        for f in (critical + high)[:15]:
            sev = f["severity"].upper()
            cls = f.get("classification", "?")
            f_name = Path(f["file"]).name
            print(f"  [{sev:8}] [{cls}] {f['subclass']:42} @ {f_name}:{f['line']}")

    if args.output:
        out_dir = Path(args.output)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "token2022_hook_findings.json").write_text(json.dumps(all_findings, indent=2))


if __name__ == "__main__":
    main()
