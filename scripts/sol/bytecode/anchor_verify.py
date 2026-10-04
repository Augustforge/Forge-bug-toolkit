#!/usr/bin/env python3
"""
anchor_verify.py — standalone bytecode-source verification.

Difference from detectors/anchor_verify_wrapper.py:
- This is called bytecode-only path (no source)
- Compares on-chain program data hash vs published source build hash
- Output: match | mismatch | unknown
"""
import argparse, hashlib, json, shutil, subprocess, sys
from pathlib import Path


def fetch_program_data(rpc_url: str, program_id: str) -> bytes | None:
    if shutil.which("solana") is None:
        return None
    try:
        r = subprocess.run(
            ["solana", "program", "dump", program_id, "/tmp/program_dump.so", "--url", rpc_url],
            capture_output=True, timeout=60,
        )
        if r.returncode == 0:
            return Path("/tmp/program_dump.so").read_bytes()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def build_source(source_dir: Path) -> bytes | None:
    if shutil.which("anchor") is None and shutil.which("cargo") is None:
        return None
    try:
        if (source_dir / "Anchor.toml").exists():
            subprocess.run(["anchor", "build"], cwd=source_dir, timeout=600, capture_output=True)
            for so in source_dir.rglob("*.so"):
                if "target" in str(so):
                    return so.read_bytes()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def main():
    ap = argparse.ArgumentParser(description="Bytecode <-> source hash verification")
    ap.add_argument("--program-id", required=True)
    ap.add_argument("--source", help="Path to source dir (Anchor project)")
    ap.add_argument("--rpc", default="https://api.mainnet-beta.solana.com")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    on_chain = fetch_program_data(args.rpc, args.program_id)
    if on_chain is None:
        print(f"[!] Could not fetch on-chain program (need solana CLI)", file=sys.stderr)
        sys.exit(2)
    on_chain_hash = hashlib.sha256(on_chain).hexdigest()

    result = {
        "program_id": args.program_id,
        "on_chain_size": len(on_chain),
        "on_chain_sha256": on_chain_hash,
        "source_built": False,
        "source_sha256": None,
        "match": None,
    }

    if args.source:
        built = build_source(Path(args.source))
        if built:
            result["source_built"] = True
            result["source_size"] = len(built)
            result["source_sha256"] = hashlib.sha256(built).hexdigest()
            result["match"] = result["on_chain_sha256"] == result["source_sha256"]

    print(f"[+] Program: {args.program_id}")
    print(f"[+] On-chain SHA256: {on_chain_hash}")
    if result["source_built"]:
        print(f"[+] Source SHA256:   {result['source_sha256']}")
        print(f"[+] Match:           {result['match']}")
    else:
        print(f"[!] Source not built (provide --source with Anchor project)")

    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "verify_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
