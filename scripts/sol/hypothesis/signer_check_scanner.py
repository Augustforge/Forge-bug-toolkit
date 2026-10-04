#!/usr/bin/env python3
"""
signer_check_scanner.py — Detector for broader class: SIGNER IDENTITY VERIFICATION GAPS.

CLASS: Accounts that should have signed the tx, but `is_signer` checks are missing.
Sibling instruction handlers — where one requires signer and another does not?

Known instances of class:
  - Wormhole 2022 ($325M): signature_set account not verified as signer in verify_signatures
  - Generic Solana 101: migration/upgrade handlers without `is_signer` check
  - Admin operations with unchecked authority

Detection strategy:
1. Find all instruction handlers (`pub fn` in impl)
2. For each handler — which accounts are expected to be signers?
3. Cross-check: same-name account siblings — one with Signer<>, another with AccountInfo<>?
4. Find `account.is_signer` manual checks → is it present in every handler?

CLASSIFICATION:
  - [known_class] = handler name matches verify_signatures/admin/upgrade patterns
  - [novel_instance] = sibling asymmetry signer constraints
"""
import argparse
import json
import re
import sys
from pathlib import Path


HANDLER_RE = re.compile(
    r"pub\s+fn\s+(\w+)\s*\([^)]*ctx:\s*Context<(\w+)>",
    re.MULTILINE,
)
SIGNER_FIELD_RE = re.compile(
    r"pub\s+(\w+):\s*Signer<",
)
ACCOUNTINFO_FIELD_RE = re.compile(
    r"pub\s+(\w+):\s*AccountInfo<",
)
ACCOUNT_STRUCT_RE = re.compile(
    r"#\[derive\(Accounts\)\]\s*\npub\s+struct\s+(\w+)<'\w+>\s*\{([^}]+)\}",
    re.DOTALL,
)
IS_SIGNER_CHECK_RE = re.compile(r"\.is_signer\s*(?:\)\s*\.\s*)?|require!\([^,]*\.is_signer")

KNOWN_HINTS = ["verify_sig", "verify_signature", "admin", "upgrade", "set_authority", "transfer_authority"]


def extract_accounts(account_struct_body: str) -> dict[str, str]:
    """Returns {field_name: account_type} from struct body."""
    fields = {}
    for m in re.finditer(r"pub\s+(\w+):\s*(\w+)<", account_struct_body):
        fields[m.group(1)] = m.group(2)
    return fields


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    findings = []
    lines = text.splitlines()

    accounts_structs = {}
    for m in ACCOUNT_STRUCT_RE.finditer(text):
        struct_name = m.group(1)
        body = m.group(2)
        accounts_structs[struct_name] = {
            "body": body,
            "fields": extract_accounts(body),
            "line": text[: m.start()].count("\n") + 1,
        }

    field_signer_status = {}
    for sn, info in accounts_structs.items():
        for fname, ftype in info["fields"].items():
            field_signer_status.setdefault(fname, {}).setdefault(ftype, []).append(sn)

    for fname, types_map in field_signer_status.items():
        is_signer_anywhere = "Signer" in types_map
        is_accountinfo_anywhere = "AccountInfo" in types_map
        if is_signer_anywhere and is_accountinfo_anywhere:
            sig_structs = types_map.get("Signer", [])
            info_structs = types_map.get("AccountInfo", [])
            for struct_name in info_structs:
                line_no = accounts_structs[struct_name]["line"]
                is_known = any(h in struct_name.lower() for h in KNOWN_HINTS)
                findings.append({
                    "class": "signer_check_drift",
                    "subclass": "sibling_asymmetry",
                    "file": str(path),
                    "line": line_no,
                    "account_name": fname,
                    "in_struct": struct_name,
                    "is_signer_in_structs": sig_structs,
                    "is_accountinfo_in_structs": info_structs,
                    "advice": f"Field `{fname}` is `Signer<>` in {sig_structs} but `AccountInfo<>` in {struct_name}. "
                              f"Same logical account, different signer enforcement = asymmetry bug.",
                    "severity": "critical" if is_known else "high",
                    "classification": "known_class" if is_known else "novel_instance",
                })

    for sn, info in accounts_structs.items():
        has_signer_field = bool(SIGNER_FIELD_RE.search(info["body"]))
        has_signer_check = bool(IS_SIGNER_CHECK_RE.search(text))
        if not has_signer_field and not has_signer_check and any(h in sn.lower() for h in KNOWN_HINTS):
            findings.append({
                "class": "signer_check_drift",
                "subclass": "admin_handler_no_signer",
                "file": str(path),
                "line": info["line"],
                "in_struct": sn,
                "advice": f"Handler context `{sn}` looks like admin/auth operation, but has neither Signer<> nor a manual is_signer check.",
                "severity": "critical",
                "classification": "known_class",
            })

    return findings


def main():
    ap = argparse.ArgumentParser(description="Find signer check gaps in Solana programs")
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
        print(f"[+] Signer check findings: {len(all_findings)} (novel: {len(novel)})")
        for f in all_findings[:10]:
            tag = "NOVEL" if f["classification"] == "novel_instance" else "known"
            print(f"  [{f['severity']:8}] [{tag}] {f.get('account_name', f.get('in_struct'))} @ {Path(f['file']).name}:{f['line']}")

    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "signer_check_findings.json").write_text(json.dumps(all_findings, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
