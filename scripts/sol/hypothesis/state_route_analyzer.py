#!/usr/bin/env python3
"""
state_route_analyzer.py — Detector for broader class: STATE MACHINE ALTERNATIVE ROUTES.

CLASS: state machine has flags/locks/checks that block operations,
but alternative routes (account migration, close+reinit, realloc, ownership
transfer, delegate) can bypass these checks.

Known instances of class:
  - Marginfi 2025 ($160M prevented): `ACCOUNT_IN_FLASHLOAN` flag NOT checked
    in `transfer_to_new_account` — account migration reset liability tracking
  - General: state lock check is present in `withdraw`, but NOT in the new
    `emergency_withdraw` instruction

Detection strategy:
1. Find state flag declarations (bool fields, bitflags, enum variants)
2. For each flag — find guard checks (`require!(flag == X)`, `if flag {}`)
3. For each instruction — which guard checks are applied?
4. Find alternative routes — instructions which:
   - Move account ownership / delegate
   - Close + recreate
   - Realloc (which can drop state)
   - Migrate to new struct version
5. Report routes which BYPASS guard checks for flagged states
"""
import argparse
import json
import re
import sys
from pathlib import Path


STATE_FLAG_DECL_RE = re.compile(
    r"pub\s+(\w+(?:_flag|_lock|_status|_state|_in_\w+|paused|frozen|locked))\s*:\s*(?:bool|u8|u16|u32|u64)",
    re.IGNORECASE,
)
ENUM_STATE_RE = re.compile(r"#\[(?:repr\(\w+\),?\s*)?\w*\]\s*pub\s+enum\s+(\w+(?:State|Status|Phase))\s*\{")
GUARD_CHECK_RE = re.compile(r"require!\s*\(\s*[^,)]*\.\s*(\w+)\s*(?:==|!=|\.is_)")
FN_HANDLER_RE = re.compile(r"pub\s+fn\s+(\w+)\s*\(")

ALTERNATIVE_ROUTE_PATTERNS = {
    "account_migration": re.compile(r"transfer.*account|migrate|move_to_new"),
    "close_reinit": re.compile(r"\.close\s*\([^)]*\)"),
    "realloc": re.compile(r"\.realloc\s*\("),
    "ownership_transfer": re.compile(r"transfer_ownership|set_owner|transfer_authority"),
    "delegate": re.compile(r"set_delegate|approve.*delegate"),
}


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    findings = []
    lines = text.splitlines()

    flags = set()
    for m in STATE_FLAG_DECL_RE.finditer(text):
        flags.add(m.group(1).lower())

    enums = []
    for m in ENUM_STATE_RE.finditer(text):
        enums.append(m.group(1))

    guarded_flags = set()
    for m in GUARD_CHECK_RE.finditer(text):
        guarded_flags.add(m.group(1).lower())

    handlers = []
    for m in FN_HANDLER_RE.finditer(text):
        handler_start = m.start()
        body_end = text.find("\n}", handler_start)
        if body_end < 0:
            body_end = min(handler_start + 3000, len(text))
        handlers.append({
            "name": m.group(1),
            "line": text[: handler_start].count("\n") + 1,
            "body": text[handler_start:body_end],
        })

    for h in handlers:
        routes_found = []
        for route_name, route_re in ALTERNATIVE_ROUTE_PATTERNS.items():
            if route_re.search(h["body"]):
                routes_found.append(route_name)
        if not routes_found:
            continue

        local_guards = set()
        for m in GUARD_CHECK_RE.finditer(h["body"]):
            local_guards.add(m.group(1).lower())

        missing_guards = (guarded_flags | flags) - local_guards
        if missing_guards:
            is_known = "transfer" in h["name"].lower() and "account" in h["name"].lower()
            findings.append({
                "class": "state_route_bypass",
                "subclass": "alternative_route_unchecked",
                "file": str(path),
                "line": h["line"],
                "handler": h["name"],
                "alternative_routes": routes_found,
                "missing_guards": sorted(missing_guards)[:10],
                "advice": f"Handler `{h['name']}` uses alternative routes {routes_found}, "
                          f"but does not check state flags {sorted(missing_guards)[:5]}. "
                          f"These flags are checked in other handlers — bypass possible.",
                "severity": "critical" if is_known else "high",
                "classification": "known_class" if is_known else "novel_instance",
            })

    return findings


def main():
    ap = argparse.ArgumentParser(description="Find state machine alternative route bypasses")
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

    novel = [f for f in all_findings if f["classification"] == "novel_instance"]
    if not args.quiet:
        print(f"[+] State route findings: {len(all_findings)} (novel: {len(novel)})")
        for f in all_findings[:10]:
            tag = "NOVEL" if f["classification"] == "novel_instance" else "known"
            print(f"  [{f['severity']:8}] [{tag}] {f['handler']:25} routes={f['alternative_routes']}")

    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "state_route_findings.json").write_text(json.dumps(all_findings, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
