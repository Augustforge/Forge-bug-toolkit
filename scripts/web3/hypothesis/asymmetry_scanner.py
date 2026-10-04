#!/usr/bin/env python3
"""
asymmetry_scanner.py — Detector for broader class: SIBLING CONTROL-FLOW DRIFT.

CLASS: Sibling functions doing similar things but with different modifiers/checks/
state mutations. Drift = bug candidate. Each instance below is ONE manifestation
of this broader class — script finds NEW instances, not copies of these.

Known instances of class:
  - DeXe Protocol: delegateTokens missing `ifNotStaken` (siblings: withdrawTokens, stakeTokens have it)
  - Alchemix: _allocate vs _allocateWithSwap — one has oracle guard, other doesn't
  - Curve readonly reentrancy: getter functions returning state during mid-tx mutation

CLASSIFICATION:
  - [known_class] = matches one of the known instances above
  - [novel_instance] = new manifestation of class — HIGH PRIORITY for hunting

Usage:
  python3 asymmetry_scanner.py --target path/to/contracts/ --output sessions/X/hypothesis/
  python3 asymmetry_scanner.py --target path/to/Contract.sol --threshold 0.6

Output: hypothesis_candidates.json (with classification field) + asymmetry_report.md
"""

import argparse
import json
import re
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

# Regex patterns for Solidity function declaration
# Captures: visibility, name, params, modifiers (everything before { or ;)
FUNC_RE = re.compile(
    r"function\s+(\w+)\s*\(([^)]*)\)\s*"
    r"((?:public|external|internal|private)?\s*"
    r"(?:view|pure|payable)?\s*[^{;]*?)\s*"
    r"[\{;]",
    re.MULTILINE | re.DOTALL,
)

# Modifier extraction — anything in the "after params" section that looks like a modifier call
MODIFIER_RE = re.compile(r"\b([a-zA-Z_]\w*)\s*(?:\([^)]*\))?")

# Common Solidity keywords that aren't modifiers
KEYWORDS = {
    "public", "external", "internal", "private",
    "view", "pure", "payable", "returns", "override",
    "virtual", "abstract", "constant", "anonymous",
    "immutable",
}


def extract_functions(source: str, file_path: str) -> list[dict]:
    """Extract all functions with their modifiers from a Solidity source."""
    functions = []
    for match in FUNC_RE.finditer(source):
        name = match.group(1)
        params = match.group(2).strip()
        rest = match.group(3).strip()

        # Extract modifiers — words that aren't keywords or returns(...)
        # Remove returns(...) block first
        rest_clean = re.sub(r"returns\s*\([^)]*\)", "", rest)
        # Find all word-like tokens
        tokens = MODIFIER_RE.findall(rest_clean)
        modifiers = [t for t in tokens if t not in KEYWORDS]

        # Find line number
        line_num = source[: match.start()].count("\n") + 1

        functions.append({
            "name": name,
            "params": params,
            "modifiers": modifiers,
            "file": file_path,
            "line": line_num,
            "signature": f"{name}({params})",
        })
    return functions


def find_sibling_groups(functions: list[dict], min_similarity: float = 0.55) -> list[list[dict]]:
    """Group functions that look like siblings (similar names or similar params)."""
    groups = []
    used = set()

    for i, f1 in enumerate(functions):
        if i in used:
            continue
        group = [f1]
        for j, f2 in enumerate(functions[i + 1:], start=i + 1):
            if j in used:
                continue
            # Similarity by name OR by params signature
            name_sim = SequenceMatcher(None, f1["name"], f2["name"]).ratio()
            param_sim = SequenceMatcher(None, f1["params"], f2["params"]).ratio()
            # Sibling heuristics:
            # - Names share a common prefix or suffix (e.g., withdrawTokens, stakeTokens, delegateTokens — all end in "Tokens")
            # - Or names differ only by short prefix (e.g., _allocate vs _allocateWithSwap)
            # - Or very similar params
            common_suffix = _longest_common_suffix(f1["name"], f2["name"])
            common_prefix = _longest_common_prefix(f1["name"], f2["name"])
            is_sibling = (
                (len(common_suffix) >= 4 and len(common_suffix) >= min(len(f1["name"]), len(f2["name"])) * 0.4)
                or (len(common_prefix) >= 4 and len(common_prefix) >= min(len(f1["name"]), len(f2["name"])) * 0.4)
                or name_sim >= min_similarity
                or (param_sim >= 0.85 and f1["params"].strip() != "")
            )
            if is_sibling:
                group.append(f2)
                used.add(j)
        if len(group) >= 2:
            groups.append(group)
            used.add(i)
    return groups


def _longest_common_suffix(a: str, b: str) -> str:
    i = 0
    while i < len(a) and i < len(b) and a[-1 - i] == b[-1 - i]:
        i += 1
    return a[-i:] if i > 0 else ""


def _longest_common_prefix(a: str, b: str) -> str:
    i = 0
    while i < len(a) and i < len(b) and a[i] == b[i]:
        i += 1
    return a[:i]


def detect_asymmetries(group: list[dict]) -> list[dict]:
    """For a group of sibling functions, find which modifiers appear in some but not all.

    Two directions:
    1. Majority-present, minority-absent: modifier on most, missing on 1-2.
       This is the classic "forgot to add" pattern (DeXe withdrawTokens/delegateTokens/stakeTokens
       where 8 funcs have onlyOwner but stakeTokens doesn't).
    2. Minority-present, majority-absent: modifier on a few, missing on most.
       This catches DeXe's actual bug: ifNotStaken on withdraw+stake but missing on delegate.
       Lower confidence because more often legitimate (e.g., view functions don't need guards).

    We score by:
    - How "security-flavoured" the modifier name is (whitelist boost)
    - Group size (bigger group = stronger signal)
    - How balanced present/absent are
    """
    if len(group) < 2:
        return []

    # Modifiers that strongly suggest security checks (boost their priority)
    SECURITY_FLAVOURED = re.compile(
        r"^(if\w+|only\w+|when\w+|requires?\w*|ensures?\w*|"
        r"non[Rr]eentrant|nonReentrant|whenNotPaused|whenPaused|"
        r"checks?\w*|verif\w*|valid\w*|protect\w*|guard\w*|"
        r"locked|unlocked|notStaked|notStaken|hasRole)",
        re.IGNORECASE,
    )

    # Union of all modifiers
    all_mods = set()
    for fn in group:
        all_mods.update(fn["modifiers"])

    asymmetries = []
    for mod in all_mods:
        present_in = [fn for fn in group if mod in fn["modifiers"]]
        absent_in = [fn for fn in group if mod not in fn["modifiers"]]

        # Must be asymmetric (some have, some don't)
        if not present_in or not absent_in:
            continue
        if len(present_in) < 2 and len(absent_in) < 2:
            continue  # both sides too small, no clear pattern

        is_security = bool(SECURITY_FLAVOURED.match(mod))

        # Determine direction and confidence
        if len(absent_in) < len(present_in):
            # Majority-present, minority-absent (classic forgot-to-add)
            direction = "majority_present"
            base_confidence = "high" if len(absent_in) <= 2 else "medium"
        elif len(present_in) < len(absent_in):
            # Minority-present, majority-absent — DeXe-like pattern
            direction = "minority_present"
            # Lower base confidence; boost if security-flavoured
            if len(present_in) >= 2 and is_security:
                base_confidence = "high"
            elif len(present_in) >= 2:
                base_confidence = "medium"
            else:
                base_confidence = "low"
        else:
            # Equal split
            direction = "balanced"
            base_confidence = "low"

        # Skip very low confidence non-security signals to reduce noise
        if base_confidence == "low" and not is_security:
            continue

        # Classification: known_class vs novel_instance
        # Known instances of broader "sibling control-flow drift" class
        absent_names = {f["name"].lower() for f in absent_in}
        present_names = {f["name"].lower() for f in present_in}
        is_known = False
        if mod.lower() == "ifnotstaken" and "delegatetokens" in absent_names:
            is_known = True  # DeXe instance
        elif any(n.endswith("_allocate") for n in absent_names) and any(n.endswith("_allocatewithswap") for n in present_names):
            is_known = True  # Alchemix instance

        asymmetries.append({
            "modifier": mod,
            "is_security_flavoured": is_security,
            "direction": direction,
            "present_in": [{"name": f["name"], "file": f["file"], "line": f["line"]} for f in present_in],
            "absent_in": [{"name": f["name"], "file": f["file"], "line": f["line"]} for f in absent_in],
            "confidence": base_confidence,
            "classification": "known_class" if is_known else "novel_instance",
            "class": "sibling_control_flow_drift",
        })
    return asymmetries


def scan_file(path: Path) -> tuple[list[dict], list[dict]]:
    """Returns (functions, asymmetries) for a single .sol file."""
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return [], []
    functions = extract_functions(source, str(path))
    groups = find_sibling_groups(functions)
    asymmetries = []
    for group in groups:
        for asym in detect_asymmetries(group):
            asym["sibling_group"] = [f["name"] for f in group]
            asym["file"] = str(path)
            asymmetries.append(asym)
    return functions, asymmetries


def scan_dir(target: Path) -> dict:
    """Scan a directory recursively for .sol files."""
    all_funcs: list[dict] = []
    all_asyms: list[dict] = []
    files_scanned = 0
    sol_files = sorted(target.rglob("*.sol")) if target.is_dir() else [target]
    # Filter out common library/test dirs
    sol_files = [
        f for f in sol_files
        if "node_modules" not in f.parts
        and "lib/" not in str(f)
        and "/lib/" not in str(f)
        and ".t.sol" not in f.name
        and "/test/" not in str(f)
        and "/tests/" not in str(f)
    ]
    for sol_file in sol_files:
        files_scanned += 1
        funcs, asyms = scan_file(sol_file)
        all_funcs.extend(funcs)
        all_asyms.extend(asyms)

    return {
        "files_scanned": files_scanned,
        "functions_found": len(all_funcs),
        "asymmetries": all_asyms,
    }


def format_hypothesis_md(report: dict) -> str:
    """Convert asymmetry findings to hypothesis_candidates.md format."""
    lines = [
        "# Hypothesis Candidates — Asymmetry Scanner Output",
        "",
        f"**Files scanned**: {report['files_scanned']}",
        f"**Functions analyzed**: {report['functions_found']}",
        f"**Asymmetries detected**: {len(report['asymmetries'])}",
        "",
        "Each asymmetry is a candidate hypothesis: function missing a modifier present in siblings.",
        "Validation: check intent. If modifier protects an invariant (e.g., `ifNotStaken`), absence in",
        "sibling = likely bug. If modifier is cosmetic (e.g., `view` annotation), false positive.",
        "",
        "---",
        "",
    ]

    for idx, asym in enumerate(report["asymmetries"], 1):
        present_names = ", ".join(f["name"] for f in asym["present_in"])
        absent_names = ", ".join(f["name"] for f in asym["absent_in"])
        first_absent = asym["absent_in"][0]
        lines.append(f"## H{idx}: `{asym['modifier']}` missing in `{absent_names}`")
        lines.append("")
        lines.append(f"- **File**: `{asym['file']}`")
        lines.append(f"- **Sibling group**: `{', '.join(asym['sibling_group'])}`")
        lines.append(f"- **Modifier present in**: `{present_names}`")
        lines.append(f"- **Modifier absent in**: `{absent_names}` (line {first_absent['line']})")
        lines.append(f"- **Confidence**: {asym['confidence']}")
        lines.append("")
        lines.append(f"**Hypothesis**: If `{asym['modifier']}` enforces an invariant in `{present_names}`, ")
        lines.append(f"then `{absent_names}` violates that invariant. Verify by checking modifier body ")
        lines.append(f"and reasoning whether the absent function should require the same guarantee.")
        lines.append("")
        lines.append("**Verification plan**: ")
        lines.append(f"1. Read `{asym['modifier']}` definition — what state does it check?")
        lines.append(f"2. For `{absent_names}` — does same invariant apply?")
        lines.append(f"3. If yes — write Foundry test demonstrating the bug.")
        lines.append("")
        lines.append("---")
        lines.append("")

    if not report["asymmetries"]:
        lines.append("_No asymmetries detected. Either codebase is consistent, or threshold too high._")
        lines.append("_Try lowering `--min-similarity` or check that target has Solidity files._")

    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description="Find sibling functions with asymmetric modifiers (DeXe pattern)")
    p.add_argument("--target", required=True, help="Path to .sol file or directory")
    p.add_argument("--output", default=".", help="Output directory")
    p.add_argument("--min-similarity", type=float, default=0.55, help="Sibling similarity threshold (default 0.55)")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"ERROR: target does not exist: {target}")
        return 1

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.quiet:
        print(f"[*] Scanning {target}...")
    report = scan_dir(target)

    # Write JSON
    json_path = output_dir / "asymmetry_report.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Write markdown
    md_path = output_dir / "hypothesis_candidates.md"
    md_path.write_text(format_hypothesis_md(report), encoding="utf-8")

    if not args.quiet:
        print(f"[+] Scanned {report['files_scanned']} files, {report['functions_found']} functions.")
        print(f"[+] Found {len(report['asymmetries'])} asymmetries.")
        print(f"[+] JSON: {json_path}")
        print(f"[+] Markdown: {md_path}")
        if report["asymmetries"]:
            print("\nTop findings:")
            for asym in report["asymmetries"][:5]:
                absent = asym["absent_in"][0]
                print(f"  - {absent['name']:30s} missing '{asym['modifier']}' (line {absent['line']}) — confidence {asym['confidence']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
