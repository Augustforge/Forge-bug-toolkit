#!/usr/bin/env python3
"""
aa_erc4337_classifier.py — Auto-classifier for ERC-4337 Account Abstraction targets.

Mirror of bridge_detector.py — scans target source code for AA framework imports +
entry function names + storage signatures. If confident → writes
`protocol_class:account-abstraction` + framework tags to `_tags.txt`.

Unlocks auto-matching of:
  - threat_models/erc4337_signature_replay.yaml
  - checklists/specialized/aa_erc4337.md
  - detectors/erc4337_issues.py
  - specialized/aa_erc4337_hunter.py

Without this, the operator must manually tag AA targets via `_tags.txt`.

Usage:
  py -3 aa_erc4337_classifier.py --target sessions/$T --source-path $REPO
  py -3 aa_erc4337_classifier.py --target sessions/$T              # uses chain.json source_path
  py -3 aa_erc4337_classifier.py --target sessions/$T --dry-run    # report only

Idempotent — safe to re-run.

Confidence levels:
  STRONG   — 2+ evidence categories (framework + entry function OR storage)
  POSSIBLE — 1 evidence category — writes "possible-aa" tag, requires manual review
  NONE     — no match
"""
import argparse
import json
import re
import sys
from pathlib import Path


# Framework signature → tag mapping
# Covers: EntryPoint v0.6/v0.7/v0.8, popular smart account stacks, paymaster libs.
FRAMEWORK_PATTERNS = {
    "entrypoint-v06": [
        r"\bIEntryPoint\b", r"\b0x5FF137D4b0FDCD49DcA30c7CF57E578a026d2789\b",
    ],
    "entrypoint-v07": [
        r"\b0x0000000071727De22E5E9d8BAf0edAc6f37da032\b",
        r"\bPackedUserOperation\b",
    ],
    "entrypoint-v08": [
        r"\b0x4337084D9E255Ff0702461CF8895CE9E3b5Ff108\b",
    ],
    "zerodev-kernel": [
        r"\bKernel\b.*account", r"\bIKernel\b", r"\bKernelStorage\b",
        r"\bExecutionDetail\b", r"\bIValidator\b.*kernel",
    ],
    "safe-account": [
        r"\bSafe4337Module\b", r"\bSafeProxyFactory\b",
        r"\bSafe\b.*ModuleManager", r"\bExecTransactionFromModule\b",
    ],
    "biconomy": [
        r"\bBiconomy\b", r"\bSmartAccount\b.*Biconomy", r"\bModuleManager\b.*Biconomy",
    ],
    "alchemy-light-account": [
        r"\bLightAccount\b", r"\bLightAccountFactory\b", r"\bUpgradeableModularAccount\b",
    ],
    "coinbase-smart-wallet": [
        r"\bCoinbaseSmartWallet\b", r"\bMultiOwnable\b.*Coinbase",
    ],
    "etherspot": [
        r"\bEtherspot\b", r"\bModularEtherspotWallet\b",
    ],
    "erc-7579-modular": [
        r"\bIERC7579\b", r"\bERC7579\b", r"\bModuleManager\b",
        r"\binstallModule\b", r"\buninstallModule\b",
    ],
    "erc-7702-delegation": [
        r"\b7702\b.*delegation", r"\bSetCodeAuth\b", r"\bAuthority\b.*7702",
    ],
    "session-keys": [
        r"\bSessionKey\b", r"\bSessionKeyManager\b", r"\bsessionKeySig\b",
    ],
    "paymaster-verifying": [
        r"\bVerifyingPaymaster\b", r"\bBasePaymaster\b",
    ],
    "paymaster-erc20": [
        r"\bTokenPaymaster\b", r"\bERC20Paymaster\b",
    ],
    "social-recovery": [
        r"\bSocialRecovery\b", r"\bGuardianManager\b", r"\bRecoveryModule\b",
    ],
}

# Generic AA entry function names — strong signal independent of framework
ENTRY_FN_PATTERNS = [
    r"\b(function|fn|func)\s+validateUserOp\b",
    r"\b(function|fn|func)\s+_validateSignature\b",
    r"\b(function|fn|func)\s+_validateNonce\b",
    r"\b(function|fn|func)\s+validatePaymasterUserOp\b",
    r"\b(function|fn|func)\s+_validatePaymasterUserOp\b",
    r"\b(function|fn|func)\s+postOp\b",
    r"\b(function|fn|func)\s+_postOp\b",
    r"\b(function|fn|func)\s+executeUserOp\b",
    r"\b(function|fn|func)\s+execute\b.*UserOp",
    r"\b(function|fn|func)\s+isValidSignature\b",  # ERC-1271 — often AA
    r"\b(function|fn|func)\s+createAccount\b",
    r"\b(function|fn|func)\s+getAddress\b.*salt",   # factory counterfactual
    r"\b(function|fn|func)\s+_call\b.*EntryPoint",
    r"\b(function|fn|func)\s+handleOps\b",
    r"\b(function|fn|func)\s+handleAggregatedOps\b",
    r"\b(function|fn|func)\s+simulateValidation\b",
]

# Storage / state indicators of AA architecture
STORAGE_PATTERNS = [
    r"\bIEntryPoint\s+(public|internal|private)?\s*(immutable|constant)?\s*\w*entryPoint\b",
    r"\bentryPoint\s*\(\s*\)",
    r"\bnonce(s|Map)?\s*\[\s*address",   # nonce mapping per account
    r"\b_nonces\b",
    r"\bUserOperation\b",
    r"\bPackedUserOperation\b",
    r"\bUserOpHash\b|\buserOpHash\b",
    r"\bSIG_VALIDATION_FAILED\b",
    r"\bSIG_VALIDATION_SUCCESS\b",
    r"\bvalidationData\b",
    r"\bDEPOSIT_PAYMASTER\b|\bdeposits\s*\[\s*address",  # paymaster deposit map
    r"\bsponsoredOps\b|\bsponsorship\b",
    r"\bsessionKeys?\s*\[",
    r"\bguardians?\s*\[",
    r"\bIPaymaster\b",
    r"\bIAccount\b",
]

SOURCE_EXTS = {".sol", ".vy"}  # AA is EVM-centric; non-EVM AA forks rare enough to skip


def scan_file(path: Path) -> dict:
    """Returns dict {category: [match strings]} per file."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {}
    result = {"frameworks": set(), "entry_fns": [], "storage": []}
    for fw, patterns in FRAMEWORK_PATTERNS.items():
        for p in patterns:
            if re.search(p, text):
                result["frameworks"].add(fw)
                break
    for p in ENTRY_FN_PATTERNS:
        m = re.findall(p, text)
        if m:
            result["entry_fns"].extend([(path.name, str(m[:3]))])
            break
    for p in STORAGE_PATTERNS:
        if re.search(p, text):
            result["storage"].append((path.name, p))
    return result


def scan_target(source_dir: Path) -> dict:
    """Walk source_dir, accumulate evidence across all source files."""
    if not source_dir.is_dir():
        return {"frameworks": set(), "entry_fns": [], "storage": [], "scanned": 0}
    acc = {"frameworks": set(), "entry_fns": [], "storage": [], "scanned": 0}
    for f in source_dir.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in SOURCE_EXTS:
            continue
        parts = {p.lower() for p in f.parts}
        if parts & {"node_modules", "build", "out", "artifacts", "cache", ".git", "lib", "forge-cache"}:
            continue
        acc["scanned"] += 1
        r = scan_file(f)
        if r.get("frameworks"):
            acc["frameworks"].update(r["frameworks"])
        if r.get("entry_fns"):
            acc["entry_fns"].extend(r["entry_fns"])
        if r.get("storage"):
            acc["storage"].extend(r["storage"])
    return acc


def classify(evidence: dict) -> tuple[str, list[str]]:
    """Returns (verdict, tags_to_write).

    Verdict: STRONG | POSSIBLE | NONE
    Tags include: protocol_class:account-abstraction, erc4337, aa, smart-account, <framework>, possible-aa
    """
    fw = evidence["frameworks"]
    fns = evidence["entry_fns"]
    storage = evidence["storage"]

    categories_hit = sum([bool(fw), bool(fns), bool(storage)])

    if categories_hit >= 2:
        verdict = "STRONG"
        tags = ["protocol_class:account-abstraction", "erc4337", "aa", "smart-account", "account-abstraction"]
        for f in sorted(fw):
            tags.append(f)
            # Add specialized sub-class tags for routing precision
            if "paymaster" in f:
                tags.append("paymaster")
            if "session-keys" in f:
                tags.append("session-keys")
            if "social-recovery" in f:
                tags.append("social-recovery")
            if "7579" in f:
                tags.append("erc7579")
                tags.append("modular-account")
            if "7702" in f:
                tags.append("erc7702")
        return verdict, tags
    if categories_hit == 1:
        verdict = "POSSIBLE"
        tags = ["possible-aa"]
        if fw:
            tags.append("protocol_class:account-abstraction")
            tags.append("erc4337")
            tags.append("account-abstraction")
            for f in sorted(fw):
                tags.append(f)
        return verdict, tags
    return "NONE", []


def merge_tags(target: Path, new_tags: list[str], dry_run: bool) -> tuple[list[str], list[str]]:
    """Append new_tags to _tags.txt (idempotent). Returns (added, already_present)."""
    tags_txt = target / "_tags.txt"
    existing = set()
    if tags_txt.exists():
        for line in tags_txt.read_text(encoding="utf-8").splitlines():
            line = line.strip().lower()
            if line and not line.startswith("#"):
                existing.add(line)
    added = []
    present = []
    for t in new_tags:
        tl = t.strip().lower()
        if not tl:
            continue
        if tl in existing:
            present.append(t)
        else:
            added.append(t)
            existing.add(tl)
    if added and not dry_run:
        with tags_txt.open("a", encoding="utf-8") as f:
            if tags_txt.stat().st_size > 0:
                f.write("\n")
            f.write("# Added by aa_erc4337_classifier.py auto-classifier\n")
            for t in added:
                f.write(t + "\n")
    return added, present


def main():
    ap = argparse.ArgumentParser(description="Auto-classify target as ERC-4337 Account Abstraction class.")
    ap.add_argument("--target", required=True, help="Session directory (sessions/$T)")
    ap.add_argument("--source-path", help="Override source code path (default: read from chain.json)")
    ap.add_argument("--dry-run", action="store_true", help="Report only, don't write _tags.txt")
    args = ap.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"ERROR: target dir not found: {target}", file=sys.stderr)
        sys.exit(2)

    source_path = None
    if args.source_path:
        source_path = Path(args.source_path)
    else:
        cj = target / "chain.json"
        if cj.exists():
            try:
                data = json.loads(cj.read_text(encoding="utf-8"))
                sp = data.get("source_path")
                if sp:
                    source_path = Path(sp)
            except Exception:
                pass
    if not source_path or not source_path.is_dir():
        print(f"ERROR: no source path. Pass --source-path or set chain.json.source_path", file=sys.stderr)
        sys.exit(2)

    print(f"[*] Scanning {source_path} for ERC-4337 signatures...")
    evidence = scan_target(source_path)
    print(f"    Files scanned: {evidence['scanned']}")
    print(f"    Frameworks found: {sorted(evidence['frameworks']) or 'none'}")
    print(f"    Entry functions: {len(evidence['entry_fns'])} hits")
    print(f"    Storage patterns: {len(evidence['storage'])} hits")

    verdict, tags = classify(evidence)
    print(f"\n[*] Verdict: {verdict}")

    if verdict == "NONE":
        print("    Not an ERC-4337 / AA target. No tags written.")
        sys.exit(0)

    print(f"    Tags to apply: {tags}")
    added, present = merge_tags(target, tags, args.dry_run)
    if args.dry_run:
        print(f"\n[DRY RUN] Would add: {added}")
        print(f"          Already present: {present}")
    else:
        print(f"\n[+] Added to {target}/_tags.txt: {added}")
        if present:
            print(f"    (already present, skipped: {present})")

    print(f"\nNext:")
    print(f"  py -3 -X utf8 scripts/web3/threat_models/apply.py --target {target}")
    print(f"  py -3 scripts/web3/specialized/aa_erc4337_hunter.py --source {source_path}")
    if verdict == "STRONG":
        print(f"  → erc4337_signature_replay.yaml should match → 6 hypotheses + 5 executable checks")
    else:
        print(f"  → POSSIBLE-aa — review evidence manually, may be non-AA contract using IEntryPoint indirectly")

    print(f"\nRelated artifacts:")
    print(f"  - scripts/web3/_target_routing.md (multi-class routing decisions)")
    print(f"  - scripts/web3/checklists/specialized/aa_erc4337.md (manual review)")
    print(f"  - scripts/web3/threat_models/erc4337_signature_replay.yaml (auto-applied)")


if __name__ == "__main__":
    main()
