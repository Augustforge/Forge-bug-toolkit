#!/usr/bin/env python3
"""
CI/CD artifact leak scanner — the most underrated bug bounty gap (2025).

Real findings of $25k+ in March 2025 (tj-actions/changed-files compromise,
ArtiPACKED CVE-2025-30066). The idea is simple: GitHub Actions artifacts often
contain secrets in build logs, "oops commits" in deleted PRs leak through
the Events API, and CircleCI/Travis hosted logs are also publicly accessible.

Sources:
- Wiz: tj-actions supply chain attack
- Unit42: ArtiPACKED research
- Multiple researchers found $25k+ via GitHub Actions log scraping

Usage:
    python3 cicd_leak_scanner.py --org companyname --output sessions/companyname
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import zipfile
from io import BytesIO
from pathlib import Path

import requests

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
HEADERS = {"Accept": "application/vnd.github+json"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"

# Compromised actions to flag immediately (CVE-2025-30066 pattern)
COMPROMISED_ACTIONS = [
    "tj-actions/changed-files",
    "reviewdog/action-setup",
    "reviewdog/action-shellcheck",
    "reviewdog/action-composite-template",
]

SECRET_REGEXES = {
    # gh[pousr]_ covers ghp_/gho_/ghu_/ghs_/ghr_ (5 of 6 legacy PAT/OAuth/app-token formats);
    # github_pat_ is the newer fine-grained PAT format (2022+) — 6th format, distinct prefix shape.
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}|github_pat_[A-Za-z0-9_]{20,}"),
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "aws_secret_key": re.compile(r"(?i)aws_secret[_a-z]*\s*[=:]\s*['\"]?([a-zA-Z0-9/+=]{40})"),
    "slack_token": re.compile(r"xox[baprs]-[0-9a-zA-Z\-]{10,48}"),
    "google_api": re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
    "stripe_live": re.compile(r"sk_live_[0-9a-zA-Z]{24,}"),
    "discord_token": re.compile(r"[MN][A-Za-z0-9_-]{23}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"),
    "jwt": re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    "generic_secret": re.compile(
        r"(?i)(secret|password|token|api[_-]?key)\s*[=:]\s*['\"]([a-zA-Z0-9_\-]{20,})['\"]"
    ),
}


def list_repos(org: str, max_pages: int = 5) -> list[dict]:
    repos = []
    for page in range(1, max_pages + 1):
        try:
            r = requests.get(
                f"https://api.github.com/orgs/{org}/repos",
                headers=HEADERS,
                params={"per_page": 100, "page": page, "type": "public"},
                timeout=20,
            )
            if r.status_code != 200:
                break
            batch = r.json()
            if not batch:
                break
            repos.extend(batch)
        except Exception:
            break
    return repos


def list_artifacts(repo_full: str) -> list[dict]:
    try:
        r = requests.get(
            f"https://api.github.com/repos/{repo_full}/actions/artifacts",
            headers=HEADERS, params={"per_page": 100}, timeout=20,
        )
        if r.status_code != 200:
            return []
        return r.json().get("artifacts", [])[:50]
    except Exception:
        return []


def list_workflow_runs(repo_full: str) -> list[dict]:
    try:
        r = requests.get(
            f"https://api.github.com/repos/{repo_full}/actions/runs",
            headers=HEADERS, params={"per_page": 30}, timeout=20,
        )
        if r.status_code != 200:
            return []
        return r.json().get("workflow_runs", [])
    except Exception:
        return []


def fetch_run_logs(repo_full: str, run_id: int) -> str:
    """Logs only for public repos (or with auth)."""
    try:
        r = requests.get(
            f"https://api.github.com/repos/{repo_full}/actions/runs/{run_id}/logs",
            headers=HEADERS, timeout=30,
        )
        if r.status_code != 200:
            return ""
        try:
            zf = zipfile.ZipFile(BytesIO(r.content))
            text_chunks = []
            for name in zf.namelist():
                try:
                    text_chunks.append(zf.read(name).decode("utf-8", errors="ignore"))
                except Exception:
                    continue
            return "\n".join(text_chunks)
        except zipfile.BadZipFile:
            return r.text
    except Exception:
        return ""


def scan_text_for_secrets(text: str) -> list[dict]:
    findings = []
    for name, pattern in SECRET_REGEXES.items():
        for m in pattern.finditer(text)[:5] if hasattr(pattern.finditer(text), '__getitem__') else list(pattern.finditer(text))[:5]:
            findings.append({
                "type": name,
                "match": m.group(0)[:80] + ("..." if len(m.group(0)) > 80 else ""),
            })
    return findings


def find_secrets(text: str) -> list[dict]:
    findings = []
    for name, pattern in SECRET_REGEXES.items():
        matches = list(pattern.finditer(text))[:5]
        for m in matches:
            findings.append({
                "type": name,
                "preview": m.group(0)[:80],
            })
    return findings


def check_compromised_actions(repo_full: str) -> list[dict]:
    """Scans .github/workflows/ for use of compromised actions."""
    found = []
    try:
        r = requests.get(
            f"https://api.github.com/repos/{repo_full}/contents/.github/workflows",
            headers=HEADERS, timeout=15,
        )
        if r.status_code != 200:
            return []
        for f in r.json():
            if not f.get("name", "").endswith((".yml", ".yaml")):
                continue
            content_r = requests.get(f["download_url"], timeout=15)
            if content_r.status_code != 200:
                continue
            content = content_r.text
            for action in COMPROMISED_ACTIONS:
                if action in content:
                    found.append({
                        "workflow": f["name"],
                        "compromised_action": action,
                        "url": f["html_url"],
                        "severity": "CRITICAL",
                    })
    except Exception:
        pass
    return found


def trufflehog_repo(repo_url: str, out_dir: Path) -> int:
    """Run trufflehog on repo. Returns count of findings."""
    if not shutil_which("trufflehog"):
        return -1
    try:
        out_file = out_dir / f"trufflehog_{repo_url.rstrip('/').split('/')[-1]}.json"
        result = subprocess.run(
            ["trufflehog", "git", repo_url, "--json", "--no-update", "--only-verified"],
            capture_output=True, text=True, timeout=300,
        )
        if result.stdout:
            out_file.write_text(result.stdout)
            return result.stdout.count("\n")
    except Exception:
        return -1
    return 0


def shutil_which(cmd: str) -> str | None:
    import shutil
    return shutil.which(cmd)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--org", required=True, help="GitHub organization name")
    ap.add_argument("--output", required=True)
    ap.add_argument("--max-repos", type=int, default=20)
    ap.add_argument("--scan-logs", action="store_true",
                    help="Download and scan workflow run logs (slow)")
    ap.add_argument("--trufflehog", action="store_true",
                    help="Run trufflehog on each repo (slow but thorough)")
    args = ap.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    if not GITHUB_TOKEN:
        print("[!] GITHUB_TOKEN not set — heavily rate limited")

    print(f"[*] Listing public repos for org: {args.org}")
    repos = list_repos(args.org)[:args.max_repos]
    print(f"    {len(repos)} repos")

    results = {
        "org": args.org,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "repos_scanned": len(repos),
        "compromised_actions": [],
        "artifact_secrets": [],
        "log_secrets": [],
        "trufflehog_findings": {},
    }

    for repo in repos:
        full = repo["full_name"]
        print(f"[*] {full}")

        compromised = check_compromised_actions(full)
        if compromised:
            print(f"    [!!] {len(compromised)} compromised actions used")
            for c in compromised:
                c["repo"] = full
            results["compromised_actions"].extend(compromised)

        artifacts = list_artifacts(full)
        if artifacts:
            print(f"    {len(artifacts)} artifacts")
            for a in artifacts[:5]:
                if not a.get("archive_download_url"):
                    continue
                try:
                    r = requests.get(a["archive_download_url"],
                                     headers=HEADERS, timeout=60, stream=True)
                    if r.status_code != 200:
                        continue
                    content = r.content[:5_000_000]  # 5MB cap
                    try:
                        zf = zipfile.ZipFile(BytesIO(content))
                        for name in zf.namelist()[:20]:
                            try:
                                text = zf.read(name).decode("utf-8", errors="ignore")[:100_000]
                                secs = find_secrets(text)
                                if secs:
                                    results["artifact_secrets"].append({
                                        "repo": full, "artifact": a["name"],
                                        "file": name, "secrets": secs,
                                    })
                                    print(f"      [!!] secrets in {a['name']}/{name}: "
                                          f"{[s['type'] for s in secs]}")
                            except Exception:
                                continue
                    except zipfile.BadZipFile:
                        pass
                except Exception:
                    continue
                time.sleep(1)

        if args.scan_logs:
            runs = list_workflow_runs(full)[:5]
            for run in runs:
                logs = fetch_run_logs(full, run["id"])
                if logs:
                    secs = find_secrets(logs)
                    if secs:
                        results["log_secrets"].append({
                            "repo": full, "run_id": run["id"],
                            "url": run.get("html_url"),
                            "secrets": secs,
                        })
                        print(f"    [!!] secrets in run #{run['id']}: "
                              f"{[s['type'] for s in secs]}")
                time.sleep(1)

        if args.trufflehog:
            count = trufflehog_repo(repo["clone_url"], out)
            results["trufflehog_findings"][full] = count

        time.sleep(0.5)

    summary = out / "cicd_leaks.json"
    summary.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    print("\n[+] Summary:")
    print(f"    Compromised actions used: {len(results['compromised_actions'])}")
    print(f"    Artifact secrets:         {len(results['artifact_secrets'])}")
    print(f"    Log secrets:              {len(results['log_secrets'])}")
    print(f"    Saved: {summary}")

    if results["compromised_actions"] or results["artifact_secrets"] or results["log_secrets"]:
        print("\n[!] HIGH PRIORITY: actionable findings detected")


if __name__ == "__main__":
    main()
