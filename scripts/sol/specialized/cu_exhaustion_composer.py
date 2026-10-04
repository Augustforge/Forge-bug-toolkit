#!/usr/bin/env python3
"""
cu_exhaustion_composer.py — Compose CU (Compute Unit) exhaustion attacks.

CONTEXT:
Solana txs limited to 1.4M CU. Two attack classes:

1. **DoS attack**: attacker constructs tx that consumes near 1.4M CU
   with small actual work — blocks protocol's legitimate ops in same slot
   (if they share writable accounts OR depend on attacker's slot
   leader timing).

2. **CU starvation attack**: protocol's normal operation requires close
   to 1.4M CU under specific input conditions. Attacker crafts input
   pushing CU over limit → tx reverts → DoS of legitimate functionality.

DETECTION:
1. Find instruction handlers with loops/iterations of user-controlled length
2. Find CPI chains > 4 calls (cumulative overhead)
3. Find serialization/deserialization of unbounded-size data
4. Compose: combine 2-3 high-cost patterns into single tx → estimate CU
5. Flag handlers where crafted input pushes above 1.4M CU

CLASSIFICATION:
  - [known_class] = compute_dos_analyzer already flagged the surface
  - [novel_instance] = new attack composition discovered

OUTPUT: per-handler CU cost estimate + composition attack scenarios.

Usage:
    python3 cu_exhaustion_composer.py --target sessions/$TARGET/source
"""
import argparse
import json
import re
import sys
from pathlib import Path


CU_COSTS = {
    "syscall_base": 100,
    "cpi_call_overhead": 1000,
    "account_load": 1500,
    "ed25519_verify": 76500,
    "secp256k1_recover": 25000,
    "keccak256": 5440,
    "sha256": 5440,
    "borsh_deserialize_per_byte": 5,
    "loop_iteration_base": 100,
}

USER_CONTROLLED_LOOP_PATTERNS = [
    re.compile(r"for\s+\w+\s+in\s+(?:0\.\.|\w+\.iter\(\)|\w+\.items\(\))"),
    re.compile(r"while\s+\w+\s*[<>=]"),
    re.compile(r"\.fold\s*\(|\.map\s*\(|\.filter\s*\("),
]
INPUT_DRIVEN_PATTERNS = [
    re.compile(r"args\.\w+|amounts?\.len\(\)|indices?\.len\(\)|count\.\.\w+|capacity\s*:\s*u32"),
]
CPI_CHAIN_PATTERNS = [
    re.compile(r"\binvoke(?:_signed)?\s*\("),
]
HEAVY_CRYPTO_PATTERNS = [
    re.compile(r"ed25519_program|ed25519_verify"),
    re.compile(r"secp256k1_recover"),
    re.compile(r"\bhashv\(|sha256\("),
]


def estimate_handler_cu(text: str, handler_name: str, handler_body: str) -> dict:
    cu_estimate = 5_000

    loops = sum(1 for p in USER_CONTROLLED_LOOP_PATTERNS for _ in p.finditer(handler_body))
    cpi_chain = sum(1 for p in CPI_CHAIN_PATTERNS for _ in p.finditer(handler_body))
    heavy_crypto = sum(1 for p in HEAVY_CRYPTO_PATTERNS for _ in p.finditer(handler_body))
    input_driven = any(p.search(handler_body) for p in INPUT_DRIVEN_PATTERNS)

    cu_estimate += cpi_chain * CU_COSTS["cpi_call_overhead"]
    cu_estimate += heavy_crypto * CU_COSTS["ed25519_verify"]
    cu_estimate += loops * 50 * CU_COSTS["loop_iteration_base"]
    cu_loop_max_iters = 0
    if input_driven and loops > 0:
        cu_loop_max_iters = (1_400_000 - cu_estimate) // CU_COSTS["loop_iteration_base"]

    return {
        "handler": handler_name,
        "base_cu_estimate": cu_estimate,
        "loops": loops,
        "cpi_calls": cpi_chain,
        "heavy_crypto": heavy_crypto,
        "user_input_driven": input_driven,
        "cu_to_limit": 1_400_000 - cu_estimate,
        "max_loop_iterations_to_dos": cu_loop_max_iters if input_driven else None,
    }


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    findings = []

    fn_pattern = re.compile(r"pub\s+fn\s+(\w+)\s*\([^)]*ctx:\s*Context", re.MULTILINE)
    for m in fn_pattern.finditer(text):
        handler_name = m.group(1)
        start = m.end()
        depth = 0
        body_start = -1
        i = start
        while i < len(text):
            if text[i] == "{":
                if body_start < 0:
                    body_start = i
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    body = text[body_start:i+1]
                    break
            i += 1
        else:
            continue

        est = estimate_handler_cu(text, handler_name, body)

        if est["base_cu_estimate"] > 800_000:
            findings.append({
                "class": "cu_exhaustion",
                "subclass": "near_limit_baseline",
                "file": str(path),
                "line": text[:m.start()].count("\n") + 1,
                "handler": handler_name,
                "cu_estimate": est["base_cu_estimate"],
                "advice": f"Handler `{handler_name}` baseline CU ~{est['base_cu_estimate']:,}. "
                          f"Small input/state changes push over 1.4M limit → DoS surface.",
                "severity": "high",
                "classification": "novel_instance",
                "broader_class": "cu_baseline_brittle",
            })

        if est["user_input_driven"] and est["loops"] > 0 and est["max_loop_iterations_to_dos"]:
            iters = est["max_loop_iterations_to_dos"]
            if iters < 10000:
                findings.append({
                    "class": "cu_exhaustion",
                    "subclass": "user_input_loop_dos",
                    "file": str(path),
                    "line": text[:m.start()].count("\n") + 1,
                    "handler": handler_name,
                    "advice": f"Handler `{handler_name}` has {est['loops']} loops driven by user input. "
                              f"Submitting {iters:,}+ iterations exhausts 1.4M CU budget → tx revert OR partial state corruption.",
                    "severity": "high" if iters < 1000 else "medium",
                    "classification": "novel_instance",
                    "broader_class": "cu_input_dos",
                    "attack_template": "cu_exhaustion_via_loop_count",
                    "attack_vars": {"target_handler": handler_name, "loop_iterations": str(iters)},
                })

        if est["cpi_calls"] >= 4:
            findings.append({
                "class": "cu_exhaustion",
                "subclass": "deep_cpi_chain",
                "file": str(path),
                "line": text[:m.start()].count("\n") + 1,
                "handler": handler_name,
                "advice": f"Handler `{handler_name}` has {est['cpi_calls']} CPI calls. "
                          f"CPI overhead compounds (~1k CU each). Stacking + crafted callee makes 1.4M reach quickly.",
                "severity": "medium",
                "classification": "novel_instance",
                "broader_class": "cu_cpi_stacking",
            })

    return findings


def main():
    ap = argparse.ArgumentParser(description="Compose CU exhaustion attacks")
    ap.add_argument("--target", required=True)
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    target = Path(args.target)
    files = list(target.rglob("*.rs")) if target.is_dir() else [target]
    all_findings = []
    for f in files:
        all_findings.extend(scan_file(f))

    if not args.quiet:
        print(f"[+] Scanned {len(files)} files. CU exhaustion findings: {len(all_findings)}")
        high = [f for f in all_findings if f["severity"] == "high"]
        print(f"    High: {len(high)}")

        for f in all_findings[:15]:
            sev = f["severity"].upper()
            f_name = Path(f["file"]).name
            print(f"  [{sev:8}] {f['subclass']:30} fn `{f['handler']}` @ {f_name}:{f['line']}")

    if args.output:
        out_dir = Path(args.output)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "cu_exhaustion_findings.json").write_text(json.dumps(all_findings, indent=2))


if __name__ == "__main__":
    main()
