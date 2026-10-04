#!/usr/bin/env python3
"""
Variant analysis — found bug X on target A -> automatically check
all other session targets for a similar pattern.

Idea: the same vulnerable library / framework / pattern often
appears across several targets. If we submit one as a finding —
the others may be affected too.

Usage:
    python3 variant_analysis.py --finding-id F003 --session sessions/example.com
"""

import argparse
import json
import sys
from pathlib import Path


def load_finding(session: Path, fid: str) -> dict:
    for fname in ["scan_summary.json", "web3_summary.json"]:
        f = session / fname
        if not f.exists():
            continue
        try:
            data = json.loads(f.read_text())
            for finding in data.get("findings", []):
                if finding.get("id") == fid:
                    return finding
        except Exception:
            pass
    return {}


def signature(finding: dict) -> dict:
    """Extract the signature: vuln type + pattern markers."""
    return {
        "vulnerability": finding.get("vulnerability"),
        "swc_id": finding.get("swc_id"),
        "tools": tuple(sorted(finding.get("tools_flagged", []))),
        "function_name": finding.get("function", ""),
        "description_keywords": _extract_keywords(finding.get("description", "")),
    }


def _extract_keywords(desc: str) -> set:
    if not desc:
        return set()
    common_words = {"the", "this", "that", "and", "or", "in", "of", "to",
                     "is", "are", "was", "were", "be", "have", "has",
                     "function", "contract", "code", "value"}
    words = {w.strip(".,();[]{}").lower() for w in desc.split() if len(w) >= 4}
    return words - common_words


def signature_similarity(s1: dict, s2: dict) -> float:
    """0.0-1.0 similarity score."""
    score = 0.0
    if s1["vulnerability"] == s2["vulnerability"]:
        score += 0.5
    if s1["swc_id"] and s1["swc_id"] == s2["swc_id"]:
        score += 0.3
    if s1["tools"] == s2["tools"]:
        score += 0.1
    if s1["description_keywords"] and s2["description_keywords"]:
        intersection = len(s1["description_keywords"] & s2["description_keywords"])
        union = len(s1["description_keywords"] | s2["description_keywords"])
        if union > 0:
            score += 0.1 * (intersection / union)
    return min(score, 1.0)


def scan_all_sessions(sessions_dir: Path, source_signature: dict,
                      source_session: Path, threshold: float) -> list[dict]:
    matches = []
    for session in sessions_dir.iterdir():
        if not session.is_dir() or session.name.startswith("_"):
            continue
        if session.resolve() == source_session.resolve():
            continue

        for fname in ["scan_summary.json", "web3_summary.json"]:
            f = session / fname
            if not f.exists():
                continue
            try:
                data = json.loads(f.read_text())
                for finding in data.get("findings", []):
                    sig = signature(finding)
                    sim = signature_similarity(source_signature, sig)
                    if sim >= threshold:
                        matches.append({
                            "session": session.name,
                            "finding_id": finding.get("id"),
                            "vulnerability": finding.get("vulnerability"),
                            "severity": finding.get("severity"),
                            "similarity": round(sim, 3),
                            "file": finding.get("file"),
                        })
            except Exception:
                continue
    return sorted(matches, key=lambda x: x["similarity"], reverse=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--finding-id", required=True)
    ap.add_argument("--session", required=True)
    ap.add_argument("--sessions-dir", default="sessions/")
    ap.add_argument("--threshold", type=float, default=0.6)
    ap.add_argument("--output")
    args = ap.parse_args()

    session = Path(args.session)
    finding = load_finding(session, args.finding_id)
    if not finding:
        sys.exit(f"Finding {args.finding_id} not found in {session}")

    src_sig = signature(finding)
    print(f"[*] Source: {finding.get('vulnerability')} ({finding.get('severity')})")
    print(f"[*] Scanning sessions/ for similar patterns (threshold={args.threshold})")

    matches = scan_all_sessions(Path(args.sessions_dir), src_sig, session, args.threshold)

    result = {
        "source": {
            "session": str(session),
            "finding_id": args.finding_id,
            "vulnerability": finding.get("vulnerability"),
        },
        "variants_found": len(matches),
        "variants": matches,
    }

    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False))
        print(f"[+] Saved: {args.output}")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))

    print(f"\n[+] {len(matches)} potential variants in other sessions")
    for m in matches[:10]:
        print(f"  {m['session']}/{m['finding_id']}: {m['vulnerability']} "
              f"(sim {m['similarity']})")


if __name__ == "__main__":
    main()
