#!/usr/bin/env python3
"""anchor_idl_diff.py — diff on-chain IDL vs source IDL for IDL takeover detection.

Anchor's IDL can be claimed permissionlessly via `IdlCreateAccount`. Attacker
uploads a modified IDL (extra instruction discriminators, fake args, redirected accounts),
users' frontend follows the malicious IDL -> phishing/drain.

This script:
1. Fetch IDL from on-chain (via `anchor idl fetch <PROGRAM_ID>`)
2. Compare with source IDL (target/idl/program.json in repo)
3. Flag differences:
   - extra instructions (added by attacker)
   - changed instruction args (e.g., recipient swapped)
   - changed account constraints
   - discriminator mismatches

Usage:
    python3 anchor_idl_diff.py --program-id 9xQeWv... --source-idl target/idl/protocol.json
    python3 anchor_idl_diff.py --program-id 9xQeWv... --source-idl target/idl/protocol.json --rpc https://api.mainnet-beta.solana.com
"""
import argparse, json, subprocess, sys, tempfile
from pathlib import Path


def fetch_onchain_idl(program_id: str, rpc: str) -> dict | None:
    try:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmp_path = f.name
        result = subprocess.run(
            ["anchor", "idl", "fetch", program_id, "--out", tmp_path, "--provider.cluster", rpc],
            capture_output=True, timeout=30,
        )
        if result.returncode != 0:
            print(f"[!] anchor idl fetch failed: {result.stderr.decode()}", file=sys.stderr)
            return None
        return json.loads(Path(tmp_path).read_text())
    except FileNotFoundError:
        print("[!] anchor CLI not installed", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[!] fetch error: {e}", file=sys.stderr)
        return None


def diff_idls(source: dict, onchain: dict) -> dict:
    findings = []
    source_ix = {ix["name"]: ix for ix in source.get("instructions", [])}
    onchain_ix = {ix["name"]: ix for ix in onchain.get("instructions", [])}

    for name in onchain_ix:
        if name not in source_ix:
            findings.append({
                "type": "extra_instruction",
                "severity": "critical",
                "classification": "novel_instance",
                "instruction": name,
                "description": f"On-chain IDL has instruction '{name}' not present in source. POSSIBLE IDL TAKEOVER.",
                "details": onchain_ix[name],
            })

    for name in source_ix:
        if name not in onchain_ix:
            findings.append({
                "type": "missing_instruction",
                "severity": "medium",
                "classification": "known_class",
                "instruction": name,
                "description": f"Source has instruction '{name}' not exposed in on-chain IDL.",
            })

    for name in source_ix.keys() & onchain_ix.keys():
        src_args = source_ix[name].get("args", [])
        on_args = onchain_ix[name].get("args", [])
        if src_args != on_args:
            findings.append({
                "type": "args_mismatch",
                "severity": "high",
                "classification": "novel_instance",
                "instruction": name,
                "description": f"Instruction '{name}' args differ. Possible arg swap attack (e.g., recipient/sender flip).",
                "source_args": src_args,
                "onchain_args": on_args,
            })

        src_accounts = source_ix[name].get("accounts", [])
        on_accounts = onchain_ix[name].get("accounts", [])
        if src_accounts != on_accounts:
            findings.append({
                "type": "accounts_mismatch",
                "severity": "high",
                "classification": "novel_instance",
                "instruction": name,
                "description": f"Instruction '{name}' accounts list differs. Possible account substitution.",
                "source_accounts": [a.get("name") for a in src_accounts],
                "onchain_accounts": [a.get("name") for a in on_accounts],
            })

        src_disc = source_ix[name].get("discriminator")
        on_disc = onchain_ix[name].get("discriminator")
        if src_disc and on_disc and src_disc != on_disc:
            findings.append({
                "type": "discriminator_mismatch",
                "severity": "critical",
                "classification": "novel_instance",
                "instruction": name,
                "description": f"Instruction '{name}' discriminator differs. Calls to source's discriminator may invoke different on-chain logic.",
                "source_disc": src_disc,
                "onchain_disc": on_disc,
            })

    src_accounts = {a["name"]: a for a in source.get("accounts", [])}
    on_accounts = {a["name"]: a for a in onchain.get("accounts", [])}
    for name in on_accounts:
        if name not in src_accounts:
            findings.append({
                "type": "extra_account_type",
                "severity": "medium",
                "classification": "novel_instance",
                "account": name,
                "description": f"On-chain IDL declares account type '{name}' not in source.",
            })

    return {"total": len(findings), "findings": findings}


def main():
    ap = argparse.ArgumentParser(description="Diff on-chain Anchor IDL vs source IDL")
    ap.add_argument("--program-id", required=True)
    ap.add_argument("--source-idl", required=True, help="Path to source IDL JSON (e.g., target/idl/program.json)")
    ap.add_argument("--rpc", default="https://api.mainnet-beta.solana.com")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    source_path = Path(args.source_idl)
    if not source_path.exists():
        print(f"[!] source IDL not found: {source_path}", file=sys.stderr)
        sys.exit(1)
    source = json.loads(source_path.read_text())

    print(f"[*] Fetching on-chain IDL for {args.program_id}...")
    onchain = fetch_onchain_idl(args.program_id, args.rpc)
    if onchain is None:
        print(f"[!] Could not fetch on-chain IDL. Program may not have claimed IDL authority — that itself is a finding (IDL takeover surface).")
        result = {
            "total": 1,
            "findings": [{
                "type": "no_onchain_idl",
                "severity": "high",
                "classification": "known_class",
                "description": "On-chain IDL not found — IdlCreateAccount may not have been called. Attacker can claim IDL authority.",
            }],
        }
    else:
        result = diff_idls(source, onchain)

    print(f"\n[+] Diff complete: {result['total']} findings")
    for f in result["findings"]:
        sev = f["severity"].upper()
        cls = f["classification"]
        print(f"  [{sev}] [{cls}] {f['type']}: {f['description']}")

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2))
        print(f"\n[+] Saved to {out}")


if __name__ == "__main__":
    main()
