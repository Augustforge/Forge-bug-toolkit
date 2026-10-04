#!/usr/bin/env python3
"""
spec_miner.py — Sibling of comment_miner: extracts MUST/SHALL/ALWAYS/NEVER
claims from README.md, docs/**/*.md, whitepaper.pdf (if parser available).

CLASS: SPEC-VS-CODE GAP. Whitepaper/docs declare "system guarantees X" or
"this MUST never happen" — but the contract may not enforce it. Alchemix /
Mezo / Vest case: doc says "no downside guard fallback" but code allowed it.

CLASSIFICATION:
  - [code_enforced]    = spec claim has matching code guard (low priority)
  - [code_unenforced]  = spec claim has NO matching code guard (HIGH priority)
  - [ambiguous]        = can't tell automatically — manual review needed

Usage:
  python3 spec_miner.py --repo path/to/repo --source-glob '**/*.sol' \\
    --output sessions/X/hypothesis/

Output: spec_findings.json + spec_delta.md
"""
import argparse
import json
import re
import sys
from pathlib import Path

CLAIM_PATTERNS = [
    (re.compile(r"\b(MUST(?!\s+be\s+called)|SHALL|ALWAYS|NEVER|GUARANTEED?)\b\s+([^\n.]{5,150})", re.IGNORECASE), "spec_claim"),
    (re.compile(r"\bassumes?\s+(?:that\s+)?([^\n.]{10,150})", re.IGNORECASE), "assumption"),
    (re.compile(r"\b(?:no|cannot|impossible to)\s+([^\n.]{5,150})", re.IGNORECASE), "negation_claim"),
    (re.compile(r"\binvariant[:\s]+([^\n.]{5,150})", re.IGNORECASE), "explicit_invariant"),
]

SKIP_DIRS = {".git", "node_modules", "target", "out", "build", "cache", "dist"}


def find_doc_files(repo: Path) -> list[Path]:
    out = []
    for name in ["README.md", "README", "WHITEPAPER.md", "SPEC.md", "ARCHITECTURE.md"]:
        p = repo / name
        if p.exists():
            out.append(p)
    for d in ["docs", "doc", "whitepaper", "spec"]:
        dp = repo / d
        if dp.is_dir():
            for f in dp.rglob("*.md"):
                if any(s in f.parts for s in SKIP_DIRS):
                    continue
                out.append(f)
    return out


def extract_claims(doc: Path) -> list[dict]:
    out = []
    try:
        text = doc.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return out
    lines = text.splitlines()
    for i, line in enumerate(lines, 1):
        for regex, kind in CLAIM_PATTERNS:
            m = regex.search(line)
            if m:
                claim_text = (m.group(1) if kind == "assumption" else (m.group(0) if kind != "explicit_invariant" else m.group(1))).strip()
                out.append({
                    "doc": str(doc),
                    "line": i,
                    "kind": kind,
                    "claim": claim_text[:200],
                    "context": line.strip()[:300],
                })
    return out


def keywords_from_claim(claim: str) -> list[str]:
    """Crude keyword extractor — used to guess what code should enforce the claim."""
    words = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]{3,}\b", claim)
    stop = {"that", "this", "with", "from", "into", "when", "then", "value", "must", "shall", "always", "never", "no", "be"}
    return [w.lower() for w in words if w.lower() not in stop][:5]


def find_enforcement(source_files: list[Path], keywords: list[str]) -> list[str]:
    """Return file:line refs where keywords appear together near guard tokens."""
    hits = []
    if not keywords:
        return hits
    guard_tokens = ["require", "assert", "revert", "if (", "if(", "ensure", "check"]
    for f in source_files:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            ll = line.lower()
            if any(g in ll for g in guard_tokens) and any(k in ll for k in keywords):
                hits.append(f"{f.name}:{i}")
                if len(hits) >= 5:
                    return hits
    return hits


def classify(claim: dict, source_files: list[Path]) -> dict:
    kws = keywords_from_claim(claim["claim"])
    hits = find_enforcement(source_files, kws)
    if hits:
        claim["status"] = "code_enforced"
        claim["enforcement_hits"] = hits
        claim["priority"] = "low"
    elif len(kws) < 2:
        claim["status"] = "ambiguous"
        claim["priority"] = "medium"
    else:
        claim["status"] = "code_unenforced"
        claim["priority"] = "high"
        claim["enforcement_hits"] = []
    claim["keywords"] = kws
    return claim


def render_md(claims: list[dict], repo: Path) -> str:
    lines = []
    lines.append(f"# Spec Delta — {repo.name}")
    lines.append("")
    lines.append(f"Total spec claims extracted: **{len(claims)}**")
    high = [c for c in claims if c.get("priority") == "high"]
    med = [c for c in claims if c.get("priority") == "medium"]
    low = [c for c in claims if c.get("priority") == "low"]
    lines.append(f"- HIGH (code_unenforced): {len(high)}")
    lines.append(f"- MEDIUM (ambiguous): {len(med)}")
    lines.append(f"- LOW (code_enforced): {len(low)}")
    lines.append("")
    lines.append("> HIGH = whitepaper/docs claim with no matching code guard. **Audit these first.**")
    lines.append("")

    for label, group in [("HIGH — code_unenforced", high), ("MEDIUM — ambiguous", med)]:
        if not group:
            continue
        lines.append(f"## {label}")
        lines.append("")
        for c in group:
            lines.append(f"### {c['kind']}: \"{c['claim']}\"")
            lines.append(f"- **Source**: `{Path(c['doc']).name}:{c['line']}`")
            lines.append(f"- **Context**: {c['context']}")
            lines.append(f"- **Keywords**: {', '.join(c.get('keywords', []))}")
            if c.get("enforcement_hits"):
                lines.append(f"- **Possible enforcement**: {', '.join(c['enforcement_hits'])}")
            else:
                lines.append(f"- **No matching code guard found** — verify manually")
            lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="Path to protocol repo")
    ap.add_argument("--source-glob", default="**/*.sol", help="Glob for source files (default '**/*.sol' — use '**/*.rs' for Rust)")
    ap.add_argument("--output", required=True, help="Output directory")
    args = ap.parse_args()

    repo = Path(args.repo)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    docs = find_doc_files(repo)
    if not docs:
        print("[warn] no doc files found (README.md / docs/ / SPEC.md / WHITEPAPER.md)", file=sys.stderr)
        (out_dir / "spec_findings.json").write_text("[]", encoding="utf-8")
        (out_dir / "spec_delta.md").write_text("# Spec Delta\n\nNo doc files found.\n", encoding="utf-8")
        return

    source_files = []
    for p in repo.rglob(args.source_glob.split("/")[-1]):
        try:
            rel_parts = p.relative_to(repo).parts
        except ValueError:
            rel_parts = p.parts
        if not any(s in rel_parts for s in SKIP_DIRS):
            source_files.append(p)
    print(f"[info] {len(docs)} doc files, {len(source_files)} source files")

    claims = []
    for d in docs:
        for c in extract_claims(d):
            claims.append(classify(c, source_files))

    (out_dir / "spec_findings.json").write_text(json.dumps(claims, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "spec_delta.md").write_text(render_md(claims, repo), encoding="utf-8")
    print(f"[ok] {len(claims)} claims → {out_dir / 'spec_delta.md'}")


if __name__ == "__main__":
    main()
