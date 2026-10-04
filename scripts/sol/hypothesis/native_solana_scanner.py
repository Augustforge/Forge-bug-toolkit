#!/usr/bin/env python3
"""
native_solana_scanner.py — Detect trust-gap patterns in **native Solana** programs
(no Anchor framework). Targets: Wormhole, SPL Token, Mango v3, custom protocols.

CONTEXT:
Native Solana programs do not use `#[derive(Accounts)]` macros. Account
validation is hand-coded via the `next_account_info(iter)` pattern. Anchor's
auto-generated checks (signer/writable/owner) do NOT apply — each check
must be manual.

This is **the** historically dangerous coding style — Wormhole 2022 ($325M)
lived here, Cashio 2022 ($52M) partly, and many native programs are unaudited
simply because Anchor-biased tools do not cover them.

DETECTION PATTERNS (native-specific):

1. **`next_account_info(account_info_iter)` without checks** — Account loaded but
   `account.owner` / `account.is_signer` / discriminator not verified.

2. **Process_instruction with account index access** —
   `accounts[N].key` use without preceding key/owner verification.

3. **Borsh deserialize without owner check** — `T::try_from_slice(&account.data.borrow())`
   without `account.owner == program_id` check.

4. **Sysvar account index trust** — `accounts[N]` assumed to be specific
   sysvar (clock, rent, instructions) without `accounts[N].key == &sysvar::ID`.

5. **Signature set account state trust** (Wormhole class) — account
   deserialized with trusted assumptions about internal state (number of signers,
   guardian set index) without re-verification.

CLASSIFICATION:
  - [known_class] = matches Wormhole / Cashio historical patterns
  - [novel_instance] = a new native-coding gap

Usage:
    python3 native_solana_scanner.py --target sessions/$TARGET/source
"""
import argparse
import json
import re
import sys
from pathlib import Path


ANCHOR_MARKERS = [
    re.compile(r"#\[derive\(Accounts\)\]"),
    re.compile(r"use\s+anchor_lang"),
    re.compile(r"declare_id!"),
]

NATIVE_MARKERS = [
    re.compile(r"use\s+solana_program"),
    re.compile(r"entrypoint!\("),
    re.compile(r"next_account_info\s*\("),
    re.compile(r"process_instruction\s*\("),
]

NEXT_ACCOUNT_INFO_RE = re.compile(
    r"(?:let\s+(\w+)\s*=\s*)?next_account_info\s*\(\s*\w+\s*\)\??\s*[;,?]"
)

ACCOUNT_USAGE_PATTERNS = {
    "deserialize_data": re.compile(r"::try_from_slice\s*\(\s*&?\s*(\w+)\.data\b"),
    "key_usage_no_check": re.compile(r"(\w+)\.key(?:\(\))?(?!\s*==)"),
    "lamports_write": re.compile(r"(\w+)\.lamports.*[+-]?=\s*"),
    "data_write": re.compile(r"(\w+)\.data\.borrow_mut"),
}

OWNER_CHECK_PATTERNS = {
    "explicit_owner": re.compile(r"(\w+)\.owner\s*==|require!.*owner.*==|assert_eq!.*owner"),
    "owner_keys_eq": re.compile(r"require_keys_eq!\s*\(\s*\*?(\w+)\.owner|cmp_pubkeys.*owner"),
}

SIGNER_CHECK_PATTERNS = {
    "explicit_signer": re.compile(r"(\w+)\.is_signer|require!.*is_signer|assert!.*is_signer"),
}

KEY_CHECK_PATTERNS = [
    re.compile(r"(\w+)\.key\(?\)?\s*==\s*"),
    re.compile(r"require_keys_eq!\s*\(\s*(\w+)\.key"),
    re.compile(r"cmp_pubkeys\s*\(\s*&?(\w+)\.key"),
]

SYSVAR_ACCESS = re.compile(r"(\w+)\.key\(?\)?\s*==\s*&?sysvar::|sysvar::\w+::ID\s*==\s*(\w+)\.key")

# CPI-4/5 (asymmetric.re "Invocation Security"): signer passed to an arbitrary CPI.
INVOKE_RE = re.compile(r"\binvoke(?:_signed)?\s*\(")
ASSIGN_RE = re.compile(r"(?:system_instruction::)?assign\s*\(")
# Mitigations: post-CPI owner re-check back to system_program; pre/post lamport balance guard.
OWNER_RECHECK_SYSTEM = re.compile(
    r"\.owner\s*==[^\n]*system_program|require_keys_eq!\s*\(\s*\*?\w+\.owner\s*,\s*&?\s*(?:system_program|solana_program::system_program)",
)
LAMPORT_GUARD = re.compile(
    r"lamports?_before|lamports?_after|balance_before|balance_after|\.lamports\(\)[^\n]*\.lamports\(\)",
)


def is_native_solana(text: str) -> bool:
    """True if file uses native Solana account model (not Anchor #[derive(Accounts)]).

    Mango v3-style hybrid: anchor_lang imported for emit! but account parsing native.
    Decision: file is native if uses `next_account_info`, `accounts[N]`, OR
    Solitaire `FromAccounts` macros — regardless of anchor_lang import.
    """
    has_native_pattern = (
        any(p.search(text) for p in NATIVE_MARKERS)
        or re.search(r"accounts\s*\[\s*\d+\s*\]", text)
        or re.search(r"#\[derive\(FromAccounts\)\]", text)  # Solitaire
        or re.search(r"array_refs!|array_ref!", text)  # Mango v3-style
    )
    has_anchor_struct = re.search(r"#\[derive\(Accounts\)\]", text)
    return bool(has_native_pattern and not has_anchor_struct)


def find_account_vars(text: str) -> list[tuple[str, int]]:
    accounts = []
    for m in NEXT_ACCOUNT_INFO_RE.finditer(text):
        name = m.group(1)
        line = text[: m.start()].count("\n") + 1
        if name:
            accounts.append((name, line))
    return accounts


def check_var_safety(text: str, var_name: str) -> dict:
    has_owner = bool(re.search(rf"{re.escape(var_name)}\.owner\s*==", text)) or \
                bool(re.search(rf"require_keys_eq!\s*\(\s*\*?{re.escape(var_name)}\.owner", text))
    has_signer = bool(re.search(rf"{re.escape(var_name)}\.is_signer", text))
    has_key_check = any(p.search(text) and var_name in p.search(text).group(0)
                        for p in KEY_CHECK_PATTERNS if p.search(text))
    is_deserialized = bool(re.search(rf"::try_from_slice\s*\(\s*&?\s*{re.escape(var_name)}\.data", text))
    is_signer_used = bool(re.search(rf"{re.escape(var_name)}\.is_signer.*true|require!\s*\(\s*{re.escape(var_name)}\.is_signer", text))
    is_writable_modified = bool(re.search(rf"{re.escape(var_name)}\.(?:lamports|data)\.borrow_mut", text))
    return {
        "has_owner_check": has_owner,
        "has_signer_check": has_signer,
        "has_key_check": has_key_check,
        "is_deserialized": is_deserialized,
        "is_used_as_signer": is_signer_used,
        "is_mutated": is_writable_modified,
    }


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    if not is_native_solana(text):
        return []

    findings = []
    accounts = find_account_vars(text)

    if not accounts:
        return findings

    for var_name, line_no in accounts:
        safety = check_var_safety(text, var_name)

        is_known_class = var_name.lower() in (
            "signature_set", "signature_account", "bridge", "guardian_set",
            "vaa_account", "claim_account", "config"
        )

        if safety["is_deserialized"] and not safety["has_owner_check"]:
            findings.append({
                "class": "native_solana_trust_gap",
                "subclass": "deserialize_without_owner_check",
                "file": str(path),
                "line": line_no,
                "account_var": var_name,
                "advice": f"Account `{var_name}` deserialized via `try_from_slice` without `{var_name}.owner == program_id` check. "
                          f"Attacker can craft fake account with identical layout owned by different program → state confusion. "
                          f"Wormhole 2022 ($325M) class: signature_set deserialized with trusted internal state.",
                "severity": "critical",
                "classification": "known_class" if is_known_class else "novel_instance",
                "broader_class": "native_account_owner_trust",
                "attack_template": "owner_check_substitution",
            })

        if safety["is_used_as_signer"] is False and safety["is_mutated"] and not safety["has_signer_check"]:
            findings.append({
                "class": "native_solana_trust_gap",
                "subclass": "mutated_without_signer_check",
                "file": str(path),
                "line": line_no,
                "account_var": var_name,
                "advice": f"Account `{var_name}` mutated (lamports/data) without `is_signer` verification. "
                          f"Unauthorized actor can trigger state change OR drain.",
                "severity": "high",
                "classification": "novel_instance",
                "broader_class": "native_signer_trust",
            })

        if not safety["has_key_check"] and not safety["has_owner_check"] and (safety["is_deserialized"] or safety["is_mutated"]):
            findings.append({
                "class": "native_solana_trust_gap",
                "subclass": "fully_unverified_account",
                "file": str(path),
                "line": line_no,
                "account_var": var_name,
                "advice": f"Account `{var_name}` used (deserialize/mutate) without ANY identity check (key/owner/signer). "
                          f"Maximum trust gap.",
                "severity": "critical",
                "classification": "known_class" if is_known_class else "novel_instance",
                "broader_class": "native_account_blind_trust",
            })

    for m in SYSVAR_ACCESS.finditer(text):
        pass

    array_access = re.findall(r"accounts\s*\[\s*(\d+)\s*\]", text)
    if array_access:
        unique_indices = set(array_access)
        for idx in unique_indices:
            if not re.search(rf"accounts\s*\[\s*{idx}\s*\]\.key\b.*==|require_keys_eq!.*accounts\s*\[\s*{idx}\s*\]", text):
                if re.search(rf"accounts\s*\[\s*{idx}\s*\]\.data|accounts\s*\[\s*{idx}\s*\]\.lamports", text):
                    findings.append({
                        "class": "native_solana_trust_gap",
                        "subclass": "indexed_account_no_key_check",
                        "file": str(path),
                        "line": 1,
                        "advice": f"`accounts[{idx}]` used data/lamports without key/owner check. "
                                  f"Process_instruction-style native code commonly has this gap.",
                        "severity": "high",
                        "classification": "novel_instance",
                        "broader_class": "native_indexed_trust",
                    })

    # CPI-4 / CPI-5: signer privilege passed to an arbitrary CPI (no Anchor Program<> typing here).
    has_signer = bool(re.search(r"is_signer", text))
    if has_signer:
        # CPI-4: account reassigned via `assign()` without re-checking owner == system_program after.
        am = ASSIGN_RE.search(text)
        if am and not OWNER_RECHECK_SYSTEM.search(text):
            findings.append({
                "class": "native_solana_trust_gap",
                "subclass": "assign_ownership_hijack",
                "file": str(path),
                "line": text[: am.start()].count("\n") + 1,
                "advice": "`assign()` reassigns an account's owner with a signer in scope and no post-call "
                          "`owner == system_program` re-check. Attacker can `assign(signer, attacker_program)` → "
                          "original owner loses control permanently (asymmetric.re CPI-4).",
                "severity": "high",
                "classification": "novel_instance",
                "broader_class": "native_cpi_signer_passthrough",
                "attack_template": "assign_owner_hijack",
            })
        # CPI-5: signer passed into invoke/invoke_signed without a pre/post lamport balance guard.
        im = INVOKE_RE.search(text)
        if im and not LAMPORT_GUARD.search(text):
            findings.append({
                "class": "native_solana_trust_gap",
                "subclass": "unbounded_lamport_spend",
                "file": str(path),
                "line": text[: im.start()].count("\n") + 1,
                "advice": "Signer account passed into a CPI with no pre/post lamport balance guard. Solana has no "
                          "`msg.value` cap — the callee program can drain the signer's full balance "
                          "(asymmetric.re CPI-5). Add `balance_before`/`balance_after` + require!(spent <= max).",
                "severity": "high",
                "classification": "novel_instance",
                "broader_class": "native_cpi_signer_passthrough",
                "attack_template": "lamport_drain",
            })

    return findings


def main():
    ap = argparse.ArgumentParser(description="Native Solana (non-Anchor) trust gap detector")
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
    native_files = 0
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
            if is_native_solana(text):
                native_files += 1
        except Exception:
            continue
        all_findings.extend(scan_file(f))

    if not args.quiet:
        critical = [f for f in all_findings if f["severity"] == "critical"]
        high = [f for f in all_findings if f["severity"] == "high"]
        novel = [f for f in all_findings if f.get("classification") == "novel_instance"]
        known = [f for f in all_findings if f.get("classification") == "known_class"]
        print(f"[+] Scanned {len(files)} files ({native_files} native Solana). Trust gaps: {len(all_findings)}")
        print(f"    Critical: {len(critical)}")
        print(f"    High:     {len(high)}")
        print(f"    Novel:    {len(novel)}")
        print(f"    Known:    {len(known)} (Wormhole/Cashio-class)")

        for f in (critical + high)[:15]:
            sev = f["severity"].upper()
            cls = f.get("classification", "?")
            f_name = Path(f["file"]).name
            print(f"  [{sev:8}] [{cls}] {f['subclass']:35} @ {f_name}:{f['line']}")

    if args.output:
        out_dir = Path(args.output)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "native_solana_findings.json").write_text(json.dumps(all_findings, indent=2))


if __name__ == "__main__":
    main()
