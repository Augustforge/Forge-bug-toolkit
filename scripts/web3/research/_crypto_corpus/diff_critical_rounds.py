#!/usr/bin/env python3
"""
diff_critical_rounds.py — Cross-diff critical TSS round functions across
multiple implementations.

Approach: for each critical pattern (e.g., "Paillier biprime check"),
grep all repos and compare which have the check and which do not. Asymmetry
(N-1 have it, 1 doesn't) = candidate vulnerability.

Usage:
  python3 diff_critical_rounds.py
  python3 diff_critical_rounds.py --output diff_report.md
  python3 diff_critical_rounds.py --check paillier_biprime
"""
import argparse
import re
import sys
import time
from pathlib import Path

THIS_DIR = Path(__file__).parent
REPOS_DIR = THIS_DIR / "repos"

# Critical patterns. Each = canonical guard that *should* exist in correct impl.
# `regex` — what to grep. `context_lines` — for human review.
# `severity_if_missing` — severity warning if N-1 have it, 1 doesn't.
CHECKS = [
    {
        "id": "paillier_biprime",
        "what": "Paillier key biprime validation (N = p*q where p,q safe primes)",
        "regex": r"(biprime|BiPrime|isProductOfPrimes|safePrime|safe_prime|SafePrime)",
        "severity_if_missing": "critical",
        "where_should_be": "KeyGen round 1, Paillier key validation",
    },
    {
        "id": "paillier_modulus_bitlen",
        "what": "Paillier N bitlength check (>= 2048)",
        "regex": r"(BitLen|bit_len|bitLen|N\.BitLen|paillier.*2048|2048.*paillier)",
        "severity_if_missing": "high",
        "where_should_be": "KeyGen Paillier setup",
    },
    {
        "id": "zk_iterations_constant",
        "what": "ZK proof iterations constant (>= 128 for security)",
        "regex": r"(const|var)\s+(Iterations|ProofIters|ZKIters?|ZKProofIterations|RangeProofIterations)\s*=\s*\d+",
        "severity_if_missing": "critical",
        "where_should_be": "ZK proof package",
    },
    {
        "id": "schnorr_challenge_derivation",
        "what": "Schnorr challenge derived via Fiat-Shamir from full transcript",
        "regex": r"(challenge.*Hash|Hash.*challenge|fiat.*shamir|FiatShamir|hash_to_challenge)",
        "severity_if_missing": "high",
        "where_should_be": "Schnorr proof generation",
    },
    {
        "id": "mta_range_proof",
        "what": "MtA (Multiplicative-to-Additive) range proof verification",
        "regex": r"(MtA|MTAwc|range_proof|RangeProof|MtAwcVerify)",
        "severity_if_missing": "critical",
        "where_should_be": "Signing round 2-3",
    },
    {
        "id": "signature_aggregation_modular",
        "what": "Signature share aggregation with explicit modular reduction",
        "regex": r"(s\.Mod\(|sum\.Mod\(|\.Mod\(.*q\)|\.Mod\(.*N\)|modN|mod_n)",
        "severity_if_missing": "medium",
        "where_should_be": "Signing final aggregation",
    },
    {
        "id": "session_nonce_uniqueness",
        "what": "Per-session nonce / session_id uniqueness check",
        "regex": r"(sessionID|session_id|SessionId|nonce.*unique|nonce_used|usedNonces)",
        "severity_if_missing": "high",
        "where_should_be": "Ceremony coordinator",
    },
    {
        "id": "ggn_tssshock_iterations_match",
        "what": "Iterations constant matches across modproof/dlnproof (TSSHOCK class)",
        "regex": r"(modproof\.Iterations|dlnproof\.Iterations|ProofIters\s*=\s*128)",
        "severity_if_missing": "critical",
        "where_should_be": "Crypto package — all ZK proof types should use same iterations constant",
    },
]


def find_source_files(repo: Path) -> list[Path]:
    """Get all Go/Rust source files in repo."""
    out = []
    for ext in ("*.go", "*.rs"):
        out.extend(repo.rglob(ext))
    # Skip vendored / generated
    return [f for f in out if not any(p in f.parts for p in ("vendor", "target", "node_modules"))]


def grep_check(repo: Path, check: dict) -> list[tuple[Path, int, str]]:
    pat = re.compile(check["regex"], re.IGNORECASE)
    hits = []
    for f in find_source_files(repo):
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(content.splitlines(), 1):
                if pat.search(line):
                    hits.append((f.relative_to(repo), i, line.strip()[:150]))
                    if len(hits) >= 10:
                        return hits
        except Exception:
            continue
    return hits


def analyze(repos: list[Path], checks: list[dict]) -> dict:
    """For each check, for each repo, find hits. Compute asymmetry."""
    results = {}
    for check in checks:
        per_repo = {}
        for repo in repos:
            hits = grep_check(repo, check)
            per_repo[repo.name] = {
                "has_check": len(hits) > 0,
                "hit_count": len(hits),
                "sample_hits": hits[:3],
            }
        # Asymmetry: how many repos have it
        with_check = sum(1 for v in per_repo.values() if v["has_check"])
        total = len(per_repo)
        results[check["id"]] = {
            "check": check,
            "per_repo": per_repo,
            "with_check": with_check,
            "total": total,
            "asymmetry": with_check < total and with_check >= 1,
        }
    return results


def render_md(results: dict) -> str:
    lines = [
        f"# TSS Cross-Implementation Diff Report",
        f"",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}",
        f"",
        f"## How to read",
        f"",
        f"Each check represents a canonical safety guard. If N-1 implementations have it, ",
        f"and 1 does not — it is a **candidate vulnerability**. Open the files manually and work out:",
        f"- (a) legitimate optimization / different protocol variant?",
        f"- (b) forgotten safety check?",
        f"",
        f"## Asymmetric findings (PRIORITY)",
        f"",
    ]
    asymmetric = [r for r in results.values() if r["asymmetry"]]
    if not asymmetric:
        lines.append("_No asymmetric checks found. Either all implementations safe, or all uniformly missing._")
    else:
        for r in asymmetric:
            c = r["check"]
            lines.append(f"### {c['id']} — {c['severity_if_missing'].upper()}")
            lines.append(f"")
            lines.append(f"**What**: {c['what']}")
            lines.append(f"**Where should be**: {c['where_should_be']}")
            lines.append(f"")
            lines.append(f"| Repo | Has check? | Hits |")
            lines.append(f"|---|---|---|")
            for repo_name, info in r["per_repo"].items():
                mark = "yes" if info["has_check"] else "**MISSING**"
                lines.append(f"| {repo_name} | {mark} | {info['hit_count']} |")
            lines.append(f"")
            missing = [n for n, i in r["per_repo"].items() if not i["has_check"]]
            if missing:
                lines.append(f"**Action**: Open these repos and verify why check missing: {', '.join(missing)}")
            lines.append(f"")

    lines.append(f"## Full matrix")
    lines.append(f"")
    repos_list = sorted({n for r in results.values() for n in r["per_repo"]})
    lines.append(f"| Check | " + " | ".join(repos_list) + " |")
    lines.append(f"|---" * (len(repos_list) + 1) + "|")
    for cid, r in results.items():
        row = [cid]
        for repo_name in repos_list:
            info = r["per_repo"].get(repo_name, {})
            row.append("✓" if info.get("has_check") else "·")
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="diff_report.md")
    ap.add_argument("--check", help="Run only one check by id")
    args = ap.parse_args()

    if not REPOS_DIR.exists():
        print("[err] _crypto_corpus/repos/ not found. Run fetch.py first.", file=sys.stderr)
        sys.exit(1)

    repos = sorted([p for p in REPOS_DIR.iterdir() if p.is_dir()])
    if not repos:
        print("[err] no repos in _crypto_corpus/repos/. Run fetch.py first.", file=sys.stderr)
        sys.exit(1)

    print(f"[info] analyzing {len(repos)} repo(s): {[r.name for r in repos]}")

    checks = CHECKS if not args.check else [c for c in CHECKS if c["id"] == args.check]
    if args.check and not checks:
        print(f"[err] no check named {args.check}", file=sys.stderr)
        sys.exit(1)

    results = analyze(repos, checks)
    report = render_md(results)

    out = Path(args.output)
    out.write_text(report, encoding="utf-8")
    print(f"[ok] report: {out}")

    asymmetric = sum(1 for r in results.values() if r["asymmetry"])
    print(f"[info] {asymmetric} asymmetric finding(s) — open report for review")


if __name__ == "__main__":
    main()
