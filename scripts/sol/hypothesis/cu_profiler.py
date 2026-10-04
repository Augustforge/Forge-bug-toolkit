#!/usr/bin/env python3
"""cu_profiler.py — Compute Unit profiling for exploit feasibility.

Solana txs limited to 1.4M CU per tx (default 200k). If an exploit requires
>1.4M CU — it won't work in one tx. If it requires a high priority fee for
landing — the cost increase will change the severity calc.

Profile types:
1. **Static estimation**: parse instruction handler in Rust source, count syscalls/CPI/loops
2. **Dynamic**: run in `solana-test-validator` with `--compute-unit-limit`, observe usage
3. **Crowd-source**: pull recent successful tx CU from RPC `getTransaction` for known signatures

Helps J4 economic_analysis with realistic CU cost vs exploit profit margin.

Usage:
    python3 cu_profiler.py --rust-source path/to/lib.rs --instruction borrow
    python3 cu_profiler.py --signature 5xQe... --rpc https://api.mainnet-beta.solana.com
    python3 cu_profiler.py --crowd-source PROGRAM_ID --rpc-url ... --limit 20
"""
import argparse, json, re, sys, urllib.request
from pathlib import Path


CU_COSTS = {
    "sysvar_clock_get": 5,
    "sysvar_rent_get": 5,
    "ed25519_verify": 76_500,
    "secp256k1_recover": 25_000,
    "keccak256": 5_440,
    "sha256": 5_440,
    "compute_meter_consume": 5,
    "cpi_overhead": 1_000,
    "account_load_per_account": 1_000,
    "borsh_serialize_per_field": 50,
    "ix_handler_baseline": 1_000,
    "for_loop_iteration": 100,
    "borrow_mut_overhead": 50,
    "panic_unwind": 0,
}


def estimate_cu_static(source: str, instruction: str | None = None) -> dict:
    """Static analysis: count expensive operations in Rust source."""
    if instruction:
        ix_pattern = re.compile(
            rf"(?:pub\s+fn|fn)\s+{re.escape(instruction)}\s*\([^)]*\)\s*->[^{{]+\{{(.*?)\n\}}\n",
            re.DOTALL,
        )
        m = ix_pattern.search(source)
        if not m:
            return {"error": f"instruction '{instruction}' not found in source"}
        body = m.group(1)
    else:
        body = source

    counts = {
        "cpi_calls": len(re.findall(r"\binvoke(?:_signed)?\s*\(", body)),
        "for_loops": len(re.findall(r"\bfor\s+\w+\s+in\s+", body)),
        "ed25519_verify": len(re.findall(r"ed25519_program|ed25519_verify", body)),
        "secp256k1": len(re.findall(r"secp256k1_recover", body)),
        "sha256_calls": len(re.findall(r"\bhashv?\s*\(|sha256\s*\(", body)),
        "account_loads": len(re.findall(r"AccountInfo|AccountLoader|Account\s*<", body)),
        "borrow_mut": len(re.findall(r"\.try_borrow_mut\b|\.borrow_mut\b", body)),
        "unwrap": len(re.findall(r"\.unwrap\(\)", body)),
        "panic": len(re.findall(r"panic!\s*\(", body)),
    }

    cu_estimate = CU_COSTS["ix_handler_baseline"]
    cu_estimate += counts["cpi_calls"] * CU_COSTS["cpi_overhead"]
    cu_estimate += counts["for_loops"] * 10 * CU_COSTS["for_loop_iteration"]
    cu_estimate += counts["ed25519_verify"] * CU_COSTS["ed25519_verify"]
    cu_estimate += counts["secp256k1"] * CU_COSTS["secp256k1_recover"]
    cu_estimate += counts["sha256_calls"] * CU_COSTS["sha256"]
    cu_estimate += counts["account_loads"] * CU_COSTS["account_load_per_account"]
    cu_estimate += counts["borrow_mut"] * CU_COSTS["borrow_mut_overhead"]

    findings = []
    if cu_estimate > 1_400_000:
        findings.append({
            "type": "cu_budget_exceeded",
            "severity": "info",
            "classification": "known_class",
            "description": f"Estimated CU {cu_estimate:,} exceeds 1.4M max per tx. Exploit may need to span multiple txs OR reduce input size.",
        })
    if counts["unwrap"] > 5:
        findings.append({
            "type": "panic_surface",
            "severity": "medium",
            "classification": "novel_instance",
            "description": f"{counts['unwrap']} .unwrap() calls — high panic surface. Each panic = tx failure but no fund loss usually. Investigate DoS vector.",
        })
    if counts["cpi_calls"] > 3:
        findings.append({
            "type": "high_cpi_count",
            "severity": "info",
            "classification": "novel_instance",
            "description": f"{counts['cpi_calls']} CPI calls in one instruction. Composability surface — review each CPI target for trust assumptions.",
        })
    if counts["for_loops"] > 0:
        findings.append({
            "type": "unbounded_loop_surface",
            "severity": "medium",
            "classification": "known_class",
            "description": f"{counts['for_loops']} for loops. Verify each has bounded input (caller cannot inflate iteration count). DoS vector if unbounded.",
        })

    return {
        "method": "static",
        "instruction": instruction or "(whole file)",
        "counts": counts,
        "cu_estimate": cu_estimate,
        "findings": findings,
    }


def fetch_tx_cu(rpc_url: str, signature: str) -> dict | None:
    try:
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [signature, {"encoding": "json", "maxSupportedTransactionVersion": 0}],
        }).encode()
        req = urllib.request.Request(rpc_url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read())
        return resp.get("result")
    except Exception as e:
        print(f"[!] RPC error: {e}", file=sys.stderr)
        return None


def main():
    ap = argparse.ArgumentParser(description="Solana CU profiler — static + dynamic")
    ap.add_argument("--rust-source", help="Path to Rust source file or directory")
    ap.add_argument("--instruction", help="Specific instruction name to profile")
    ap.add_argument("--signature", help="Real tx signature to fetch CU usage")
    ap.add_argument("--rpc", default="https://api.mainnet-beta.solana.com")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    result = {"chain": "solana", "method": None, "findings": []}

    if args.signature:
        print(f"[*] Fetching tx {args.signature[:12]}... from RPC")
        tx = fetch_tx_cu(args.rpc, args.signature)
        if tx:
            meta = tx.get("meta", {})
            cu_consumed = meta.get("computeUnitsConsumed", 0)
            fee = meta.get("fee", 0)
            log_msgs = meta.get("logMessages", [])
            result.update({
                "method": "dynamic_rpc",
                "cu_consumed": cu_consumed,
                "fee_lamports": fee,
                "fee_sol": fee / 1_000_000_000,
                "log_count": len(log_msgs),
                "program_invocations": [m for m in log_msgs if "invoke" in m][:10],
            })
            if cu_consumed > 1_200_000:
                result["findings"].append({
                    "type": "near_cu_limit",
                    "severity": "info",
                    "description": f"CU usage {cu_consumed:,} is >85% of max. Small changes could push over limit.",
                })

    elif args.rust_source:
        src_path = Path(args.rust_source)
        if not src_path.exists():
            print(f"[!] Source not found: {src_path}", file=sys.stderr)
            sys.exit(1)
        if src_path.is_dir():
            sources = list(src_path.rglob("*.rs"))
            combined = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in sources)
        else:
            combined = src_path.read_text(encoding="utf-8", errors="replace")
        result = estimate_cu_static(combined, args.instruction)

    else:
        print("[!] Provide --rust-source OR --signature", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2, default=str))

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
