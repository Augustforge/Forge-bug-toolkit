#!/usr/bin/env python3
"""
bridge_detector.py — Auto-classifier for bridge / attested-payload targets.

Scans target source code for bridge framework imports + entry function names +
storage layout signatures. If confident → writes `protocol_class:bridge` +
framework tags to `_tags.txt`. This unlocks auto-matching of:
  - threat_models/cross_chain_source_destination_binding.yaml
  - threat_models/attested_amount_trust_gap.yaml
  - checklists/specialized/bridge.md
  - prompts/bridge_message_forge.md
  - bridge_tests/source_amount_grep.sh

Replaces manual `_tags.txt` authoring for bridge class. Without this, apply.py
does not match bridge TMs if you forgot to tag.

Usage:
  py -3 bridge_detector.py --target sessions/$T --source-path $REPO
  py -3 bridge_detector.py --target sessions/$T              # uses chain.json source_path
  py -3 bridge_detector.py --target sessions/$T --dry-run    # report only, no write

Idempotent — safe to re-run. Won't duplicate existing tags.

Confidence levels:
  STRONG   — 2+ evidence categories (framework + entry function OR storage)
  POSSIBLE — 1 evidence category — writes "possible-bridge" tag, requires manual review
  NONE     — no match, exits cleanly
"""
import argparse
import json
import re
import sys
from pathlib import Path


# Framework signature → tag mapping
FRAMEWORK_PATTERNS = {
    "wormhole": [
        r"\bIWormhole\b", r"\bcompleteTransfer\w*\b", r"\bVAA\b",
        r"\bpublishMessage\b", r"\bguardian_set\b", r"\bguardianSet\b",
        r"\bsignature_set\b", r"\bsignatureSet\b", r"\bpostVAA\b",
    ],
    "layerzero": [
        r"\bILayerZero\w*\b", r"\bLZAppV2?\b", r"\bOAppCore\b",
        r"\bEndpointV2\b", r"\b_lzReceive\b", r"\b_lzSend\b",
        r"\brequiredDVNCount\b", r"\bUlnConfig\b",
    ],
    "axelar": [
        r"\bIAxelar\w*\b", r"\bAxelarExecutable\b", r"\bcallContract\b",
        r"\bvalidateContractCall\b",
    ],
    "ccip": [
        r"\bITokenMessenger\b", r"\battestationService\b",
        r"\bMessageTransmitter\b", r"\bICCIPRouter\b", r"\bIRouter\b.*ccip",
    ],
    "connext": [r"\bIConnext\b", r"\bxcall\b.*Connext", r"\bConnextHandler\b"],
    "hyperlane": [r"\bIMailbox\b.*Hyperlane", r"\bHyperlaneMessage\b"],
    "across": [r"\bSpokePool\b", r"\bHubPool\b", r"\bAcrossDepositor\b"],
    "stargate": [r"\bIStargate\w*\b", r"\bIStargateRouter\b", r"\bIStargateReceiver\b"],
    "synapse": [r"\bISynapseBridge\b", r"\bnUSD\b"],
    "thorchain-tss": [r"\btss-lib\b", r"\bPaillierSK\b", r"\bGG20\b", r"\bdlnproof\b"],
    "pbaas": [r"\bcheckCCEValues\b", r"\bCCE\b.*Verus", r"\bCrossChainExport\b"],
    "ibc-custom": [r"\bIBCPacket\b", r"\brecvPacket\b", r"\bIBCApp\b"],
    "polkadot-xcm": [r"\bXCMMessage\b", r"\bParachainBridge\b"],
    "gravity-cosmos": [
        r"\bsubmitBatch\b", r"\bupdateValset\b", r"\bupdateValsetAndSubmitBatch\b",
        r"\bcheckValidatorSignatures\b", r"\bmakeCheckpoint\b", r"\b_makeCheckpoint\b",
        r"\bstate_lastValsetNonce\b", r"\bstate_powerThreshold\b", r"\blogicCall\b",
    ],
}

# Generic bridge entry function names (any chain)
ENTRY_FN_PATTERNS = [
    r"\b(function|fn|func)\s+submitImports\b",
    r"\b(function|fn|func)\s+receiveMessage\b",
    r"\b(function|fn|func)\s+claimMessage\b",
    r"\b(function|fn|func)\s+relayMessage\b",
    r"\b(function|fn|func)\s+completeTransfer\w*\b",
    r"\b(function|fn|func)\s+process\b",
    r"\b(function|fn|func)\s+executeMessage\b",
    r"\b(function|fn|func)\s+deliver\b",
    r"\b(function|fn|func)\s+finalizeTransfer\b",
    r"\b(function|fn|func)\s+redeem\b.*proof",
    r"\b(function|fn|func)\s+unlock\b.*sig",
    r"\b(function|fn|func)\s+mintWithProof\b",
    # Go/Rust capitalised conventions
    r"\bfunc\s+\(\w+\s+\*?\w+\)\s+(SubmitImports|ReceiveMessage|ClaimMessage|CompleteTransfer|Process|ExecuteMessage|Deliver|FinalizeTransfer)\b",
    r"\bpub\s+fn\s+(submit_imports|receive_message|claim_message|complete_transfer|process_msg|execute_message|deliver|finalize_transfer)\b",
    # Gravity / M-of-N validator-set bridges
    r"\b(function|fn|func)\s+submitBatch\b",
    r"\b(function|fn|func)\s+updateValset\w*\b",
]

# Storage/state indicators of attested-payload bridge
STORAGE_PATTERNS = [
    r"\b(notary_set|notarySet|notaries)\b",
    r"\b(guardian_set|guardianSet|guardians)\b",
    r"\b(signature_set|signatureSet|sigSet)\b",
    r"\bvalidators\s*\[\s*\d*\s*\]",   # validators array
    r"\bmerkleRoot\b.*public",
    r"\bconsumedVAAs?\b",
    r"\bconfirmedMessages\b",
    r"\bnonceUsed\b",
    r"\b(state_lastValsetNonce|state_lastValsetCheckpoint|state_powerThreshold)\b",
    r"\bvalsetNonce\b",
]

SOURCE_EXTS = {".sol", ".vy", ".go", ".rs", ".move"}


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
            break  # one hit per file enough
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
        # Skip vendored deps / node_modules / build outputs
        parts = {p.lower() for p in f.parts}
        if parts & {"node_modules", "build", "out", "artifacts", "cache", ".git"}:
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
    Tags include: protocol_class:bridge, bridge, attested-payload, <framework>, possible-bridge
    """
    fw = evidence["frameworks"]
    fns = evidence["entry_fns"]
    storage = evidence["storage"]

    categories_hit = sum([bool(fw), bool(fns), bool(storage)])

    if categories_hit >= 2:
        verdict = "STRONG"
        tags = ["protocol_class:bridge", "bridge", "attested-payload", "cross-chain", "custody"]
        for f in sorted(fw):
            tags.append(f)
        return verdict, tags
    if categories_hit == 1:
        verdict = "POSSIBLE"
        tags = ["possible-bridge"]
        if fw:
            tags.append("protocol_class:bridge")
            tags.append("bridge")
            tags.append("attested-payload")
            tags.append("custody")
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
            f.write("# Added by bridge_detector.py auto-classifier\n")
            for t in added:
                f.write(t + "\n")
    return added, present


def main():
    ap = argparse.ArgumentParser(description="Auto-classify target as bridge / attested-payload class.")
    ap.add_argument("--target", required=True, help="Session directory (sessions/$T)")
    ap.add_argument("--source-path", help="Override source code path (default: read from chain.json)")
    ap.add_argument("--dry-run", action="store_true", help="Report only, don't write _tags.txt")
    args = ap.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"ERROR: target dir not found: {target}", file=sys.stderr)
        sys.exit(2)

    # Source path: CLI override or from chain.json
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

    print(f"[*] Scanning {source_path} for bridge signatures...")
    evidence = scan_target(source_path)
    print(f"    Files scanned: {evidence['scanned']}")
    print(f"    Frameworks found: {sorted(evidence['frameworks']) or 'none'}")
    print(f"    Entry functions: {len(evidence['entry_fns'])} hits")
    print(f"    Storage patterns: {len(evidence['storage'])} hits")

    verdict, tags = classify(evidence)
    print(f"\n[*] Verdict: {verdict}")

    if verdict == "NONE":
        print("    Not a bridge. No tags written.")
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

    # Suggest next steps
    print(f"\nNext:")
    print(f"  py -3 -X utf8 scripts/web3/threat_models/apply.py --target {target}")
    print(f"  bash scripts/web3/bridge_tests/source_amount_grep.sh {source_path} {target}")
    if verdict == "STRONG":
        print(f"  → 2 threat models should match: cross_chain_source_destination_binding + attested_amount_trust_gap")
    else:
        print(f"  → POSSIBLE-bridge — review evidence manually, escalate if confirmed")

    # Cross-link
    print(f"\nRelated artifacts:")
    print(f"  - scripts/web3/_target_routing.md (routing decisions)")
    print(f"  - scripts/web3/checklists/specialized/bridge.md (manual review checklist)")
    print(f"  - scripts/web3/prompts/bridge_message_forge.md (adversarial lens)")


if __name__ == "__main__":
    main()
