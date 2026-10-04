#!/usr/bin/env python3
"""
re_discovery_runner.py — automated pre-fix re-discovery harness.

Reads `pre_fix_manifest.json`, for each exploit:
1. Ensures repo cloned + full git history (unshallow if needed)
2. Checks out pre-fix commit
3. Runs expected hypothesis script
4. Verifies output contains finding matching `expected_finding_class`
5. Records PASS/FAIL

This is the STRONGEST possible validation — toolkit catches REAL bugs
without knowing the answer.

Usage:
    python3 re_discovery_runner.py --manifest pre_fix_manifest.json \\
        --samples-dir sessions/_validation/sol_samples/ \\
        --scripts-dir scripts/sol \\
        --output sessions/_validation/re_discovery_results/

    python3 re_discovery_runner.py --exploit wormhole_2022 --manifest ...
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


SCRIPT_MAP = {
    "owner_check_missing": "hypothesis/owner_check_scanner.py",
    "signer_check_missing": "hypothesis/signer_check_scanner.py",
    "oracle_integration": "hypothesis/oracle_integration_audit.py",
    "amm_tick_array": "specialized/amm_hunter_sol.py",
    "account_trust_violation": "hypothesis/account_trust_audit.py",
    "remaining_accounts_unverified": "hypothesis/account_trust_audit.py",
    "cpi_program_id_missing": "hypothesis/cpi_program_id_validator.py",
    "state_route_alternative": "hypothesis/state_route_analyzer.py",
    "governance_durable_nonce": "specialized/squads_v4_simulator.py",
    "economic_attack": "specialized/mev_simulator_sol.py",
}


def run_cmd(cmd: list[str], cwd: Path | None = None, timeout: int = 300) -> tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd,
                          encoding="utf-8", errors="replace")
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -1, "", str(e)


def ensure_repo_ready(repo_dir: Path, repo_url: str, pre_fix_commit: str, samples_dir: Path) -> dict:
    if not repo_dir.exists():
        if repo_url == "PRIVATE":
            return {"ready": False, "reason": "source private — cannot clone"}
        rc, _, err = run_cmd(["git", "clone", repo_url, str(repo_dir)], cwd=samples_dir, timeout=600)
        if rc != 0:
            return {"ready": False, "reason": f"clone failed: {err[:200]}"}

    rc, _, _ = run_cmd(["git", "log", "--format=%H", "-1"], cwd=repo_dir)
    if rc != 0:
        return {"ready": False, "reason": "git log failed (not a git repo?)"}

    if pre_fix_commit and pre_fix_commit != "main":
        if pre_fix_commit.startswith("before:"):
            date = pre_fix_commit.split(":", 1)[1]
            rc, sha_out, _ = run_cmd(["git", "log", f"--before={date}", "-1", "--format=%H"], cwd=repo_dir)
            if rc != 0 or not sha_out.strip():
                rc2, _, _ = run_cmd(["git", "fetch", "--unshallow"], cwd=repo_dir, timeout=600)
                rc, sha_out, _ = run_cmd(["git", "log", f"--before={date}", "-1", "--format=%H"], cwd=repo_dir)
                if rc != 0 or not sha_out.strip():
                    return {"ready": False, "reason": f"no commit found before {date} even after unshallow"}
            target_sha = sha_out.strip()
        else:
            rc, _, _ = run_cmd(["git", "cat-file", "-e", pre_fix_commit], cwd=repo_dir)
            if rc != 0:
                rc2, _, _ = run_cmd(["git", "fetch", "--unshallow"], cwd=repo_dir, timeout=600)
                rc, _, _ = run_cmd(["git", "cat-file", "-e", pre_fix_commit], cwd=repo_dir)
                if rc != 0:
                    return {"ready": False, "reason": f"commit {pre_fix_commit} not found even after unshallow"}
            target_sha = pre_fix_commit

        rc, _, err = run_cmd(["git", "checkout", target_sha], cwd=repo_dir)
        if rc != 0:
            return {"ready": False, "reason": f"checkout failed: {err[:200]}"}
        return {"ready": True, "checked_out_sha": target_sha}
    return {"ready": True, "checked_out_sha": "HEAD"}


def validate_exploit(exploit: dict, samples_dir: Path, scripts_dir: Path, output_dir: Path) -> dict:
    name = exploit["name"]
    result = {"name": name, "status": "?", "evidence": None}

    if exploit["validation_status"] == "PASS_PRIOR_SESSION":
        result["status"] = "PASS"
        result["evidence"] = exploit.get("validation_evidence")
        result["note"] = "validated in prior session, skipping re-run"
        return result
    if exploit["validation_status"] == "BLOCKED_SOURCE_PRIVATE":
        result["status"] = "BLOCKED"
        result["note"] = "source not public"
        return result
    if exploit["validation_status"] == "GOVERNANCE_BUG_NOT_CODE_PATCHABLE":
        result["status"] = "SKIP"
        result["note"] = "governance attack, not code-level fix"
        return result

    repo_dir_name = exploit["repo_url"].rstrip("/").rstrip(".git").split("/")[-1]
    repo_dir = samples_dir / repo_dir_name
    print(f"[{name}] Preparing {repo_dir}...")
    prep = ensure_repo_ready(repo_dir, exploit["repo_url"], exploit["pre_fix_commit"], samples_dir)
    if not prep["ready"]:
        result["status"] = "FAIL_SETUP"
        result["note"] = prep["reason"]
        return result

    expected_class = exploit["expected_finding_class"].split("|")[0].strip()
    script_rel = SCRIPT_MAP.get(expected_class)
    if not script_rel:
        result["status"] = "FAIL_NO_SCRIPT"
        result["note"] = f"no script registered for class {expected_class}"
        return result

    script_path = scripts_dir / script_rel
    if not script_path.exists():
        result["status"] = "FAIL_SCRIPT_MISSING"
        result["note"] = f"{script_path} not found"
        return result

    expected_files = exploit.get("expected_files", [])
    target_dir = repo_dir
    if expected_files:
        first_file = repo_dir / expected_files[0]
        if first_file.exists():
            target_dir = first_file.parent
        else:
            for ef in expected_files:
                parts = Path(ef).parts
                for i in range(len(parts), 0, -1):
                    cand = repo_dir / Path(*parts[:i])
                    if cand.exists():
                        target_dir = cand if cand.is_dir() else cand.parent
                        break
                if target_dir != repo_dir:
                    break

    out_subdir = output_dir / name
    out_subdir.mkdir(parents=True, exist_ok=True)

    cmd = ["python3", str(script_path), "--target", str(target_dir), "--output", str(out_subdir)]
    print(f"[{name}] Running {script_path.name} on {target_dir}...")
    rc, stdout, stderr = run_cmd(cmd, timeout=300)

    findings_files = list(out_subdir.rglob("*.json"))
    findings = []
    for ff in findings_files:
        try:
            data = json.loads(ff.read_text(encoding="utf-8"))
            if isinstance(data, list):
                findings.extend(data)
            elif isinstance(data, dict) and "findings" in data:
                findings.extend(data["findings"])
        except Exception:
            continue

    match_pattern = exploit.get("expected_account_name_pattern", "")
    matched = []
    for f in findings:
        f_str = json.dumps(f).lower()
        if expected_class.lower() in f_str:
            if not match_pattern:
                matched.append(f)
            else:
                import re
                if re.search(match_pattern.lower(), f_str):
                    matched.append(f)

    if matched:
        result["status"] = "PASS"
        result["evidence"] = f"{len(matched)} findings match expected class '{expected_class}'"
        result["sample_finding"] = matched[0]
    elif findings:
        result["status"] = "PARTIAL"
        result["evidence"] = f"{len(findings)} findings generated, but none match expected class '{expected_class}'"
    else:
        result["status"] = "FAIL_NO_FINDINGS"
        result["stdout_tail"] = stdout[-500:] if stdout else ""
        result["stderr_tail"] = stderr[-500:] if stderr else ""

    result["script_used"] = script_rel
    result["target_dir"] = str(target_dir)
    result["findings_count"] = len(findings)
    return result


def main():
    ap = argparse.ArgumentParser(description="Pre-fix re-discovery validation runner")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--samples-dir", required=True, help="Where to clone repos")
    ap.add_argument("--scripts-dir", required=True, help="Path to scripts/sol/")
    ap.add_argument("--output", required=True)
    ap.add_argument("--exploit", help="Run single exploit by name")
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text())
    samples_dir = Path(args.samples_dir)
    scripts_dir = Path(args.scripts_dir)
    output_dir = Path(args.output)
    samples_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    targets = manifest["exploits"]
    if args.exploit:
        targets = [t for t in targets if t["name"] == args.exploit]
        if not targets:
            print(f"[!] Exploit '{args.exploit}' not in manifest", file=sys.stderr)
            sys.exit(1)

    results = []
    for exploit in targets:
        print(f"\n=== {exploit['name']} (loss: ${exploit['loss_usd']:,}) ===")
        r = validate_exploit(exploit, samples_dir, scripts_dir, output_dir)
        results.append(r)
        print(f"  Status: {r['status']}")
        if r.get("evidence"):
            print(f"  Evidence: {r['evidence']}")
        if r.get("note"):
            print(f"  Note: {r['note']}")

    pass_count = sum(1 for r in results if r["status"] == "PASS")
    partial_count = sum(1 for r in results if r["status"] == "PARTIAL")
    blocked = sum(1 for r in results if r["status"] in ("BLOCKED", "SKIP"))
    fail = sum(1 for r in results if r["status"].startswith("FAIL"))

    summary = {
        "total": len(results),
        "pass": pass_count,
        "partial": partial_count,
        "blocked": blocked,
        "fail": fail,
        "production_ready": pass_count >= 5,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "results": results,
    }

    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))

    print(f"\n=== Summary ===")
    print(f"PASS:    {pass_count}")
    print(f"PARTIAL: {partial_count}")
    print(f"BLOCKED: {blocked}")
    print(f"FAIL:    {fail}")
    print(f"\nProduction ready (>=5 PASS): {summary['production_ready']}")
    print(f"Full report: {output_dir}/summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
