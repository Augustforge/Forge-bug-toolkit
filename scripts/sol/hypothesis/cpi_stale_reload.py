#!/usr/bin/env python3
"""
cpi_stale_reload.py — Solana CPI "missing reload" (stale deserialized struct) detector.

CLASS (asymmetric.re "Invocation Security", CPI-2; affinity to taxonomy Cat 2.4 cache-invalidation):
Anchor loads & deserializes an account's data into an in-memory struct at the start of an
instruction. After a CPI that MUTATES that account (e.g. a token transfer changing a balance),
the on-chain data changes but the already-deserialized struct in memory does NOT — only the raw
`AccountInfo` (lamports/owner) is auto-refreshed. Reading `ctx.accounts.X.field` after the CPI,
without calling `X.reload()`, acts on STALE data → wrong accounting (e.g. credit based on
pre-transfer balance).

DETECTION SIGNAL (heuristic, per-function):
  - A CPI is invoked: `invoke(`, `invoke_signed(`, `::cpi::`, `CpiContext`, `token::transfer`, etc.
  - After it, a deserialized field of an account is read: `ctx.accounts.X.<field>` / `X.<field>`.
  - The function never calls `.reload()`.
→ candidate stale-read. Every flag → manual check: "is the field read after the CPI, and was the
   account mutated by that CPI, without a reload()?"

Heuristic / triage aid — false positives expected (not every post-CPI field read is stale).

Contract: --target <dir|.rs> --output <dir> [--quiet]  (auto-run by sol/scan.sh glob)
"""
import argparse
import json
import re
import sys
from pathlib import Path

ANCHOR_MARKER = re.compile(r"use\s+anchor_lang|#\[derive\(Accounts\)\]|ctx\.accounts")
FN_RE = re.compile(r"pub\s+fn\s+(\w+)\s*\(")
CPI_RE = re.compile(
    r"\binvoke(?:_signed)?\s*\(|::cpi::|CpiContext::|token::(?:transfer|mint_to|burn)\s*\(|"
    r"transfer_checked\s*\(|associated_token|solana_program::program::invoke"
)
RELOAD_RE = re.compile(r"\.reload\s*\(\s*\)")
# read of a deserialized field on an anchor account (heuristic): ctx.accounts.X.field or X.amount/.balance
FIELD_READ_RE = re.compile(
    r"ctx\.accounts\.(\w+)\.(\w+)|(\b\w+)\.(amount|balance|owner_data|state|total|shares|reserves)\b"
)


def split_functions(text: str):
    """Yield (name, start_line, body) per `pub fn`."""
    fns = []
    matches = list(FN_RE.finditer(text))
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        line = text[:start].count("\n") + 1
        fns.append((m.group(1), line, body))
    return fns


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    if not ANCHOR_MARKER.search(text):
        return []

    findings = []
    for name, line, body in split_functions(text):
        cpi = CPI_RE.search(body)
        if not cpi:
            continue
        if RELOAD_RE.search(body):
            continue  # function reloads somewhere — assume handled
        # is there a deserialized-field read AFTER the CPI?
        after = body[cpi.end():]
        fr = FIELD_READ_RE.search(after)
        if not fr:
            continue
        acct = fr.group(1) or fr.group(3) or "?"
        field = fr.group(2) or fr.group(4) or "?"
        findings.append({
            "class": "cpi_stale_reload",
            "subclass": "field_read_after_cpi_no_reload",
            "file": str(path),
            "line": line + body[:cpi.end()].count("\n"),
            "handler": name,
            "account": acct,
            "field": field,
            "advice": f"In `{name}`: a CPI is invoked, then `{acct}.{field}` (deserialized) is read with no "
                      f"`{acct}.reload()`. If the CPI mutated `{acct}`, the read sees STALE pre-CPI data "
                      f"(asymmetric.re CPI-2). Add `{acct}.reload()?` after the CPI before reading.",
            "severity": "high",
            "classification": "novel_instance",
            "broader_class": "stale_deserialized_struct",
        })
    return findings


def main():
    ap = argparse.ArgumentParser(description="Solana CPI missing-reload (stale struct) detector")
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
        print(f"[+] CPI stale-reload scan: {len(files)} files, {len(all_findings)} flags")
        for x in all_findings[:15]:
            print(f"  [{x['severity']:6}] {x['handler']:24} {x['account']}.{x['field']} @ {Path(x['file']).name}:{x['line']}")

    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "cpi_stale_reload_findings.json").write_text(json.dumps(all_findings, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
