#!/usr/bin/env python3
"""
inverse_op_symmetry.py — Detector for broader class: INVERSE OPERATION ASYMMETRY.

CLASS: pairs of operations that should be mathematical inverses, but
use asymmetric arithmetic (same rounding direction) → profitable
round-trip.

Known instances of class:
  - Sec3 blog 2025: bidirectional rounding in AMM/lending
  - Kamino-class precision loss
  - Generic: mint with floor + redeem with floor (should be floor + ceil)

Detection strategy:
1. Find inverse-operation function pairs (mint/burn, deposit/withdraw,
   swap_a_to_b/swap_b_to_a, lock/unlock, stake/unstake)
2. For each pair — extract arithmetic operations (mul/div)
3. Compare rounding direction (floor vs ceil)
4. Flag if same direction
"""
import argparse
import json
import re
import sys
from pathlib import Path


INVERSE_PAIRS = [
    ("mint", "burn"),
    ("mint", "redeem"),
    ("deposit", "withdraw"),
    ("stake", "unstake"),
    ("lock", "unlock"),
    ("lend", "repay"),
    ("borrow", "repay"),
    ("buy", "sell"),
    ("swap_a_to_b", "swap_b_to_a"),
    ("wrap", "unwrap"),
]

FN_RE = re.compile(r"pub\s+fn\s+(\w+)\s*\([^)]*\)[^{]*\{")
FLOOR_OP_RE = re.compile(r"\.checked_div\(|\.\s*div\s*\(|\s/\s")
CEIL_OP_RE = re.compile(r"div_ceil|ceil_div|round_up|saturating_add\s*\(\s*1\s*\)\s*\.\s*checked_div")


def extract_function_body(text: str, fn_start: int) -> str:
    body_start = text.find("{", fn_start)
    if body_start < 0:
        return ""
    depth = 0
    i = body_start
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[body_start:i + 1]
        i += 1
    return text[body_start:]


def analyze_rounding(body: str) -> dict:
    floor_count = len(FLOOR_OP_RE.findall(body))
    ceil_count = len(CEIL_OP_RE.findall(body))
    return {"floor": floor_count, "ceil": ceil_count}


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    findings = []

    functions = {}
    for m in FN_RE.finditer(text):
        name = m.group(1).lower()
        line_no = text[: m.start()].count("\n") + 1
        body = extract_function_body(text, m.start())
        functions[name] = {
            "name": m.group(1),
            "line": line_no,
            "body": body,
            "rounding": analyze_rounding(body),
        }

    for pair in INVERSE_PAIRS:
        a_match = [fn for n, fn in functions.items() if pair[0] in n]
        b_match = [fn for n, fn in functions.items() if pair[1] in n]
        if not a_match or not b_match:
            continue
        a = a_match[0]
        b = b_match[0]
        a_round = a["rounding"]
        b_round = b["rounding"]

        a_dir = "floor" if a_round["floor"] > a_round["ceil"] else ("ceil" if a_round["ceil"] > 0 else "none")
        b_dir = "floor" if b_round["floor"] > b_round["ceil"] else ("ceil" if b_round["ceil"] > 0 else "none")

        if a_dir == b_dir and a_dir != "none":
            is_known_pair = pair in [("mint", "burn"), ("mint", "redeem"), ("deposit", "withdraw")]
            findings.append({
                "class": "inverse_op_asymmetry",
                "subclass": f"{pair[0]}_{pair[1]}_same_rounding",
                "file": str(path),
                "line": a["line"],
                "function_a": a["name"],
                "function_b": b["name"],
                "function_b_line": b["line"],
                "rounding_a": a_dir,
                "rounding_b": b_dir,
                "advice": f"Inverse operations `{a['name']}` ({a_dir} rounding) and `{b['name']}` "
                          f"({b_dir} rounding) — same direction. "
                          f"For safety: one should round down, other round up. "
                          f"Profit round-trip possible.",
                "severity": "high" if is_known_pair else "medium",
                "classification": "known_class" if is_known_pair else "novel_instance",
            })

    return findings


def main():
    ap = argparse.ArgumentParser(description="Find inverse operation asymmetry")
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

    if not args.quiet:
        print(f"[+] Inverse op asymmetries: {len(all_findings)}")
        for f in all_findings[:10]:
            tag = "NOVEL" if f["classification"] == "novel_instance" else "known"
            print(f"  [{f['severity']:8}] [{tag}] {f['function_a']} + {f['function_b']} ({f['rounding_a']})")

    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "inverse_op_findings.json").write_text(json.dumps(all_findings, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
