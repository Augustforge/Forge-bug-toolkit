#!/usr/bin/env python3
"""
audit_trail_miner.py — Git log mining for "fix/guard/protection" commits vs actual code changes.

The Alchemix pattern: a commit `16e0882` claimed "Direct WETH-to-wstETH allocation marks down
vault shares" but the resolution was documented as runbook only — no actual code fix in the
listed strategy. Mining commit messages vs diffs surfaces these gaps.

Signals:
  - Commit message says "fix" / "guard" / "protect" / "patch" / "resolved" / "audit"
  - But diff is empty / only adds comments / only touches docs / only renames

Usage:
  python3 audit_trail_miner.py --repo path/to/repo --output sessions/X/hypothesis/
  python3 audit_trail_miner.py --repo path/to/repo --since 2024-01-01

Output: audit_trail.json + audit_trail_findings.md
"""

import argparse
import json
import re
import subprocess
from pathlib import Path

FIX_KEYWORDS = re.compile(
    r"\b(fix|guard|protect|protection|patch|patched|resolved|"
    r"audit|vulnerab|security|critical|severe|high-?severity|"
    r"missing|miss[ -]?off|forgot|oversight|"
    r"cve|exploit|hack)\b",
    re.IGNORECASE,
)

SUSPICIOUS_LOW_SIGNAL_PATTERNS = re.compile(
    r"\b(typo|comment|docstring|readme|changelog|version bump|cleanup|format|lint|spell)\b",
    re.IGNORECASE,
)


def run_git(repo: Path, args: list[str]) -> str:
    """Run git command, return stdout."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo)] + args,
            capture_output=True,
            text=True,
            timeout=60,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"WARN: git failed: {e}")
        return ""


def get_commits(repo: Path, since: str = None, limit: int = 500) -> list[dict]:
    """Get commits matching fix/audit keywords."""
    args = ["log", f"--max-count={limit}", "--pretty=format:%H|%ai|%an|%s"]
    if since:
        args.append(f"--since={since}")
    output = run_git(repo, args)

    commits = []
    for line in output.split("\n"):
        if not line.strip():
            continue
        parts = line.split("|", 3)
        if len(parts) < 4:
            continue
        sha, date, author, subject = parts
        if FIX_KEYWORDS.search(subject):
            commits.append({
                "sha": sha,
                "date": date,
                "author": author,
                "subject": subject,
            })
    return commits


def get_commit_diff_stats(repo: Path, sha: str) -> dict:
    """Get diff stats for a commit."""
    # numstat: lines added, lines removed, file
    output = run_git(repo, ["show", "--numstat", "--pretty=format:%b", sha])
    files = []
    body_lines = []
    total_add = 0
    total_del = 0
    for line in output.split("\n"):
        if not line.strip():
            continue
        # numstat lines look like: 12\t5\tpath/to/file
        parts = line.split("\t")
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            add, dele, fname = int(parts[0]), int(parts[1]), parts[2]
            total_add += add
            total_del += dele
            files.append({"file": fname, "added": add, "deleted": dele})
        else:
            body_lines.append(line)
    body = "\n".join(body_lines).strip()
    return {
        "files": files,
        "lines_added": total_add,
        "lines_deleted": total_del,
        "body": body[:500],
    }


def analyze_commit(commit: dict, diff_stats: dict) -> dict:
    """Analyze: does this fix-commit actually fix code?"""
    flags = []

    # Empty diff
    if diff_stats["lines_added"] == 0 and diff_stats["lines_deleted"] == 0:
        flags.append("EMPTY_DIFF")

    # Diff only touches docs/comments/readme
    only_docs = all(
        f["file"].endswith((".md", ".txt", ".rst", "README")) or
        "/docs/" in f["file"] or
        "/.github/" in f["file"]
        for f in diff_stats["files"]
    ) if diff_stats["files"] else False
    if only_docs and diff_stats["files"]:
        flags.append("DOCS_ONLY")

    # Diff is tiny but commit claims big fix
    if 0 < diff_stats["lines_added"] + diff_stats["lines_deleted"] <= 3:
        if any(kw in commit["subject"].lower() for kw in ("critical", "high", "severe", "vulnerab", "audit")):
            flags.append("CLAIM_BIG_TINY_DIFF")

    # Suspicious low-signal subject
    if SUSPICIOUS_LOW_SIGNAL_PATTERNS.search(commit["subject"]):
        flags.append("LOW_SIGNAL_SUBJECT")

    # Diff doesn't touch .sol but commit mentions security
    has_sol = any(f["file"].endswith(".sol") for f in diff_stats["files"])
    if not has_sol and "audit" in commit["subject"].lower():
        flags.append("NO_SOL_BUT_AUDIT")

    # Compute risk score
    score = 0
    if "EMPTY_DIFF" in flags:
        score += 5
    if "DOCS_ONLY" in flags:
        score += 4
    if "CLAIM_BIG_TINY_DIFF" in flags:
        score += 3
    if "NO_SOL_BUT_AUDIT" in flags:
        score += 3
    if "LOW_SIGNAL_SUBJECT" in flags:
        score += 1

    # Classification: known_class vs novel_instance
    # Known classes: "documented fix not applied" matches Alchemix pattern (commit 16e0882)
    if "EMPTY_DIFF" in flags or "DOCS_ONLY" in flags:
        classification = "known_class"
        broader_class = "stale_documentation_vs_current_code"
    elif "CLAIM_BIG_TINY_DIFF" in flags or "NO_SOL_BUT_AUDIT" in flags:
        classification = "novel_instance"
        broader_class = "audit_trail_mismatch"
    else:
        classification = "novel_instance"
        broader_class = "low_signal_security_commit"

    return {
        "flags": flags,
        "risk_score": score,
        "classification": classification,
        "broader_class": broader_class,
        "stats": diff_stats,
    }


def format_md(report: dict) -> str:
    """Generate hypothesis markdown."""
    lines = [
        "# Audit Trail Mining — Hypothesis Candidates",
        "",
        "Commits where message claims a security fix but diff is suspicious (empty, docs-only, or tiny).",
        "Each is a hypothesis: \"this fix was documented but maybe NOT actually applied to code.\"",
        "",
        "**Risk score**: empty_diff(5) + docs_only(4) + claim_big_tiny(3) + no_sol_but_audit(3) + low_signal(1)",
        "",
        "---",
        "",
    ]
    for idx, finding in enumerate(report["suspicious_commits"], 1):
        c = finding["commit"]
        analysis = finding["analysis"]
        lines.append(f"## H{idx}: `{c['sha'][:10]}` — score {analysis['risk_score']}")
        lines.append("")
        lines.append(f"- **Date**: {c['date']}")
        lines.append(f"- **Author**: {c['author']}")
        lines.append(f"- **Subject**: `{c['subject']}`")
        lines.append(f"- **Flags**: {', '.join(analysis['flags']) or 'none'}")
        lines.append(f"- **Diff**: +{analysis['stats']['lines_added']} −{analysis['stats']['lines_deleted']}, {len(analysis['stats']['files'])} files")
        if analysis["stats"]["files"]:
            files_short = [f"{f['file']}" for f in analysis["stats"]["files"][:5]]
            lines.append(f"- **Files**: {', '.join(files_short)}{'...' if len(analysis['stats']['files']) > 5 else ''}")
        lines.append("")
        lines.append("**Verification**: ")
        lines.append(f"```bash")
        lines.append(f"git show {c['sha']}")
        lines.append(f"```")
        lines.append("Then check: does the diff actually address what the subject says?")
        lines.append("If diff is docs-only or empty — the vulnerability may still be live in code.")
        lines.append("")
        lines.append("---")
        lines.append("")
    if not report["suspicious_commits"]:
        lines.append("_No suspicious commits found. Either repo is clean, or `--since` filter too narrow._")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description="Mine git history for fix-commits that don't actually fix code")
    p.add_argument("--repo", required=True, help="Path to git repository")
    p.add_argument("--output", default=".", help="Output directory")
    p.add_argument("--since", help="Date filter, e.g. 2024-01-01")
    p.add_argument("--limit", type=int, default=500, help="Max commits to scan")
    p.add_argument("--min-score", type=int, default=3, help="Minimum risk score to include")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    repo = Path(args.repo)
    if not repo.exists():
        print(f"ERROR: repo does not exist: {repo}")
        return 1
    if not (repo / ".git").exists():
        # Maybe target is a sub-folder; try parent
        if (repo.parent / ".git").exists():
            repo = repo.parent
        else:
            print(f"ERROR: not a git repository: {repo}")
            return 1

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.quiet:
        print(f"[*] Mining git history in {repo}...")

    commits = get_commits(repo, since=args.since, limit=args.limit)
    if not args.quiet:
        print(f"[+] Found {len(commits)} fix-keyword commits")

    suspicious = []
    for c in commits:
        diff_stats = get_commit_diff_stats(repo, c["sha"])
        analysis = analyze_commit(c, diff_stats)
        if analysis["risk_score"] >= args.min_score:
            suspicious.append({"commit": c, "analysis": analysis})

    suspicious.sort(key=lambda x: -x["analysis"]["risk_score"])

    report = {
        "repo": str(repo),
        "scanned_commits": len(commits),
        "suspicious_commits": suspicious,
    }

    json_path = output_dir / "audit_trail.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    md_path = output_dir / "audit_trail_findings.md"
    md_path.write_text(format_md(report), encoding="utf-8")

    if not args.quiet:
        print(f"[+] Suspicious commits: {len(suspicious)}")
        print(f"[+] JSON: {json_path}")
        print(f"[+] Markdown: {md_path}")
        if suspicious:
            print("\nTop suspicious commits:")
            for s in suspicious[:5]:
                c = s["commit"]
                flags = ",".join(s["analysis"]["flags"])
                print(f"  - {c['sha'][:10]} [{flags}] score={s['analysis']['risk_score']}  '{c['subject'][:60]}'")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
