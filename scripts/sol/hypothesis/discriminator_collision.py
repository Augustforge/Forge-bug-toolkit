#!/usr/bin/env python3
"""
discriminator_collision.py — 8-byte discriminator overlap across programs/types.

CLASS: hardcoded discriminators can collide → wrong type accepted.
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

DISC_RE = re.compile(r"discriminator\s*[:=]\s*\[\s*((?:\d+\s*,?\s*){8})\]")


def scan_file(path: Path) -> list[tuple[str, int, str]]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    out = []
    for m in DISC_RE.finditer(text):
        disc = tuple(int(x.strip()) for x in m.group(1).rstrip(",").split(",")[:8])
        line_no = text[: m.start()].count("\n") + 1
        out.append((str(path), line_no, str(disc)))
    return out


def main():
    ap = argparse.ArgumentParser(description="Detect discriminator collisions")
    ap.add_argument("--target", required=True)
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    target = Path(args.target)
    files = [target] if target.is_file() and target.suffix == ".rs" else list(target.rglob("*.rs")) if target.is_dir() else []
    if not files: print(f"[!] No .rs files", file=sys.stderr); sys.exit(1)

    by_disc = defaultdict(list)
    for f in files:
        if "/target/" in str(f).replace("\\", "/"): continue
        for fp, ln, d in scan_file(f):
            by_disc[d].append((fp, ln))

    findings = []
    for disc, locations in by_disc.items():
        if len(locations) > 1:
            for fp, ln in locations:
                findings.append({
                    "class": "discriminator_collision",
                    "file": fp, "line": ln, "discriminator": disc,
                    "colliding_with": [{"file": f, "line": l} for f, l in locations if (f, l) != (fp, ln)],
                    "advice": f"Discriminator {disc} appears at {len(locations)} locations → type confusion possible.",
                    "severity": "high", "classification": "known_class",
                })

    if not args.quiet: print(f"[+] Discriminator collisions: {len(findings)}")
    if args.output:
        out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
        (out / "discriminator_findings.json").write_text(json.dumps(findings, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
