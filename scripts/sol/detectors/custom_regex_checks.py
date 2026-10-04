#!/usr/bin/env python3
"""
custom_regex_checks.py — Solana regex-based fast detectors.

10 checks covering primary Solana footguns. Each check is a fast regex pass
over Rust source — first-line defense before deeper hypothesis analysis.

Checks:
1. Missing is_signer verification
2. Missing account.owner verification
3. Anchor::init without already_init protection
4. PDA seed empty (&[])
5. invoke_signed without AccountInfo authority verify
6. Missing checked_add/sub (Anchor < 0.30 pattern)
7. Sysvar passed as raw AccountInfo
8. Type confusion (AccountInfo direct cast)
9. Hardcoded discriminator (vs derived)
10. Unbounded loop (compute budget DoS)

Output: regex_findings.json + regex_report.md
"""
import argparse
import json
import re
import sys
from pathlib import Path


CHECKS = [
    {
        "id": "missing_signer_check",
        "regex": re.compile(r"#\[account\(([^)]+)\)\][^\n]*\n[^\n]*pub\s+(\w+):\s*(?:Signer|AccountInfo)", re.MULTILINE),
        "post_check": lambda m: "signer" not in m.group(1).lower() and "Signer<" not in m.group(0),
        "advice": "Account expects a signature — add `signer` constraint in #[account(...)] or use `Signer<'info>` type",
        "severity_hint": "critical",
        "class": "missing_signer_check",
    },
    {
        "id": "missing_owner_check",
        "regex": re.compile(r"AccountInfo<'\w+>\s*[^\n]*\n[^{}\n]*\{[^}]*?\.data\.borrow\(\)", re.DOTALL),
        "post_check": lambda m: "owner ==" not in m.group(0) and "key_eq" not in m.group(0),
        "advice": "AccountInfo data access without verifying ownership — add require_keys_eq!(account.owner, expected_program)",
        "severity_hint": "critical",
        "class": "missing_owner_check",
    },
    {
        "id": "anchor_init_no_guard",
        "regex": re.compile(r"#\[account\(init,([^)]+)\)\]"),
        "post_check": lambda m: "init_if_needed" not in m.group(0) and "constraint" not in m.group(0),
        "advice": "Anchor `init` without guard may allow reinitialization. Use a constraint check.",
        "severity_hint": "high",
        "class": "account_reinit",
    },
    {
        "id": "pda_seeds_empty",
        "regex": re.compile(r"seeds\s*=\s*\[\s*\]"),
        "post_check": lambda m: True,
        "advice": "PDA with empty seeds — all calls create the same PDA → collision/hijack",
        "severity_hint": "critical",
        "class": "pda_seed_collision",
    },
    {
        "id": "invoke_signed_no_authority",
        "regex": re.compile(r"invoke_signed\s*\([^,]+,\s*[^,]+,\s*&?\[\s*&?\[\s*\]\s*\]"),
        "post_check": lambda m: True,
        "advice": "invoke_signed with empty signers — no authority verification",
        "severity_hint": "high",
        "class": "cpi_authority_missing",
    },
    {
        "id": "unchecked_arithmetic",
        "regex": re.compile(r"(\w+)\s*[\+\-\*]=\s*(\w+)|(\w+)\s*=\s*(\w+)\s*[\+\-\*]\s*(\w+)"),
        "post_check": lambda m: "checked_" not in (m.string[max(0, m.start()-50):m.start()] + m.group(0)),
        "advice": "Arithmetic without checked_add/sub/mul — overflow possible. Use checked_* or saturating_*.",
        "severity_hint": "medium",
        "class": "arithmetic_overflow",
    },
    {
        "id": "sysvar_raw_account",
        "regex": re.compile(r"pub\s+(clock|rent|stake_history|recent_blockhashes):\s*AccountInfo"),
        "post_check": lambda m: True,
        "advice": "Sysvar passed as AccountInfo (no type check) — fake sysvar substitution possible. Use Sysvar<'info, Clock> etc.",
        "severity_hint": "high",
        "class": "sysvar_trust",
    },
    {
        "id": "type_confusion_cast",
        "regex": re.compile(r"AccountInfo[^>]*>::try_from\(|try_from_account_info\("),
        "post_check": lambda m: True,
        "advice": "Direct AccountInfo → typed cast without discriminator check — type confusion possible",
        "severity_hint": "high",
        "class": "type_confusion",
    },
    {
        "id": "hardcoded_discriminator",
        "regex": re.compile(r"discriminator\s*=\s*\[\s*\d+\s*(?:,\s*\d+\s*){7}\]"),
        "post_check": lambda m: True,
        "advice": "Hardcoded 8-byte discriminator — verify no overlap with another account type via `custom_discriminator_audit.py`",
        "severity_hint": "medium",
        "class": "custom_discriminator",
    },
    {
        "id": "unbounded_loop",
        "regex": re.compile(r"for\s+\w+\s+in\s+\w+(?:\.iter\(\))?\s*\{|while\s+\w+", re.MULTILINE),
        "post_check": lambda m: ".take(" not in m.string[m.start():min(len(m.string), m.start()+200)],
        "advice": "Unbounded loop — compute budget DoS is possible. Use .take(MAX) or an explicit bound check.",
        "severity_hint": "medium",
        "class": "compute_dos",
    },
]


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    findings = []
    lines = text.splitlines()
    for check in CHECKS:
        for m in check["regex"].finditer(text):
            try:
                if not check["post_check"](m):
                    continue
            except Exception:
                continue
            line_no = text[: m.start()].count("\n") + 1
            snippet = lines[line_no - 1].strip()[:140] if line_no <= len(lines) else ""
            findings.append({
                "check_id": check["id"],
                "class": check["class"],
                "file": str(path),
                "line": line_no,
                "snippet": snippet,
                "advice": check["advice"],
                "severity": check["severity_hint"],
                "classification": "known_class",
            })
    return findings


def main():
    ap = argparse.ArgumentParser(description="Solana fast regex-based detector pass")
    ap.add_argument("--target", required=True, help="Source dir or .rs file")
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    target = Path(args.target)
    files = []
    if target.is_file() and target.suffix == ".rs":
        files = [target]
    elif target.is_dir():
        files = list(target.rglob("*.rs"))
    else:
        print(f"[!] Target not found: {target}", file=sys.stderr)
        sys.exit(1)

    all_findings = []
    for f in files:
        if "/test" in str(f).replace("\\", "/").lower() or "/target/" in str(f).replace("\\", "/"):
            continue
        all_findings.extend(scan_file(f))

    if not args.quiet:
        print(f"[+] Scanned {len(files)} files. Findings: {len(all_findings)}")
        by_class = {}
        for f in all_findings:
            by_class.setdefault(f["class"], 0)
            by_class[f["class"]] += 1
        for cls, n in sorted(by_class.items(), key=lambda x: -x[1]):
            print(f"  {cls:30} {n}")

    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "regex_findings.json").write_text(json.dumps(all_findings, indent=2), encoding="utf-8")
        md = "# Solana Regex Findings\n\n"
        for f in all_findings:
            md += f"## [{f['severity']}] {f['check_id']} ({f['classification']})\n"
            md += f"**File**: {f['file']}:{f['line']}\n\n"
            md += f"```rust\n{f['snippet']}\n```\n\n"
            md += f"**Advice**: {f['advice']}\n\n"
        (out / "regex_report.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
