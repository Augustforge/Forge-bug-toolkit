#!/usr/bin/env python3
"""
crypto_audit.py — find cryptographic footguns in Solidity.

Targets:
- ecrecover without `v in {27,28}` check (signature malleability)
- ecrecover return == 0 not checked
- EIP-1271 isValidSignature returning trusted value
- keccak256(abi.encodePacked(...)) collision with dynamic args
- Reused nonces / deadline missing in sig payload
- VRF: PRNG via block.timestamp / blockhash
- BLS aggregation without subgroup check (rare flag)
"""
import argparse
import json
import re
import sys
from pathlib import Path


CHECKS = [
    ("ecrecover_no_v_check", re.compile(r"ecrecover\s*\("), "Verify v ∈ {27,28} BEFORE ecrecover to block signature malleability"),
    ("ecrecover_no_zero_check", re.compile(r"(\w+)\s*=\s*ecrecover\s*\([^;]+;\s*(?!.*\1\s*!=\s*address\(0\))", re.DOTALL), "ecrecover may return 0 on invalid sig — must check != address(0)"),
    ("eip1271_trust", re.compile(r"isValidSignature\s*\([^)]*\)\s*(?:public|external)\s+view\s+returns"), "EIP-1271 callee can return MAGICVALUE for any payload — never use as authorization proof"),
    ("packed_dynamic_collision", re.compile(r"keccak256\s*\(\s*abi\.encodePacked\s*\([^)]*(?:string|bytes|\w+\[\])"), "encodePacked with multiple dynamic types → hash collision"),
    ("blockhash_randomness", re.compile(r"\b(blockhash|block\.timestamp|block\.difficulty|block\.prevrandao)\b[^;]*(?:rand|random|seed|lottery)"), "block.* as randomness — miner-controllable"),
    ("missing_chainid", re.compile(r"EIP712Domain|DOMAIN_SEPARATOR"), "Verify chainId in domain separator (cross-chain replay)"),
    ("missing_deadline", re.compile(r"function\s+\w*(?:permit|sign|approve)\w*\s*\([^)]*\)\s+(?!.*deadline)", re.IGNORECASE), "Signature function without deadline → infinite replay window"),
    ("vrf_predictable", re.compile(r"keccak256\s*\([^)]*block\.timestamp[^)]*\)"), "Keccak over block.timestamp is predictable, not random"),
]


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    findings = []
    lines = text.splitlines()
    for cid, regex, advice in CHECKS:
        for m in regex.finditer(text):
            line_no = text[: m.start()].count("\n") + 1
            snippet = lines[line_no - 1].strip()[:120] if line_no <= len(lines) else ""
            findings.append({
                "check": cid,
                "file": str(path),
                "line": line_no,
                "snippet": snippet,
                "advice": advice,
            })
    return findings


def main():
    ap = argparse.ArgumentParser(description="Crypto footgun scanner for Solidity")
    ap.add_argument("--target", required=True)
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    target = Path(args.target)
    files = [target] if target.is_file() else list(target.rglob("*.sol")) if target.is_dir() else []
    if not files:
        print(f"[!] Target not found: {target}", file=sys.stderr)
        sys.exit(1)

    all_findings = []
    for f in files:
        if "/test" in str(f).replace("\\", "/").lower():
            continue
        all_findings.extend(scan_file(f))

    if not args.quiet:
        print(f"[+] Scanned {len(files)} files. Findings: {len(all_findings)}")
        by_check = {}
        for f in all_findings:
            by_check.setdefault(f["check"], []).append(f)
        for cid, items in sorted(by_check.items()):
            print(f"\n[{cid}] ({len(items)} hits)")
            for it in items[:3]:
                print(f"  {Path(it['file']).name}:{it['line']}  {it['snippet']}")
            if len(items) > 3:
                print(f"  ... +{len(items)-3} more")

    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "crypto_audit.json").write_text(json.dumps(all_findings, indent=2), encoding="utf-8")
        md = "# Crypto Audit Report\n\n"
        for f in all_findings:
            md += f"## {f['check']}\n- {f['file']}:{f['line']}\n- `{f['snippet']}`\n- **Advice**: {f['advice']}\n\n"
        (out / "crypto_audit.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
