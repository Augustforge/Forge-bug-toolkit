#!/usr/bin/env python3
"""
selector_enum_sol.py — extract instruction discriminators from sBPF program.

Anchor programs use 8-byte sha256("global:<fn_name>")[..8] as instruction selector.
Other programs may use 1-byte or custom enum tags.

Strategy: scan ELF for 8-byte patterns in .rodata + cross-reference common
Anchor instruction names → identify likely selectors.
"""
import argparse, hashlib, json, re, sys
from pathlib import Path

COMMON_ANCHOR_INSTRUCTIONS = [
    "initialize", "deposit", "withdraw", "transfer", "mint", "burn",
    "swap", "stake", "unstake", "claim", "liquidate", "borrow", "repay",
    "create", "close", "update", "set_authority", "approve", "revoke",
    "open_position", "close_position", "increase_liquidity", "decrease_liquidity",
    "open_account", "close_account", "settle", "cancel", "place_order",
    "flash_loan", "transfer_authority", "freeze", "thaw", "execute",
    "propose", "vote", "queue", "cancel_proposal",
]


def anchor_discriminator(fn_name: str) -> bytes:
    """Compute Anchor instruction discriminator."""
    return hashlib.sha256(f"global:{fn_name}".encode()).digest()[:8]


def extract_8byte_patterns(elf_path: Path) -> list[tuple[bytes, int]]:
    """Find all 8-byte patterns that look like Anchor discriminators."""
    try:
        data = elf_path.read_bytes()
    except Exception:
        return []
    matches = []
    for i in range(0, len(data) - 8, 1):
        chunk = data[i:i+8]
        if 0 < sum(chunk) < 8 * 255:
            matches.append((chunk, i))
    return matches


def main():
    ap = argparse.ArgumentParser(description="Enumerate Solana program selectors")
    ap.add_argument("--elf", required=True, help="Path to .so")
    ap.add_argument("--output", default=None)
    ap.add_argument("--guess-instructions", action="store_true", help="Cross-reference common Anchor names")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    elf = Path(args.elf)
    if not elf.exists():
        print(f"[!] {elf}", file=sys.stderr); sys.exit(1)

    candidates = extract_8byte_patterns(elf)
    if not args.quiet:
        print(f"[+] Found {len(candidates)} 8-byte patterns")

    matches = []
    if args.guess_instructions:
        try:
            data = elf.read_bytes()
        except Exception:
            data = b""
        for name in COMMON_ANCHOR_INSTRUCTIONS:
            disc = anchor_discriminator(name)
            if disc in data:
                offset = data.find(disc)
                matches.append({
                    "instruction_name": name,
                    "discriminator_hex": disc.hex(),
                    "offset": offset,
                })
                if not args.quiet:
                    print(f"  [match]   {name:30} {disc.hex()} @ {offset}")

    summary = {
        "elf": str(elf),
        "elf_size": elf.stat().st_size,
        "total_8byte_patterns": len(candidates),
        "guessed_instructions": matches,
    }

    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "selectors.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
