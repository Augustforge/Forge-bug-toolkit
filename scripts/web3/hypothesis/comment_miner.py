#!/usr/bin/env python3
"""
comment_miner.py — Detector for broader class: AUTHOR-DECLARED INVARIANTS.

CLASS: Comments which declare author's assumptions (invariants, expected behavior,
edge case handling). These declarations indicate where author was thinking about
edge cases — often gaps remain between declaration and actual code enforcement.

Known instances of class:
  - Alchemix: `@dev oracle-independent downside guard against pathological quotes`
    — declared but not enforced in all allocation paths
  - DeFi vaults: `@dev shares MUST never decrease` — but mint/burn rounding direction
    can violate
  - Bridges: `@dev message hash includes chainId` — but actual hash omits it

CLASSIFICATION:
  - [known_class] = matches one of the above known invariants
  - [novel_instance] = new self-declared invariant — HIGH PRIORITY
    (check if implementation actually enforces what comment promises)

Signals we extract:
  - `@dev` / `@notice` / `@inheritdoc` invariants
  - Explicit "MUST"/"should"/"never"/"always" statements
  - TODO/FIXME/XXX/HACK markers
  - Workaround-comments around MONEY MATH (waiting for / trick / absorbing / not supported /
    inaccurate / temporary) — developer-acknowledged imprecision near amount/fee/quote = divergence
    seed. Aave×CoW `// Trick waiting for CoW solvers precise hook simulation` (Ehsan 2026,
    reference_ehsan_aave_cow). Pair with a getter that `return undefined`s metadata it should provide.
  - "audit-resolved" / "fixed in" mentions
  - Phrases like "assumes X" / "if Y then Z"

Usage:
  python3 comment_miner.py --target path/to/Contract.sol --output sessions/X/hypothesis/

Output: comment_findings.json + comment_invariants.md
"""

import argparse
import json
import re
from pathlib import Path

# Comment extraction patterns
NATSPEC_BLOCK_RE = re.compile(r"/\*\*(.*?)\*/", re.DOTALL)
NATSPEC_LINE_RE = re.compile(r"///\s*(.*)")
LINE_COMMENT_RE = re.compile(r"//\s*(.*)")
BLOCK_COMMENT_RE = re.compile(r"/\*(.*?)\*/", re.DOTALL)

# Signal patterns within comments
SIGNAL_PATTERNS = {
    "invariant_must": re.compile(r"\b(MUST|must)\b\s+(?!be\s+called)(\w+)", re.IGNORECASE),
    "invariant_should": re.compile(r"\b(should always|should never|always|never)\b", re.IGNORECASE),
    "assumption": re.compile(r"\b(assume[sd]?|assuming)\b", re.IGNORECASE),
    "todo_fixme": re.compile(r"\b(TODO|FIXME|XXX|HACK|BUG)\b[:\s]", re.IGNORECASE),
    # Developer-acknowledged imprecision around money math (amount/fee/quote/simulation).
    # A workaround comment near financial arithmetic = a by-design divergence seed.
    # Source: Aave×CoW `// Trick waiting for CoW solvers precise hook simulation` + `networkFee × 3`
    # hack, and `getAppDataForQuote → undefined` (Ehsan 2026). See reference_ehsan_aave_cow.
    "workaround_finmath": re.compile(
        r"\b(waiting for|trick|workaround|absorbing|not currently supported|inaccurate|"
        r"imprecise|approximation|temporar|for now|until .{0,40}? (solved|fixed|supported))\b",
        re.IGNORECASE,
    ),
    "audit_mention": re.compile(r"\b(audit|fixed in|patched|resolved|known issue|see audit)\b", re.IGNORECASE),
    "warning": re.compile(r"\b(WARNING|CAUTION|DANGER|UNSAFE|deprecated)\b", re.IGNORECASE),
    "edge_case": re.compile(r"\b(edge case|corner case|pathological|degenerate|extreme)\b", re.IGNORECASE),
    "if_then": re.compile(r"\b(if\s+\w[\w\s]{0,50}then\b)", re.IGNORECASE),
    "natspec_dev": re.compile(r"@dev\s+(.{10,200})", re.IGNORECASE | re.DOTALL),
    "natspec_notice": re.compile(r"@notice\s+(.{10,200})", re.IGNORECASE | re.DOTALL),
    "natspec_param": re.compile(r"@param\s+\w+\s+(.{10,150})", re.IGNORECASE),
    "depeg_or_economic": re.compile(r"\b(depeg|de-peg|slippage|loss|drain|exploit|vulnerab)", re.IGNORECASE),
    "oracle_concern": re.compile(r"\b(oracle|price feed|stale price|chainlink|aggregator)\b", re.IGNORECASE),
    "reentrancy_concern": re.compile(r"\b(reentran|callback|cross-function|cross-contract)\b", re.IGNORECASE),
    "race_condition": re.compile(r"\b(race|atomic|order|sequence|reorg|MEV)\b", re.IGNORECASE),
}


def extract_comments(source: str) -> list[dict]:
    """Extract all comments with line numbers. Tracks consumed character ranges to avoid double-capture."""
    comments = []
    consumed_ranges: list[tuple[int, int]] = []

    def is_consumed(start: int, end: int) -> bool:
        for cs, ce in consumed_ranges:
            if start >= cs and end <= ce:
                return True
        return False

    # NatSpec block comments /** ... */ — extract first
    for m in NATSPEC_BLOCK_RE.finditer(source):
        line = source[: m.start()].count("\n") + 1
        text = m.group(1)
        text = re.sub(r"^\s*\*\s?", "", text, flags=re.MULTILINE).strip()
        if text:
            comments.append({"line": line, "type": "natspec_block", "text": text})
        consumed_ranges.append((m.start(), m.end()))

    # NatSpec line comments /// — skip if inside a block range
    for m in NATSPEC_LINE_RE.finditer(source):
        if is_consumed(m.start(), m.end()):
            continue
        line = source[: m.start()].count("\n") + 1
        consumed_ranges.append((m.start(), m.end()))
        comments.append({"line": line, "type": "natspec_line", "text": m.group(1).strip()})

    # Regular block comments /* ... */ — skip natspec already captured
    for m in BLOCK_COMMENT_RE.finditer(source):
        if source[m.start() : m.start() + 3] == "/**":
            continue
        if is_consumed(m.start(), m.end()):
            continue
        line = source[: m.start()].count("\n") + 1
        text = m.group(1).strip()
        if text:
            comments.append({"line": line, "type": "block", "text": text})
            consumed_ranges.append((m.start(), m.end()))

    # Regular line comments // — skip if part of /// or already consumed
    for m in LINE_COMMENT_RE.finditer(source):
        if m.start() >= 1 and source[m.start() - 1] == "/":
            continue
        if is_consumed(m.start(), m.end()):
            continue
        line = source[: m.start()].count("\n") + 1
        comments.append({"line": line, "type": "line", "text": m.group(1).strip()})

    return comments


def classify_comment(comment: dict) -> list[dict]:
    """Run all signal patterns against the comment text. Returns list of matched signals."""
    matches = []
    text = comment["text"]
    for signal_name, pattern in SIGNAL_PATTERNS.items():
        m = pattern.search(text)
        if m:
            matches.append({
                "signal": signal_name,
                "match": m.group(0)[:80],
                "comment_type": comment["type"],
            })
    return matches


def get_nearby_code(source_lines: list[str], comment_line: int, radius: int = 5) -> str:
    """Get a few lines of code after the comment to identify what it describes."""
    start = comment_line  # comment is at this line, code after
    end = min(len(source_lines), comment_line + radius)
    return "\n".join(f"  {i+1}: {line}" for i, line in enumerate(source_lines[start:end], start=start))


def scan_file(path: Path) -> dict:
    """Scan a single .sol file for comment-based hypothesis candidates."""
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {"file": str(path), "findings": [], "error": "read failed"}

    source_lines = source.splitlines()
    comments = extract_comments(source)
    findings = []

    for c in comments:
        signals = classify_comment(c)
        if not signals:
            continue
        nearby = get_nearby_code(source_lines, c["line"] - 1, radius=8)
        # Classification: match known instance markers
        text_lower = c["text"].lower()
        is_known = (
            ("oracle-independent" in text_lower and "depeg" in text_lower)  # Alchemix
            or ("shares" in text_lower and ("never decrease" in text_lower or "must increase" in text_lower))  # vault inflation
            or ("chainid" in text_lower and "hash" in text_lower)  # bridge replay
        )
        findings.append({
            "line": c["line"],
            "comment_type": c["type"],
            "text": c["text"][:300],
            "signals": [s["signal"] for s in signals],
            "matches": [s["match"] for s in signals],
            "nearby_code": nearby,
            "classification": "known_class" if is_known else "novel_instance",
            "class": "author_declared_invariant",
        })

    # Score severity: more signals = higher priority
    for f in findings:
        score = 0
        for s in f["signals"]:
            if s in ("audit_mention", "todo_fixme", "warning", "depeg_or_economic"):
                score += 3
            elif s in ("invariant_must", "invariant_should", "assumption"):
                score += 2
            else:
                score += 1
        f["priority"] = score

    findings.sort(key=lambda f: -f["priority"])

    return {
        "file": str(path),
        "comments_total": len(comments),
        "findings": findings,
    }


def scan_dir(target: Path) -> dict:
    """Recursive .sol scan."""
    if target.is_file():
        return {"files": [scan_file(target)]}
    files = sorted(target.rglob("*.sol"))
    files = [
        f for f in files
        if "node_modules" not in f.parts
        and "/lib/" not in str(f)
        and ".t.sol" not in f.name
        and "/test/" not in str(f)
    ]
    results = []
    for f in files:
        r = scan_file(f)
        if r.get("findings"):
            results.append(r)
    return {"files": results}


def format_md(report: dict) -> str:
    """Markdown output as hypothesis candidates."""
    lines = [
        "# Comment Mining — Hypothesis Candidates",
        "",
        "Extracted from Solidity comments: invariants, TODOs, audit-mentions, warnings.",
        "Each is a candidate hypothesis: \"the developer DOCUMENTED this; verify it actually holds.\"",
        "",
        "**Priority key**: audit/todo/warning = 3pt, invariant/assumption = 2pt, others = 1pt.",
        "",
        "---",
        "",
    ]

    findings_idx = 0
    for file_report in report["files"]:
        if not file_report.get("findings"):
            continue
        lines.append(f"## `{file_report['file']}`")
        lines.append("")
        for f in file_report["findings"]:
            findings_idx += 1
            signals_str = ", ".join(f["signals"])
            lines.append(f"### H{findings_idx}: `{file_report['file']}:{f['line']}` — priority {f['priority']}")
            lines.append("")
            lines.append(f"**Signals**: {signals_str}")
            lines.append(f"**Comment** ({f['comment_type']}):")
            lines.append("```")
            lines.append(f["text"])
            lines.append("```")
            lines.append("**Nearby code**:")
            lines.append("```solidity")
            lines.append(f["nearby_code"])
            lines.append("```")
            lines.append("")
            lines.append("**Verification plan**: Verify if statement in comment actually holds in all code paths. ")
            lines.append("If invariant — write Foundry invariant test. If TODO/FIXME — check if condition was fixed in code.")
            lines.append("")
            lines.append("---")
            lines.append("")

    if findings_idx == 0:
        lines.append("_No notable comments found._")

    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description="Mine Solidity comments for invariant/hypothesis candidates")
    p.add_argument("--target", required=True, help="Path to .sol file or directory")
    p.add_argument("--output", default=".", help="Output directory")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"ERROR: target does not exist: {target}")
        return 1

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.quiet:
        print(f"[*] Mining comments in {target}...")
    report = scan_dir(target)

    json_path = output_dir / "comment_findings.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    md_path = output_dir / "comment_invariants.md"
    md_path.write_text(format_md(report), encoding="utf-8")

    total_findings = sum(len(f.get("findings", [])) for f in report["files"])
    if not args.quiet:
        print(f"[+] Files with findings: {len(report['files'])}")
        print(f"[+] Total comment-based hypotheses: {total_findings}")
        print(f"[+] JSON: {json_path}")
        print(f"[+] Markdown: {md_path}")
        if total_findings > 0:
            print("\nTop findings:")
            all_findings = []
            for f in report["files"]:
                for finding in f.get("findings", []):
                    all_findings.append((f["file"], finding))
            all_findings.sort(key=lambda x: -x[1]["priority"])
            for file_path, f in all_findings[:5]:
                signals = ",".join(f["signals"][:3])
                print(f"  - {file_path}:{f['line']} [{signals}] priority={f['priority']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
