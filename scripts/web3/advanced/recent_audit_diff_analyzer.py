#!/usr/bin/env python3
"""
recent_audit_diff_analyzer.py — Identify code changes since last audit.

Post-audit code is THE bug-rich zone — auditor coverage stops at commit X,
but development continues. Bugs introduced after X have never been formally
reviewed. This is statistically the highest-density bug surface in any
audited protocol.

WORKFLOW:
1. Take audit metadata (from `audit_pdf_parser.py` output OR manual --audit-date)
2. Walk git history from audit_commit → HEAD
3. Identify added/modified handlers, CPIs, account validation logic
4. Classify each change by risk surface:
   - NEW INSTRUCTION HANDLER (highest risk: untouched by audit)
   - MODIFIED VALIDATION (high: regression risk)
   - NEW CPI CALL (medium-high: trust assumption)
   - REFACTOR (medium: behavior preserved? check)
   - DOCS/COMMENT (low)

CLASSIFICATION:
  - [known_class] = pattern matches commonly-bugged post-audit categories
  - [novel_instance] = unique change requiring manual review

USAGE:
    python3 recent_audit_diff_analyzer.py \
        --repo path/to/repo \
        --audit-date 2024-03-15 \
        --output sessions/$TARGET/deep/audit_diff/
    python3 recent_audit_diff_analyzer.py \
        --repo path/to/repo \
        --audit-commit abc123 \
        --output ...
    python3 recent_audit_diff_analyzer.py \
        --audit-meta sessions/$TARGET/deep/audits_analysis.json \
        --output ...

Chain-agnostic (works for EVM + Solana + others where source is git-tracked).
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


HIGH_RISK_PATTERNS = {
    "new_pub_fn": re.compile(r"^\+\s*pub\s+fn\s+(\w+)"),
    "new_handler_anchor": re.compile(r"^\+\s*pub\s+fn\s+(\w+)\s*\([^)]*ctx:\s*Context"),
    "new_external_call": re.compile(r"^\+.*?\b(invoke|invoke_signed|call|delegatecall|staticcall)\s*\("),
    "new_modifier": re.compile(r"^\+\s*modifier\s+(\w+)"),
    "new_struct": re.compile(r"^\+\s*pub\s+struct\s+(\w+)"),
    "removed_check": re.compile(r"^-\s*(?:require|assert|require!|require_keys_eq!)\b"),
    "added_unsafe": re.compile(r"^\+\s*unsafe\s*\{"),
    "new_account_field": re.compile(r"^\+\s*pub\s+(\w+):\s*(?:Account|UncheckedAccount|AccountInfo|Box)<"),
    "weakened_visibility": re.compile(r"^\-\s*(?:pub\(crate\)|priv)\s+fn.*\n\+\s*pub\s+fn"),
    "new_token_transfer": re.compile(r"^\+.*?\b(transfer_checked|transfer|spl_token::instruction::transfer|withdraw)\s*\("),
    "new_lamport_modification": re.compile(r"^\+.*?\.lamports\s*[+\-*/]?=|^\+.*?lamports\s*\(\s*\)\s*\.\s*borrow_mut"),
    "new_state_mutation_without_guard": re.compile(r"^\+\s*\w+\.\w+\s*=\s*\w+"),
}


STATE_GUARD_PATTERNS = [
    re.compile(r"require!\s*\(\s*[^)]*flag", re.IGNORECASE),
    re.compile(r"require!\s*\(\s*[^)]*[Ii]n_[Ff]lash[Ll]oan"),
    re.compile(r"require!\s*\(\s*[^)]*locked|require!\s*\(\s*[^)]*paused"),
    re.compile(r"check_account_state|verify_state|guard_against"),
    re.compile(r"FlashLoanFlag|ACCOUNT_IN_FLASHLOAN|in_progress|is_locked"),
]


STATE_FLAG_FIELDS = [
    re.compile(r"(?:in_flashloan|flash_loan_in_progress|is_locked|paused|frozen|in_progress|reentrancy_guard|emergency_mode):\s*bool"),
    re.compile(r"flags:\s*\w*[Ff]lag|state:\s*\w*[Ss]tate"),
]


MEDIUM_RISK_PATTERNS = {
    "modified_validation": re.compile(r"^\+.*?\b(require|assert|require_keys_eq|require_gte|require_eq)\b"),
    "modified_cpi": re.compile(r"^[-+].*?\b(invoke|invoke_signed)\s*\("),
    "modified_arithmetic": re.compile(r"^[-+].*?\b(checked_add|checked_sub|checked_mul|checked_div|saturating_)\b"),
    "modified_account_constraint": re.compile(r"^[-+].*?#\[account\("),
}


LOW_SIGNAL_PATTERNS = {
    "comment_only": re.compile(r"^[+-]\s*(?://|/\*|\*|#)"),
    "test_only": re.compile(r"^[+-].*?#\[test|#\[cfg\(test"),
    "import_only": re.compile(r"^[+-]\s*use\s+"),
    "format_only": re.compile(r"^[+-]\s*$"),
}


# === E/G extension (pashov x-ray git-security): adds analytic AXES on top of the risk tiers —
# directional guards, intent category, domain overlap, late/rushed-change weighting. All purely
# additive: existing JSON keys (high_risk_changes/medium_risk_changes/summary/low_signal_count)
# are preserved; new fields are attached to each finding + new top-level keys appended. ===
GUARD_ADDED_PATTERN = re.compile(
    r"^\+\s*(?:require!?|assert!?|require_keys_eq!|require_eq!?|require_gte!?|require_neq!?)\b"
    r"|^\+\s*if\s*\(.*\)\s*\{?\s*(?:revert|require)")
GUARD_REMOVED_PATTERN = re.compile(
    r"^-\s*(?:require!?|assert!?|require_keys_eq!|require_eq!?|require_gte!?|require_neq!?)\b"
    r"|^-\s*if\s*\(.*\)\s*\{?\s*(?:revert|require)")

INTENT_BY_CATEGORY = {
    "new_pub_fn": "new-surface", "new_handler_anchor": "new-surface", "new_struct": "new-surface",
    "new_account_field": "new-surface",
    "new_external_call": "new-trust-edge", "modified_cpi": "new-trust-edge",
    "new_modifier": "access-change", "weakened_visibility": "access-change",
    "modified_account_constraint": "access-change",
    "removed_check": "guard-weakening", "added_unsafe": "safety-downgrade",
    "new_token_transfer": "value-flow", "new_lamport_modification": "value-flow",
    "new_state_mutation_without_guard": "state-change",
    "modified_validation": "guard-change", "modified_arithmetic": "arithmetic-change",
}

DOMAIN_KEYWORDS = {
    "oracle": re.compile(r"oracle|price|latestAnswer|getPrice|twap|updatedAt|sqrtPrice", re.I),
    "accounting": re.compile(r"balance|shares?|totalSupply|totalAssets|debt|collateral|reserve|liquidit", re.I),
    "access": re.compile(r"owner|admin|role|onlyOwner|authority|signer|require_keys|access|guardian", re.I),
    "value_flow": re.compile(r"transfer|withdraw|mint|burn|lamport|redeem|payout|deposit", re.I),
    "math": re.compile(r"checked_|saturating_|unchecked|\bmul\b|\bdiv\b|<<|>>|1e1[0-9]|\bcast|uint\d", re.I),
}

RUSHED_SUBJECT = re.compile(
    r"\b(hotfix|quick\s?fix|wip|temp(?:orary)?|revert|asap|urgent|last[\s-]?minute|band[\s-]?aid|todo|fixme)\b", re.I)


def intent_of(category: str) -> str:
    return INTENT_BY_CATEGORY.get(category, "other")


def domain_of(snippet: str) -> list[str]:
    return [d for d, pat in DOMAIN_KEYWORDS.items() if pat.search(snippet)]


def guard_direction(line: str) -> str | None:
    """Directional guard signal: a REMOVED guard = regression risk (high); an ADDED guard = defensive
    (often the fix for a still-unpatched-elsewhere bug → check siblings). None = not a guard line."""
    if GUARD_REMOVED_PATTERN.search(line):
        return "removed"
    if GUARD_ADDED_PATTERN.search(line):
        return "added"
    return None


def detect_late_changes(commits: list[dict]) -> list[dict]:
    """git-security 'late = rushed = risk' weighting. Flags the most-recent decile of commits
    (closest to HEAD/release = least settled) and any commit whose subject signals rushing.
    These cluster post-audit hotspots — weight their touched files higher in T1."""
    late = []
    recent_cutoff = max(1, len(commits) // 10)  # commits list is newest-first (git log default)
    for idx, c in enumerate(commits):
        reasons = []
        if idx < recent_cutoff:
            reasons.append("most-recent-decile")
        if RUSHED_SUBJECT.search(c.get("subject", "")):
            reasons.append("rushed-subject")
        if reasons:
            late.append({**c, "late_reasons": reasons})
    return late


def run_git(repo: Path, args: list[str]) -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(repo)] + args,
            capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="replace",
        )
        return r.stdout
    except Exception as e:
        print(f"[!] git error: {e}", file=sys.stderr)
        return ""


def resolve_audit_commit(repo: Path, audit_date: str | None, audit_commit: str | None) -> str | None:
    """Return commit hash representing the audit baseline."""
    if audit_commit:
        return audit_commit
    if not audit_date:
        return None
    out = run_git(repo, ["log", f"--before={audit_date}", "-1", "--format=%H"])
    return out.strip() or None


def get_commits_since(repo: Path, base_commit: str) -> list[dict]:
    out = run_git(repo, [
        "log", f"{base_commit}..HEAD",
        "--format=%H%n%an%n%ad%n%s%n---END---",
        "--date=iso",
    ])
    commits = []
    for chunk in out.split("---END---"):
        chunk = chunk.strip()
        if not chunk:
            continue
        lines = chunk.split("\n")
        if len(lines) >= 4:
            commits.append({
                "sha": lines[0],
                "author": lines[1],
                "date": lines[2],
                "subject": lines[3],
            })
    return commits


def get_diff(repo: Path, base_commit: str, target_extensions: tuple) -> str:
    paths_filter = []
    for ext in target_extensions:
        paths_filter.extend(["--", f"*{ext}"])
    out = run_git(repo, [
        "diff", base_commit, "HEAD",
        "--unified=3",
    ])
    return out


def classify_diff_chunks(diff: str, extensions: tuple, repo_path: Path | None = None,
                          include_paths: tuple = ()) -> dict:
    findings = {"high_risk": [], "medium_risk": [], "low_signal_count": 0}

    has_state_flags = False
    if repo_path:
        for rs_file in list(repo_path.rglob("*.rs"))[:50]:
            try:
                text = rs_file.read_text(encoding="utf-8", errors="ignore")
                if any(p.search(text) for p in STATE_FLAG_FIELDS):
                    has_state_flags = True
                    break
            except Exception:
                continue

    current_file = None
    current_hunk_header = None
    line_in_file = 0

    in_target_file = False
    new_handler_buffer = []

    for line in diff.split("\n"):
        if line.startswith("diff --git "):
            m = re.match(r"diff --git a/(.+?) b/(.+)", line)
            if m:
                current_file = m.group(2)
                ext_ok = any(current_file.endswith(ext) for ext in extensions)
                path_ok = (not include_paths) or any(p in current_file for p in include_paths)
                in_target_file = ext_ok and path_ok
            continue
        if not in_target_file:
            continue
        if line.startswith("@@"):
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            if m:
                line_in_file = int(m.group(1))
            current_hunk_header = line
            continue

        finding_added = False

        for category, pattern in HIGH_RISK_PATTERNS.items():
            if pattern.search(line):
                special_note = None
                special_severity_boost = False
                if has_state_flags and category in ("new_handler_anchor", "new_pub_fn", "new_token_transfer", "new_lamport_modification"):
                    special_note = ("Protocol uses state flags (flash_loan/locked/paused). New handler/transfer "
                                    "MUST verify state flag — Marginfi 2025 ($160M class) re-discovery pattern.")
                    special_severity_boost = True

                findings["high_risk"].append({
                    "category": category,
                    "file": current_file,
                    "line": line_in_file,
                    "snippet": line[:200],
                    "classification": "novel_instance" if category in (
                        "new_pub_fn", "new_handler_anchor", "removed_check", "added_unsafe",
                        "new_token_transfer", "new_lamport_modification"
                    ) else "known_class",
                    "broader_class": "post_audit_state_guard_omission" if special_severity_boost else "post_audit_high_risk_change",
                    "special_note": special_note,
                    "severity_boost": special_severity_boost,
                    # E/G axes (additive)
                    "intent": intent_of(category),
                    "direction": guard_direction(line),
                    "domain": domain_of(line),
                })
                finding_added = True
                break

        if not finding_added:
            for category, pattern in MEDIUM_RISK_PATTERNS.items():
                if pattern.search(line):
                    findings["medium_risk"].append({
                        "category": category,
                        "file": current_file,
                        "line": line_in_file,
                        "snippet": line[:200],
                        "classification": "novel_instance",
                        "broader_class": "post_audit_medium_risk_change",
                        # E/G axes (additive)
                        "intent": intent_of(category),
                        "direction": guard_direction(line),
                        "domain": domain_of(line),
                    })
                    finding_added = True
                    break

        if not finding_added:
            for pattern in LOW_SIGNAL_PATTERNS.values():
                if pattern.search(line):
                    findings["low_signal_count"] += 1
                    break

        if line.startswith("+") or line.startswith("-"):
            if line.startswith("+"):
                line_in_file += 1

    return findings


def main():
    ap = argparse.ArgumentParser(description="Identify code changes since last audit baseline")
    ap.add_argument("--repo", help="Git repo path")
    ap.add_argument("--audit-date", help="Audit completion date (YYYY-MM-DD) — find latest commit before this")
    ap.add_argument("--audit-commit", help="Explicit commit hash of audit baseline")
    ap.add_argument("--audit-meta", help="JSON output from audit_pdf_parser.py (extracts audit_date)")
    ap.add_argument("--extensions", default=".rs,.sol",
                    help="Comma-separated extensions to analyze")
    ap.add_argument("--include-paths", default=None,
                    help="Comma-separated path substrings to include (e.g., 'programs/,contracts/'). "
                         "Excludes CLI/client/test code from diff analysis.")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    extensions = tuple(args.extensions.split(","))
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    repo = Path(args.repo) if args.repo else None
    audit_date = args.audit_date
    audit_commit = args.audit_commit

    if args.audit_meta:
        meta = json.loads(Path(args.audit_meta).read_text())
        if not audit_date:
            audit_date = meta.get("latest_audit_date") or meta.get("audit_date")
        if not repo:
            repo = Path(meta.get("repo_path", "."))

    if not repo or not repo.exists():
        print(f"[!] Repo not found: {repo}", file=sys.stderr)
        sys.exit(1)

    base = resolve_audit_commit(repo, audit_date, audit_commit)
    if not base:
        print("[!] Provide --audit-date or --audit-commit or --audit-meta with audit_date", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Analyzing changes since {base[:10]} ({audit_date or 'commit-pinned'})")

    commits = get_commits_since(repo, base)
    print(f"[+] Found {len(commits)} commits since audit baseline")

    include_paths = tuple(args.include_paths.split(",")) if args.include_paths else ()
    diff = get_diff(repo, base, extensions)
    findings = classify_diff_chunks(diff, extensions, repo_path=repo, include_paths=include_paths)

    # E/G git-security axes (additive analytics over the same findings)
    late_changes = detect_late_changes(commits)
    late_files = sorted({c["sha"][:10] for c in late_changes})
    all_findings = findings["high_risk"] + findings["medium_risk"]
    removed_guards = [f for f in all_findings if f.get("direction") == "removed"]
    added_guards = [f for f in all_findings if f.get("direction") == "added"]
    domain_overlap = {}
    for f in all_findings:
        for d in f.get("domain", []):
            domain_overlap[d] = domain_overlap.get(d, 0) + 1

    report = {
        "repo": str(repo),
        "audit_baseline_commit": base,
        "audit_date": audit_date,
        "extensions": list(extensions),
        "commits_since_audit": len(commits),
        "recent_commits": commits[:20],
        "high_risk_changes": findings["high_risk"],
        "medium_risk_changes": findings["medium_risk"],
        "low_signal_count": findings["low_signal_count"],
        # E/G additive top-level keys (existing keys above untouched)
        "late_changes": late_changes,
        "git_risk_signals": {
            "late_change_commits": len(late_changes),
            "removed_guards": removed_guards,         # regression-risk: a check disappeared
            "added_guards_count": len(added_guards),  # often the fix → check siblings for unpatched twins
            "domain_overlap": domain_overlap,         # how many changes touch oracle/accounting/access/value/math
        },
        "summary": {
            "high_risk_count": len(findings["high_risk"]),
            "medium_risk_count": len(findings["medium_risk"]),
            "novel_instances": sum(1 for f in findings["high_risk"] + findings["medium_risk"]
                                   if f.get("classification") == "novel_instance"),
            # additive sub-counts
            "removed_guard_count": len(removed_guards),
            "late_change_count": len(late_changes),
        },
    }

    out_file = out_dir / "audit_diff_report.json"
    out_file.write_text(json.dumps(report, indent=2, default=str))

    print(f"\n[+] Audit diff analysis complete:")
    print(f"    HIGH RISK changes: {len(findings['high_risk'])}")
    print(f"    MEDIUM RISK changes: {len(findings['medium_risk'])}")
    print(f"    Low-signal (comments/imports/tests): {findings['low_signal_count']}")
    print(f"    Novel instances (manual review priority): {report['summary']['novel_instances']}")

    if removed_guards:
        print(f"\n  [!] REMOVED GUARDS (regression risk — {len(removed_guards)}):")
        for f in removed_guards[:10]:
            dom = ("/".join(f["domain"]) or "-")
            print(f"      {f['file']}:{f['line']}  domain={dom}")
    if late_changes:
        print(f"    Late/rushed commits (git-security hotspot): {len(late_changes)}")
    if domain_overlap:
        print(f"    Domain overlap: " + ", ".join(f"{d}={n}" for d, n in sorted(domain_overlap.items())))

    if findings["high_risk"]:
        print(f"\nTop HIGH risk changes:")
        seen_files = set()
        for f in findings["high_risk"][:15]:
            tag = f"[{f['classification']}]"
            intent = f.get("intent", "other")
            print(f"  {tag} {f['category']:30} {f['file']}:{f['line']}  intent={intent}")
            seen_files.add(f["file"])

    print(f"\n[+] Saved to {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
