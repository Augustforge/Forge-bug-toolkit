#!/usr/bin/env python3
"""
ed25519_offset_validator.py — Solana Ed25519 signature-instruction offset bypass detector.

CLASS (asymmetric.re "Wrong Offset", Relay Protocol, Critical double-spend):
The Solana Ed25519 native program verifies signatures whose public key / signature /
message live at CONFIGURABLE byte offsets, described by an `Ed25519SignatureOffsets`
struct (public_key_offset, signature_offset, message_data_offset, ...). A consumer that
introspects the sig instruction and reads the pubkey at a HARDCODED offset (e.g.
`data[16..48]`) — instead of at the offset the struct actually declares — can be tricked:
attacker puts the trusted key at the hardcoded offset (where the consumer looks) but sets
`public_key_offset` to a DIFFERENT offset holding their own key, signs with their own key,
the Ed25519 program verifies fine, and the consumer believes the trusted key signed.

DETECTION SIGNAL:
  - File deals with the Ed25519 program / sig-instruction introspection:
    `ed25519_program`, `Ed25519SignatureOffsets`, `load_instruction_at`, instructions sysvar.
  - Reads instruction data at a HARDCODED slice (`data[16..48]`, `&data[N..N+32]`, fixed index).
  - Does NOT validate `public_key_offset` (and friends) against the offset it reads from.

This is a heuristic triage aid (false positives expected). Every flag → manual check:
"does the code bind the pubkey it trusts to the offset Ed25519SignatureOffsets declares?"

Contract: --target <dir|.rs> --output <dir> [--quiet]  (auto-run by sol/scan.sh glob)
"""
import argparse
import json
import re
import sys
from pathlib import Path

ED25519_CONTEXT = [
    re.compile(r"ed25519_program"),
    re.compile(r"Ed25519SignatureOffsets|Ed25519.*[Oo]ffset"),
    re.compile(r"load_instruction_at|sysvar::instructions|get_instruction_relative"),
    re.compile(r"new_ed25519_instruction|ed25519_instruction"),
]
# Hardcoded slice / fixed-index read of instruction data (the smell).
HARDCODED_SLICE = re.compile(r"\.data\s*\[\s*\d+\s*\.\.|&\s*\w+\s*\[\s*\d+\s*\.\.\s*\d+\s*\]|data\s*\[\s*\d+\s*\]")
# Evidence the code DOES use the declared offsets (mitigation).
USES_DECLARED_OFFSET = re.compile(
    r"public_key_offset|signature_offset|message_data_offset|message_instruction_index|\.offsets\b"
)


def has_ed25519_context(text: str) -> bool:
    return sum(bool(p.search(text)) for p in ED25519_CONTEXT) >= 1


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    if not has_ed25519_context(text):
        return []

    findings = []
    uses_declared = bool(USES_DECLARED_OFFSET.search(text))
    for m in HARDCODED_SLICE.finditer(text):
        line = text[: m.start()].count("\n") + 1
        # higher risk when the code never references the declared offset fields at all
        severity = "high" if not uses_declared else "medium"
        findings.append({
            "class": "ed25519_offset_bypass",
            "subclass": "hardcoded_sig_instruction_offset",
            "file": str(path),
            "line": line,
            "snippet": text[m.start(): m.start() + 60].replace("\n", " ").strip(),
            "advice": "Sig-instruction data read at a hardcoded offset in Ed25519 context. Verify the trusted "
                      "pubkey is bound to the offset `Ed25519SignatureOffsets.public_key_offset` declares — "
                      "otherwise attacker puts the trusted key at the read offset but signs with a different key "
                      "pointed to by public_key_offset (asymmetric.re Relay double-spend).",
            "severity": severity,
            "classification": "novel_instance",
            "broader_class": "signature_offset_trust",
            "uses_declared_offset": uses_declared,
        })
    return findings


def main():
    ap = argparse.ArgumentParser(description="Solana Ed25519 signature offset bypass detector")
    ap.add_argument("--target", required=True)
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"[!] target not found: {target}", file=sys.stderr)
        sys.exit(1)

    files = list(target.rglob("*.rs")) if target.is_dir() else ([target] if target.suffix == ".rs" else [])
    all_findings = []
    for f in files:
        fp = str(f).replace("\\", "/")
        if "/target/" in fp or "/tests/" in fp:
            continue
        all_findings.extend(scan_file(f))

    if not args.quiet:
        print(f"[+] Ed25519 offset scan: {len(files)} files, {len(all_findings)} flags")
        for x in all_findings[:15]:
            print(f"  [{x['severity']:6}] {Path(x['file']).name}:{x['line']}  {x['snippet']}")

    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "ed25519_offset_findings.json").write_text(json.dumps(all_findings, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
