#!/usr/bin/env python3
"""
sbpf_disassembler.py — llvm-objdump --triple=bpf wrapper.

Solana programs are sBPF (Solana BPF) bytecode. For unverified programs:
1. Fetch program data from RPC
2. Disassemble via llvm-objdump
3. Output pseudo-asm + extracted strings/selectors

Fallback: ezbpf (simpler, faster) if available.
"""
import argparse, json, shutil, subprocess, sys
from pathlib import Path


def run_llvm_objdump(elf_path: Path) -> str | None:
    if shutil.which("llvm-objdump") is None:
        return None
    try:
        r = subprocess.run(
            ["llvm-objdump", "--triple=bpf", "-d", str(elf_path)],
            capture_output=True, text=True, timeout=120,
        )
        return r.stdout if r.returncode == 0 else None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def run_ezbpf(elf_path: Path) -> str | None:
    if shutil.which("ezbpf") is None:
        return None
    try:
        r = subprocess.run(["ezbpf", "disasm", str(elf_path)], capture_output=True, text=True, timeout=120)
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


def extract_strings(elf_path: Path) -> list[str]:
    if shutil.which("strings"):
        try:
            r = subprocess.run(["strings", "-n", "6", str(elf_path)], capture_output=True, text=True, timeout=30)
            return [s for s in r.stdout.splitlines() if s.strip()][:200]
        except Exception:
            pass
    try:
        data = elf_path.read_bytes()
    except Exception:
        return []
    strings = []
    current = []
    for b in data:
        if 32 <= b < 127:
            current.append(chr(b))
        else:
            if len(current) >= 6:
                strings.append("".join(current))
            current = []
    return strings[:200]


def main():
    ap = argparse.ArgumentParser(description="sBPF disassembler wrapper")
    ap.add_argument("--elf", required=True, help="Path to .so program file")
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    elf = Path(args.elf)
    if not elf.exists():
        print(f"[!] ELF not found: {elf}", file=sys.stderr); sys.exit(1)

    disasm = run_llvm_objdump(elf)
    tool_used = "llvm-objdump"
    if disasm is None:
        disasm = run_ezbpf(elf)
        tool_used = "ezbpf"
    if disasm is None:
        print(f"[!] Neither llvm-objdump nor ezbpf available", file=sys.stderr)
        print(f"    Install: llvm tools + ezbpf (github.com/deanmlittle/ezbpf)", file=sys.stderr)
        sys.exit(2)

    strings_out = extract_strings(elf)

    summary = {
        "elf_path": str(elf),
        "elf_size_bytes": elf.stat().st_size,
        "tool_used": tool_used,
        "disasm_lines": len(disasm.splitlines()),
        "strings_count": len(strings_out),
        "strings_sample": strings_out[:30],
    }

    if not args.quiet:
        print(f"[+] ELF: {elf} ({summary['elf_size_bytes']} bytes)")
        print(f"[+] Tool: {tool_used}")
        print(f"[+] Disasm lines: {summary['disasm_lines']}")
        print(f"[+] Strings extracted: {len(strings_out)}")

    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "disasm.txt").write_text(disasm, encoding="utf-8")
        (out / "strings.txt").write_text("\n".join(strings_out), encoding="utf-8")
        (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
