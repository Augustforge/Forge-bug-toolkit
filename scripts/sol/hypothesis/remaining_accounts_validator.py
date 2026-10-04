#!/usr/bin/env python3
"""
remaining_accounts_validator.py — Detector for `ctx.remaining_accounts[N]`
usage without identity verification.

CLASS: Method-level account access via `remaining_accounts[]` index — Anchor's
struct-level constraints do NOT apply. Each access must explicitly verify
`remaining_accounts[i].key() == expected_key` else attacker substitutes.

Known historical instance:
  - Raydium CLMM 2024 (commit 83b5a47 pre-fix): `Some(&remaining_accounts[0])`
    passed without require_keys_eq against `TickArrayBitmapExtension::key(pool_state)`.
    Fix added the key check.

Detection strategy:
1. Find all `remaining_accounts[N]` accesses
2. For each, check if **same function** has `require_keys_eq!(remaining_accounts[N].key(), ...)`
   OR `require!(remaining_accounts[N].key() == ...)` checking that index.
3. If no check → flag.

CLASSIFICATION:
  - [known_class] = matches Raydium CLMM 2024 pattern
  - [novel_instance] = different protocol with same gap

Usage:
    python3 remaining_accounts_validator.py --target sessions/$TARGET/source
"""
import argparse
import json
import re
import sys
from pathlib import Path


REMAINING_ACCESS_RE = re.compile(r"remaining_accounts\s*\[\s*(\d+)\s*\]")
KEY_CHECK_RE = re.compile(
    r"require_keys_eq!\s*\(\s*remaining_accounts\s*\[\s*(\d+)\s*\]\.key\(\)|"
    r"require!\s*\(\s*remaining_accounts\s*\[\s*(\d+)\s*\]\.key\(\)\s*==|"
    r"assert!\s*\(\s*remaining_accounts\s*\[\s*(\d+)\s*\]\.key\(\)\s*=="
)
FN_BLOCK_RE = re.compile(r"(?:pub\s+)?fn\s+(\w+)\s*[<(](?:[^{]*)\{", re.MULTILINE)


def find_function_bounds(text: str) -> list[tuple[str, int, int]]:
    """Return list of (function_name, start_pos, end_pos) for all fn definitions."""
    bounds = []
    for m in FN_BLOCK_RE.finditer(text):
        name = m.group(1)
        start = m.end() - 1
        depth = 1
        i = start + 1
        while i < len(text) and depth > 0:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        bounds.append((name, start, i))
    return bounds


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    findings = []
    lines = text.splitlines()

    fn_bounds = find_function_bounds(text)

    for m in REMAINING_ACCESS_RE.finditer(text):
        access_idx = m.group(1)
        access_pos = m.start()
        line_no = text[: access_pos].count("\n") + 1

        containing_fn = None
        fn_text = ""
        for name, start, end in fn_bounds:
            if start <= access_pos <= end:
                containing_fn = name
                fn_text = text[start:end]
                break

        if not fn_text:
            fn_text = text[max(0, access_pos - 2000): access_pos + 2000]

        checked = False
        for check_match in KEY_CHECK_RE.finditer(fn_text):
            check_idx = check_match.group(1) or check_match.group(2) or check_match.group(3)
            if check_idx == access_idx:
                checked = True
                break

        snippet_line = lines[line_no - 1].strip() if line_no <= len(lines) else ""
        is_passed_to_load = "AccountLoad" in snippet_line or "try_from" in snippet_line or "to_account_info" in snippet_line
        is_optional_wrap = "Some(" in snippet_line or "Option" in snippet_line

        if not checked:
            severity = "critical" if (is_passed_to_load or is_optional_wrap) else "high"
            findings.append({
                "class": "remaining_accounts_unverified",
                "subclass": "missing_key_check",
                "file": str(path),
                "line": line_no,
                "function": containing_fn or "?",
                "access_idx": access_idx,
                "snippet": snippet_line[:160],
                "advice": f"`remaining_accounts[{access_idx}]` accessed in `{containing_fn or '?'}` without require_keys_eq!. "
                          f"Attacker can substitute fake account. Pattern: Raydium CLMM 2024 ($505K bounty paid).",
                "severity": severity,
                "classification": "known_class" if (is_passed_to_load or is_optional_wrap) else "novel_instance",
                "broader_class": "auxiliary_account_trust",
                "attack_template": "owner_check_substitution",
            })

    return findings


def main():
    ap = argparse.ArgumentParser(description="Detect remaining_accounts[N] usage without key verification")
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
        known = [f for f in all_findings if f.get("classification") == "known_class"]
        print(f"[+] Scanned {len(files)} files. remaining_accounts findings: {len(all_findings)}")
        print(f"    Critical: {len(critical)} (passed to AccountLoad/Optional — most likely real)")
        print(f"    High:     {len(high)}")
        print(f"    Novel:    {len(novel)}")
        print(f"    Known:    {len(known)} (Raydium CLMM-class)")

        for f in (critical + high)[:15]:
            sev = f["severity"].upper()
            cls = f.get("classification", "?")
            f_name = Path(f["file"]).name
            print(f"  [{sev:8}] [{cls}] [{f['access_idx']}] fn `{f['function']}` @ {f_name}:{f['line']}")

    if args.output:
        out_dir = Path(args.output)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "remaining_accounts_findings.json").write_text(json.dumps(all_findings, indent=2))


if __name__ == "__main__":
    main()
