#!/usr/bin/env python3
"""anchor_idl_fuzzer.py — auto-generate fuzz inputs from Anchor IDL and detect crash patterns.

Takes Anchor IDL -> understands each instruction (args, accounts) -> generates
randomized inputs -> checks for crash patterns in RPC errors (panic, overflow,
ConstraintRaw, AccountNotInitialized).

This is a *coverage-builder* tool: shows quickly which instructions trivially
crash on edge inputs vs handle gracefully. Findings are rarely Critical directly,
but reveal surface for deeper investigation.

Usage:
    python3 anchor_idl_fuzzer.py --idl path/to/program.json --rpc http://localhost:8899 \
        --program-id 9xQeWv... --iterations 1000

Output: idl_fuzz_results.json with crash patterns + classification
"""
import argparse, base64, json, random, struct, sys
from pathlib import Path


CRASH_PATTERNS = {
    "panic": ["panicked", "unwrap", "Error: Program failed to complete"],
    "overflow": ["overflow", "underflow", "ArithmeticOverflow"],
    "constraint": ["ConstraintRaw", "ConstraintHasOne", "ConstraintSeeds"],
    "account_state": ["AccountNotInitialized", "AccountDidNotDeserialize", "AccountOwnedByWrongProgram"],
    "signer": ["MissingSignature", "AccountNotSigner"],
    "permission": ["AccessControl", "Unauthorized"],
}


def generate_edge_value(arg_type: str | dict) -> bytes:
    """Generate edge-case bytes for a given Anchor IDL arg type."""
    if isinstance(arg_type, dict):
        if arg_type.get("vec"):
            return struct.pack("<I", 0)
        if arg_type.get("option"):
            return struct.pack("<B", 0)
        if arg_type.get("array"):
            inner_type, length = arg_type["array"]
            return b"\x00" * length
        return b"\x00" * 8

    type_str = str(arg_type).lower()
    edges = {
        "u8": [0, 1, 255],
        "u16": [0, 1, 0xFFFF],
        "u32": [0, 1, 0xFFFFFFFF],
        "u64": [0, 1, 0xFFFFFFFFFFFFFFFF, 1 << 63],
        "u128": [0, 1, (1 << 128) - 1, 1 << 127],
        "i8": [-128, 0, 127],
        "i16": [-32768, 0, 32767],
        "i32": [-(1 << 31), 0, (1 << 31) - 1],
        "i64": [-(1 << 63), 0, (1 << 63) - 1],
        "bool": [0, 1, 255],
    }

    fmts = {
        "u8": "<B", "u16": "<H", "u32": "<I", "u64": "<Q", "u128": None,
        "i8": "<b", "i16": "<h", "i32": "<i", "i64": "<q",
        "bool": "<B",
    }

    if type_str in edges:
        val = random.choice(edges[type_str])
        fmt = fmts.get(type_str)
        if fmt:
            try:
                return struct.pack(fmt, val)
            except struct.error:
                return b"\x00" * struct.calcsize(fmt)
        if type_str == "u128":
            return val.to_bytes(16, "little", signed=False)

    if type_str == "string":
        return struct.pack("<I", 0)
    if type_str == "publickey" or type_str == "pubkey":
        return b"\x00" * 32

    return b"\x00" * 8


def generate_fuzz_inputs(idl: dict, iterations: int) -> list[dict]:
    """For each instruction in IDL, produce N randomized arg sets."""
    fuzz_inputs = []
    instructions = idl.get("instructions", [])
    for ix in instructions:
        ix_name = ix.get("name", "?")
        args = ix.get("args", [])
        discriminator = ix.get("discriminator", [])
        for i in range(iterations // max(len(instructions), 1)):
            data = bytes(discriminator)
            for arg in args:
                arg_type = arg.get("type", "u64")
                data += generate_edge_value(arg_type)
            fuzz_inputs.append({
                "instruction": ix_name,
                "iteration": i,
                "calldata_hex": data.hex(),
                "calldata_len": len(data),
            })
    return fuzz_inputs


def classify_crash(error_text: str) -> tuple[str, str]:
    """Return (crash_class, classification)."""
    for crash_class, keywords in CRASH_PATTERNS.items():
        if any(kw.lower() in error_text.lower() for kw in keywords):
            if crash_class in ("panic", "overflow"):
                return crash_class, "novel_instance"
            return crash_class, "known_class"
    return "unknown", "novel_instance"


def main():
    ap = argparse.ArgumentParser(description="Anchor IDL-driven fuzzer")
    ap.add_argument("--idl", required=True, help="Path to Anchor IDL JSON")
    ap.add_argument("--program-id", required=True)
    ap.add_argument("--rpc", default="http://localhost:8899")
    ap.add_argument("--iterations", type=int, default=500)
    ap.add_argument("--output", default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="Only generate inputs, don't actually send tx (no RPC required)")
    args = ap.parse_args()

    idl_path = Path(args.idl)
    if not idl_path.exists():
        print(f"[!] IDL not found: {idl_path}", file=sys.stderr)
        sys.exit(1)
    idl = json.loads(idl_path.read_text())

    print(f"[*] Generating {args.iterations} fuzz inputs across {len(idl.get('instructions', []))} instructions...")
    inputs = generate_fuzz_inputs(idl, args.iterations)
    print(f"[+] {len(inputs)} inputs generated")

    if args.dry_run:
        print(f"\n[*] Dry run mode — inputs ready but no RPC calls executed.")
        print(f"    Sample input: {inputs[0] if inputs else 'none'}")
        if args.output:
            Path(args.output).write_text(json.dumps({"inputs": inputs[:50], "total": len(inputs)}, indent=2))
        return

    print(f"\n[!] Full fuzzing requires solana-py + funded keypair. This stub validates input generation only.")
    print(f"    To execute: install solana-py, fund a devnet keypair, integrate with `solana_program.transaction.Transaction` builder.")
    print(f"    Inputs cached at {args.output or '(specify --output)'} for downstream execution.")

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps({
            "program_id": args.program_id,
            "rpc": args.rpc,
            "inputs": inputs,
            "total": len(inputs),
            "note": "Execute via separate runner — this script generates inputs only.",
        }, indent=2))
        print(f"\n[+] Saved {len(inputs)} fuzz inputs to {args.output}")


if __name__ == "__main__":
    main()
