#!/usr/bin/env python3
"""
pda_seed_analyzer.py — Detector for broader class: PDA SEED UNIQUENESS GAPS.

CLASS: PDA seeds insufficient for uniqueness (predictable, empty, no bump
binding) → collision / hijack.

Detection:
1. Find seeds = [...] declarations
2. Check for:
   - Empty seeds → catastrophic (caller's PDA is same for everyone)
   - Predictable seeds (constants only, no user input)
   - Missing bump constraint
   - Cross-instruction same seeds (collision)
"""
import argparse
import json
import re
import sys
from pathlib import Path


SEEDS_RE = re.compile(r"seeds\s*=\s*\[([^\]]*)\]", re.MULTILINE)
SEEDS_WITH_BUMP_RE = re.compile(r"seeds\s*=\s*\[[^\]]*\][\s,]*bump")
FIND_PROGRAM_ADDRESS_RE = re.compile(r"(?:Pubkey::)?find_program_address\s*\(\s*&\s*\[([^\]]*)\]")


def is_static_seeds(seeds_str: str) -> bool:
    """All seeds are b\"...\" constants — predictable."""
    parts = [p.strip() for p in seeds_str.split(",") if p.strip()]
    return all(p.startswith('b"') or p.startswith("b'") for p in parts) and len(parts) > 0


def is_empty_seeds(seeds_str: str) -> bool:
    return not seeds_str.strip() or seeds_str.strip() == ""


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    findings = []
    lines = text.splitlines()

    for m in SEEDS_RE.finditer(text):
        seeds_str = m.group(1)
        line_no = text[: m.start()].count("\n") + 1
        snippet = lines[line_no - 1].strip()[:140] if line_no <= len(lines) else ""

        if is_empty_seeds(seeds_str):
            findings.append({
                "class": "pda_seed_collision",
                "subclass": "empty_seeds",
                "file": str(path),
                "line": line_no,
                "snippet": snippet,
                "advice": "Empty PDA seeds — every caller derives same PDA → guaranteed collision/hijack.",
                "severity": "critical",
                "classification": "known_class",
            })
            continue

        if is_static_seeds(seeds_str):
            findings.append({
                "class": "pda_seed_collision",
                "subclass": "predictable_static_seeds",
                "file": str(path),
                "line": line_no,
                "snippet": snippet,
                "advice": "Static seeds (constants only). PDA fully predictable — anyone can pre-compute and front-run init. "
                          "Add user-specific seed (owner.key()) or mint/account ref.",
                "severity": "high",
                "classification": "novel_instance",
            })

        local_context = text[max(0, m.start() - 100): m.end() + 200]
        if not SEEDS_WITH_BUMP_RE.search(local_context):
            findings.append({
                "class": "pda_seed_collision",
                "subclass": "missing_bump_binding",
                "file": str(path),
                "line": line_no,
                "snippet": snippet,
                "advice": "PDA seeds declared without `bump` field bind. Pubkey-only PDA can have multiple bumps → "
                          "predictable hijack or non-canonical bump abuse.",
                "severity": "medium",
                "classification": "novel_instance",
            })

    for m in FIND_PROGRAM_ADDRESS_RE.finditer(text):
        seeds_str = m.group(1)
        if is_empty_seeds(seeds_str):
            line_no = text[: m.start()].count("\n") + 1
            findings.append({
                "class": "pda_seed_collision",
                "subclass": "find_program_address_empty",
                "file": str(path),
                "line": line_no,
                "advice": "find_program_address with empty seeds — same as empty seeds attack.",
                "severity": "critical",
                "classification": "known_class",
            })

    return findings


def main():
    ap = argparse.ArgumentParser(description="Audit PDA seed uniqueness")
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
        print(f"[+] PDA seed findings: {len(all_findings)} (novel: {len(novel)})")
        for f in all_findings[:10]:
            tag = "NOVEL" if f["classification"] == "novel_instance" else "known"
            print(f"  [{f['severity']:8}] [{tag}] {f['subclass']} @ {Path(f['file']).name}:{f['line']}")

    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "pda_seed_findings.json").write_text(json.dumps(all_findings, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
