#!/usr/bin/env python3
"""
state_setup_miner.py — Find rare state configurations that may trigger bugs.

Approach:
1. Identify state variables that gate function behavior (used in require/if/modifier)
2. Compute possible value combinations (especially edges: 0, 1, max, near-max)
3. For each "rare config" — flag for explicit testing

Used in /deephunt J0 (Hypothesis Generation) for long-undiscovered bugs.

Usage:
  python3 state_setup_miner.py --target path/to/Contract.sol --output sessions/X/hypothesis/

Output: state_configs.json + state_configs.md
"""

import argparse
import json
import re
from pathlib import Path

# State variable declarations
# Captures: visibility, type, name, optional default
STATE_VAR_RE = re.compile(
    r"^\s*(?:(public|private|internal)\s+)?"
    r"(?:(constant|immutable)\s+)?"
    r"((?:uint\d*|int\d*|address|bool|bytes\d*|string|"
    r"mapping\([^)]+\)|[A-Z]\w*(?:\.[A-Z]\w*)?)"
    r"(?:\[\d*\])?)\s+"
    r"(?:(public|private|internal)\s+)?"
    r"(?:(constant|immutable)\s+)?"
    r"(\w+)\s*(?:=\s*([^;]+))?\s*;",
    re.MULTILINE,
)

# require / if conditions
COND_RE = re.compile(
    r"(?:require|if|while)\s*\(([^;{]+)\)",
    re.MULTILINE | re.DOTALL,
)

# modifier definition
MODIFIER_DEF_RE = re.compile(r"modifier\s+\w+\s*\([^)]*\)\s*\{([^{}]*)\}", re.DOTALL)

# Boolean flag patterns
BOOL_FLAG_RE = re.compile(r"\b(paused|locked|initialized|enabled|active|frozen|emergency)\b", re.IGNORECASE)

# Range bound patterns
RANGE_PATTERNS = [
    (r"<\s*(\w+)", "less_than"),
    (r">\s*(\w+)", "greater_than"),
    (r"<=\s*(\w+)", "less_eq"),
    (r">=\s*(\w+)", "greater_eq"),
    (r"==\s*(\w+)", "equal"),
    (r"!=\s*(\w+)", "not_equal"),
]


def extract_state_vars(source: str) -> list[dict]:
    """Extract state variable declarations."""
    state_vars = []
    for m in STATE_VAR_RE.finditer(source):
        # Skip if inside function body — heuristic: check for `function` keyword in nearest 200 chars before
        before = source[max(0, m.start() - 500) : m.start()]
        # Match brace depth - state vars are at contract scope, not function scope
        # Crude: count { vs } since last contract/library/interface keyword
        contract_match = list(re.finditer(r"\b(contract|library|interface|abstract\s+contract)\s+\w+", before))
        if not contract_match:
            continue
        # Check we're not inside a function
        last_contract_end = contract_match[-1].end()
        body_after = before[last_contract_end:]
        brace_depth = body_after.count("{") - body_after.count("}")
        if brace_depth != 1:  # not directly inside contract scope
            continue

        var_type = m.group(3)
        name = m.group(5)
        default = m.group(6)
        is_const = m.group(2) == "constant" or m.group(4) == "constant"
        is_immut = m.group(2) == "immutable" or m.group(4) == "immutable"
        line = source[: m.start()].count("\n") + 1

        # Skip constants and immutables — they can't change
        if is_const or is_immut:
            continue
        # Skip if name didn't capture
        if not name:
            continue

        state_vars.append({
            "name": name,
            "type": var_type.strip() if var_type else "unknown",
            "default": default.strip() if default else None,
            "line": line,
            "is_bool_flag": bool(BOOL_FLAG_RE.match(name)),
        })
    return state_vars


def find_gating_conditions(source: str, var_names: set) -> list[dict]:
    """Find conditions (require/if) that gate on state variables."""
    conditions = []
    for m in COND_RE.finditer(source):
        cond_text = m.group(1).strip()
        # Find which state vars are mentioned
        mentioned = [v for v in var_names if re.search(rf"\b{re.escape(v)}\b", cond_text)]
        if not mentioned:
            continue
        line = source[: m.start()].count("\n") + 1
        conditions.append({
            "line": line,
            "condition": cond_text[:200],
            "state_vars": mentioned,
        })
    return conditions


def compute_rare_configs(state_vars: list[dict], conditions: list[dict]) -> list[dict]:
    """For each gating state var, identify edge configs worth testing."""
    rare_configs = []

    # Index conditions by mentioned var
    var_to_conds: dict[str, list[dict]] = {}
    for c in conditions:
        for v in c["state_vars"]:
            var_to_conds.setdefault(v, []).append(c)

    for v in state_vars:
        gating = var_to_conds.get(v["name"], [])
        if not gating:
            continue

        # Suggest edge values based on type
        edges = []
        t = v["type"]
        if t.startswith("uint"):
            edges = [
                {"value": "0", "rationale": "zero may be default/unset"},
                {"value": "1", "rationale": "boundary of >0 checks"},
                {"value": "type(uint256).max", "rationale": "overflow on +1"},
                {"value": "type(uint256).max - 1", "rationale": "boundary of <max checks"},
            ]
        elif t.startswith("int"):
            edges = [
                {"value": "0", "rationale": "neutral"},
                {"value": "-1", "rationale": "negative edge"},
                {"value": "type(int256).min", "rationale": "overflow on -1 or abs()"},
                {"value": "type(int256).max", "rationale": "overflow"},
            ]
        elif t == "bool":
            edges = [
                {"value": "false (default)", "rationale": "default unset state"},
                {"value": "true", "rationale": "explicitly set state"},
            ]
        elif t == "address":
            edges = [
                {"value": "address(0)", "rationale": "uninitialized / zero address bypass"},
                {"value": "address(this)", "rationale": "self-reference"},
                {"value": "address(0xdead)", "rationale": "burn address"},
            ]
        elif t.startswith("bytes"):
            edges = [
                {"value": "0x0...0", "rationale": "zero hash collision"},
                {"value": "type(bytes32).max", "rationale": "all-bits-set"},
            ]

        rare_configs.append({
            "variable": v["name"],
            "type": v["type"],
            "default": v["default"],
            "line": v["line"],
            "gating_conditions": [{"line": c["line"], "condition": c["condition"]} for c in gating[:5]],
            "edge_values_to_test": edges,
            "priority": "high" if v["is_bool_flag"] else "medium",
        })

    return rare_configs


def detect_combinatorial_setups(state_vars: list[dict], conditions: list[dict]) -> list[dict]:
    """Detect when 2+ state vars are checked together — rare combos worth exploring."""
    combos = []
    for c in conditions:
        if len(c["state_vars"]) >= 2:
            combos.append({
                "line": c["line"],
                "condition": c["condition"],
                "state_vars": c["state_vars"],
                "edge_combos": [
                    {v: "default/zero" for v in c["state_vars"]},
                    {v: "max" for v in c["state_vars"]},
                    # Mixed: first var at edge, others default
                    {**{c["state_vars"][0]: "max"}, **{v: "default" for v in c["state_vars"][1:]}},
                ],
            })
    return combos


def scan_file(path: Path) -> dict:
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {"error": "read failed"}

    state_vars = extract_state_vars(source)
    var_names = {v["name"] for v in state_vars}
    conditions = find_gating_conditions(source, var_names)
    rare_configs = compute_rare_configs(state_vars, conditions)
    combinatorial = detect_combinatorial_setups(state_vars, conditions)

    return {
        "file": str(path),
        "state_vars_total": len(state_vars),
        "gating_conditions": len(conditions),
        "rare_configs": rare_configs,
        "combinatorial_setups": combinatorial,
    }


def scan_dir(target: Path) -> dict:
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
        if r.get("rare_configs") or r.get("combinatorial_setups"):
            results.append(r)
    return {"files": results}


def format_md(report: dict) -> str:
    lines = [
        "# State Setup Mining — Rare Configurations to Test",
        "",
        "Each rare config = a hypothesis. Test if function behavior is correct under edge value.",
        "Bugs that survive audits often need specific state combinations to manifest.",
        "",
        "---",
        "",
    ]
    idx = 0
    for fr in report["files"]:
        if "error" in fr or not fr.get("rare_configs"):
            continue
        lines.append(f"## `{fr['file']}`")
        lines.append("")
        lines.append(f"- State vars: {fr['state_vars_total']}, gating conditions: {fr['gating_conditions']}")
        lines.append("")

        for rc in fr["rare_configs"]:
            idx += 1
            lines.append(f"### H{idx}: `{rc['variable']}` (`{rc['type']}`) at line {rc['line']} — priority {rc['priority']}")
            lines.append("")
            lines.append(f"**Gating conditions** (top 5):")
            for gc in rc["gating_conditions"]:
                lines.append(f"  - L{gc['line']}: `{gc['condition'][:120]}`")
            lines.append("")
            lines.append(f"**Edge values to explicitly test**:")
            for ev in rc["edge_values_to_test"]:
                lines.append(f"  - `{ev['value']}` — {ev['rationale']}")
            lines.append("")

        if fr.get("combinatorial_setups"):
            lines.append(f"### Combinatorial setups (multi-var checks)")
            for combo in fr["combinatorial_setups"][:10]:
                lines.append(f"  - L{combo['line']}: vars={combo['state_vars']}")
                lines.append(f"    `{combo['condition'][:120]}`")
            lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description="Mine rare state configurations for hypothesis testing")
    p.add_argument("--target", required=True)
    p.add_argument("--output", default=".")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"ERROR: {target} does not exist")
        return 1

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.quiet:
        print(f"[*] Mining state setups in {target}...")

    report = scan_dir(target)
    (output_dir / "state_configs.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (output_dir / "state_configs.md").write_text(format_md(report), encoding="utf-8")

    total_configs = sum(len(f.get("rare_configs", [])) for f in report["files"])
    if not args.quiet:
        print(f"[+] Files with configs: {len(report['files'])}")
        print(f"[+] Total rare configs: {total_configs}")
        print(f"[+] Output: {output_dir}/state_configs.{{json,md}}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
