#!/usr/bin/env python3
"""
owner_check_scanner.py — Detector for broader class: ACCOUNT OWNER VERIFICATION GAPS.

CLASS: `account.owner` not verified against expected program — allows
substituting fake accounts with identical-looking data.

Known instances of class:
  - Cashio 2022 ($52M): collateral.owner not verified → fake mint accepted
  - SPL token program substitution attacks
  - Stake account owner spoofing
"""
import argparse
import json
import re
import sys
from pathlib import Path


ACCOUNTINFO_FIELD_RE = re.compile(r"pub\s+(\w+):\s*AccountInfo<")
ACCOUNT_TYPED_RE = re.compile(r"pub\s+(\w+):\s*Account<'[^,]+,\s*\w+>")
OWNER_CHECK_RE = re.compile(r"\.owner\s*(?:==|!=|\.eq\(|equals|require_keys_eq|assert_eq)")
LOAD_TYPED_RE = re.compile(r"(?:try_from|try_deserialize|borrow|load)\s*[(<]")

KNOWN_HINTS = ["collateral", "mint", "token_account", "stake", "vault"]


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    findings = []
    lines = text.splitlines()

    raw_account_fields = []
    for m in ACCOUNTINFO_FIELD_RE.finditer(text):
        line_no = text[: m.start()].count("\n") + 1
        raw_account_fields.append({"name": m.group(1), "line": line_no})

    has_global_owner_check = bool(OWNER_CHECK_RE.search(text))

    for field in raw_account_fields:
        name = field["name"]
        line_no = field["line"]
        name_lc = name.lower()

        local_text = text[max(0, text.find(name) - 100): text.find(name) + 500]
        used_for_load = bool(LOAD_TYPED_RE.search(local_text))

        if not used_for_load and not any(h in name_lc for h in KNOWN_HINTS):
            continue

        is_known = any(h in name_lc for h in KNOWN_HINTS)

        if not has_global_owner_check:
            snippet = lines[line_no - 1].strip()[:140] if line_no <= len(lines) else ""
            findings.append({
                "class": "owner_check_missing",
                "file": str(path),
                "line": line_no,
                "account_name": name,
                "snippet": snippet,
                "advice": f"AccountInfo `{name}` used for data loading. "
                          f"No `.owner` verification anywhere in the file. "
                          f"Fake account with identical layout will be accepted.",
                "severity": "critical" if is_known else "high",
                "classification": "known_class" if is_known else "novel_instance",
            })

    typed_accounts_with_unchecked_owner = []
    for m in ACCOUNT_TYPED_RE.finditer(text):
        struct_start = max(0, m.start() - 1500)
        struct_context = text[struct_start: m.end() + 200]
        name = m.group(1)
        if (
            "constraint" in struct_context
            or "address =" in struct_context
            or "has_one =" in struct_context
            or "owner =" in struct_context
            or "seeds =" in struct_context
            or "token::mint =" in struct_context
            or "token::authority =" in struct_context
            or "init," in struct_context
        ):
            continue
        if re.search(rf"has_one\s*=\s*{re.escape(name)}\b", text):
            continue
        if any(h in name.lower() for h in KNOWN_HINTS):
            line_no = text[: m.start()].count("\n") + 1
            typed_accounts_with_unchecked_owner.append({
                "name": name,
                "line": line_no,
            })

    for entry in typed_accounts_with_unchecked_owner:
        findings.append({
            "class": "owner_check_missing",
            "subclass": "anchor_account_no_owner_constraint",
            "file": str(path),
            "line": entry["line"],
            "account_name": entry["name"],
            "advice": f"Anchor `Account<>` `{entry['name']}` without constraint/address. "
                      f"Anchor's automatic owner check is strict only for system-known types.",
            "severity": "medium",
            "classification": "novel_instance",
        })

    return findings


def main():
    ap = argparse.ArgumentParser(description="Find owner check gaps in Solana programs")
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
        print(f"[+] Owner check findings: {len(all_findings)} (novel: {len(novel)})")
        for f in all_findings[:10]:
            tag = "NOVEL" if f["classification"] == "novel_instance" else "known"
            print(f"  [{f['severity']:8}] [{tag}] {f['account_name']:25} @ {Path(f['file']).name}:{f['line']}")

    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "owner_check_findings.json").write_text(json.dumps(all_findings, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
