#!/usr/bin/env python3
"""
variant_scanner.py — Find same bug pattern in other places (class-of-bug expansion).

After confirming bug in FunctionA, scan whole codebase for similar functions
that might have the same bug. Real example: Alchemix WstETH bug existed identically
in SFraxETH — same auditor, same architecture, same missing oracle guard.

Approach:
1. Take a pattern (e.g., "function names matching X, missing modifier Y")
2. Scan whole codebase
3. Output candidates with similarity score

Used in /deephunt J6 (Variant Scan + Class-of-Bug Expansion).

Usage:
  python3 variant_scanner.py --target <dir> --pattern-function _allocate --pattern-missing-modifier oracleCheck
  python3 variant_scanner.py --target <dir> --pattern-from <findings.json>

Output: variants.json + variants.md
"""

import argparse
import json
import re
from pathlib import Path

FUNC_RE = re.compile(
    r"function\s+(\w+)\s*\(([^)]*)\)\s*([^{;]*)\s*[\{;]",
    re.MULTILINE | re.DOTALL,
)


def extract_functions(source: str) -> list[dict]:
    funcs = []
    for m in FUNC_RE.finditer(source):
        name = m.group(1)
        params = m.group(2).strip()
        modifiers_rest = m.group(3).strip()
        line = source[: m.start()].count("\n") + 1

        # Get function body (best-effort)
        body_start = m.end()
        depth = 1
        i = body_start
        while i < len(source) and depth > 0:
            if source[i] == "{":
                depth += 1
            elif source[i] == "}":
                depth -= 1
            i += 1
        body = source[body_start:i]

        funcs.append({
            "name": name,
            "params": params,
            "modifiers_rest": modifiers_rest,
            "body": body[:2000],
            "line": line,
        })
    return funcs


def name_similarity(a: str, b: str) -> float:
    """Simple name similarity (0-1)."""
    if a == b:
        return 1.0
    if a.lower() == b.lower():
        return 0.95
    # Common prefix/suffix
    common_prefix = 0
    for i in range(min(len(a), len(b))):
        if a[i].lower() == b[i].lower():
            common_prefix += 1
        else:
            break
    common_suffix = 0
    for i in range(1, min(len(a), len(b)) + 1):
        if a[-i].lower() == b[-i].lower():
            common_suffix += 1
        else:
            break
    return max(common_prefix, common_suffix) / max(len(a), len(b))


def find_variants(
    target_dir: Path,
    pattern_function_name: str = None,
    pattern_missing_modifier: str = None,
    pattern_keywords: list[str] = None,
    similarity_threshold: float = 0.5,
) -> list[dict]:
    """Scan for variant functions matching pattern."""
    candidates = []
    sol_files = sorted(target_dir.rglob("*.sol")) if target_dir.is_dir() else [target_dir]
    sol_files = [
        f for f in sol_files
        if "node_modules" not in f.parts
        and "/lib/" not in str(f)
        and ".t.sol" not in f.name
        and "/test/" not in str(f)
    ]

    for sol_file in sol_files:
        try:
            source = sol_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        funcs = extract_functions(source)
        for fn in funcs:
            score = 0
            reasons = []

            # Name similarity to pattern function name
            if pattern_function_name:
                sim = name_similarity(fn["name"], pattern_function_name)
                if sim >= similarity_threshold:
                    score += int(sim * 100)
                    reasons.append(f"name_similarity={sim:.2f}")

            # Body contains keywords
            if pattern_keywords:
                for kw in pattern_keywords:
                    if kw.lower() in fn["body"].lower():
                        score += 20
                        reasons.append(f"body_contains:{kw}")

            # Missing the specific modifier
            if pattern_missing_modifier:
                if pattern_missing_modifier not in fn["modifiers_rest"]:
                    # Plus: only relevant if similar function name OR similar body
                    if score > 0:
                        score += 30
                        reasons.append(f"missing_modifier:{pattern_missing_modifier}")

            if score >= 50:
                # Variant of a known bug pattern (Alchemix WstETH -> SFraxETH replication)
                # if score >= 80 = strong match (likely same bug class instance)
                # if 50 <= score < 80 = novel variant (similar surface, possibly different bug)
                classification = "known_class" if score >= 80 else "novel_instance"
                candidates.append({
                    "file": str(sol_file),
                    "function": fn["name"],
                    "line": fn["line"],
                    "score": score,
                    "classification": classification,
                    "broader_class": "class_of_bug_expansion",
                    "reasons": reasons,
                    "modifiers_present": fn["modifiers_rest"][:150],
                })

    candidates.sort(key=lambda c: -c["score"])
    return candidates


def main():
    p = argparse.ArgumentParser(description="Find variant functions with same bug class pattern")
    p.add_argument("--target", required=True, help="Directory or file to scan")
    p.add_argument("--pattern-function", help="Function name to find similar to")
    p.add_argument("--pattern-missing-modifier", help="Modifier that should be present (variant lacks it)")
    p.add_argument("--pattern-keywords", help="Comma-separated keywords likely in vulnerable body")
    p.add_argument("--similarity-threshold", type=float, default=0.4)
    p.add_argument("--output", default=".")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"ERROR: {target} does not exist")
        return 1

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    keywords = [k.strip() for k in args.pattern_keywords.split(",")] if args.pattern_keywords else None

    if not args.quiet:
        print(f"[*] Searching for variants in {target}")
        print(f"    pattern_function={args.pattern_function}, missing_modifier={args.pattern_missing_modifier}")

    variants = find_variants(
        target,
        pattern_function_name=args.pattern_function,
        pattern_missing_modifier=args.pattern_missing_modifier,
        pattern_keywords=keywords,
        similarity_threshold=args.similarity_threshold,
    )

    output = {
        "pattern": {
            "function": args.pattern_function,
            "missing_modifier": args.pattern_missing_modifier,
            "keywords": keywords,
        },
        "variants": variants,
    }

    (output_dir / "variants.json").write_text(json.dumps(output, indent=2), encoding="utf-8")

    # Markdown
    md = ["# Variant Scan Results", ""]
    md.append(f"**Pattern**: function={args.pattern_function}, missing={args.pattern_missing_modifier}, keywords={keywords}")
    md.append("")
    md.append(f"**Total variants found**: {len(variants)}")
    md.append("")
    for v in variants[:30]:
        md.append(f"- `{v['file']}:{v['line']}` `{v['function']}()` — score {v['score']}")
        md.append(f"  - Reasons: {', '.join(v['reasons'])}")
        md.append(f"  - Modifiers: `{v['modifiers_present']}`")
    (output_dir / "variants.md").write_text("\n".join(md), encoding="utf-8")

    if not args.quiet:
        print(f"[+] Variants found: {len(variants)}")
        for v in variants[:5]:
            print(f"  - {v['file']}:{v['line']} {v['function']}() score={v['score']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
