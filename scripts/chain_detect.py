#!/usr/bin/env python3
"""
chain_detect.py — Unified chain router for /hunt and /deephunt.

Single source of truth: receive target (address / repo path / hotlist entry),
detect chain, output canonical JSON. Both skills consume the same output.

Detection sources:
- Address prefix: eth:/sol:/eclipse:/etc.
- Repo content: *.sol → EVM, Anchor.toml/Cargo.toml(solana_program) → Solana
- Domain → web2
- Hotlist entry with `chain` field

Usage:
  python3 chain_detect.py --target eth:0x1234...
  python3 chain_detect.py --target sol:9xQeWv...
  python3 chain_detect.py --target ./my-anchor-repo/
  python3 chain_detect.py --target example.com
  python3 chain_detect.py --hotlist-entry sessions/_proactive/hotlist.json:0
"""
import argparse
import json
import re
import sys
from pathlib import Path


EVM_PREFIXES = {
    "eth", "ethereum", "bsc", "binance", "polygon", "matic", "arbitrum", "arb",
    "optimism", "op", "base", "avalanche", "avax", "fantom", "ftm", "celo",
    "gnosis", "xdai", "moonbeam", "linea", "scroll", "zksync", "mantle",
    "blast", "monad", "berachain", "hyperevm", "sonic-evm",
}
SOLANA_PREFIXES = {
    "sol", "solana",
    # SVM derivatives — routed to sol branch
    "eclipse", "sonic", "soon", "magicblock",
}
MOVE_PREFIXES = {
    "move", "sui", "aptos",
}
TON_PREFIXES = {
    "ton", "toncoin",
}
STACKS_PREFIXES = {
    "stacks", "clarity", "stx",
}

# TON smart-contract source extensions (FunC / Tact / Tolk / Fift / TL-B).
TON_CONTRACT_EXTS = (".fc", ".func", ".tact", ".tolk", ".fift", ".tlb")
# TON C++ node-core marker dirs (see scripts/ton/scan.sh — catchain/validator/tonlib/adnl focus).
# Require >=2 to avoid matching arbitrary C++ repos.
TON_NODE_DIRS = ("catchain", "validator-session", "tonlib", "adnl", "validator")

TON_TOOL = "scripts/ton/scan.sh"


def detect_from_address(target: str) -> dict | None:
    """Detect chain from explicit prefix like 'eth:0x...'  or 'sol:9xQe...'."""
    if ":" not in target:
        return None
    prefix, addr = target.split(":", 1)
    prefix = prefix.lower().strip()
    addr = addr.strip()

    if prefix in EVM_PREFIXES:
        return {
            "chain": "evm",
            "subchain": prefix,
            "primary_address": addr,
            "framework": None,
            "source_available": None,
            "verified": None,
        }
    if prefix in SOLANA_PREFIXES:
        return {
            "chain": "solana",
            "subchain": prefix,
            "primary_address": addr,
            "framework": "anchor_or_native",
            "source_available": None,
            "verified": None,
        }
    if prefix in MOVE_PREFIXES:
        return {
            "chain": "move",
            "subchain": prefix if prefix in ("sui", "aptos") else None,
            "primary_address": addr,
            "framework": "move",
            "source_available": None,
            "verified": None,
        }
    if prefix in TON_PREFIXES:
        return {
            "chain": "ton",
            "subchain": None,
            "primary_address": addr,
            "framework": None,
            "source_available": None,
            "verified": None,
        }
    if prefix in STACKS_PREFIXES:
        return {
            "chain": "stacks",
            "subchain": None,
            "primary_address": addr,
            "framework": "clarity",
            "source_available": None,
            "verified": None,
        }
    return None


def detect_from_repo(path: Path) -> dict | None:
    """Detect chain from repo content."""
    if not path.is_dir():
        return None

    has_sol_files = any(path.rglob("*.sol"))
    has_anchor_toml = (path / "Anchor.toml").exists() or any(path.rglob("Anchor.toml"))
    has_cargo_toml = (path / "Cargo.toml").exists() or any(path.rglob("Cargo.toml"))

    if has_anchor_toml:
        return {
            "chain": "solana",
            "subchain": "solana",
            "primary_address": None,
            "framework": "anchor",
            "source_available": True,
            "source_path": str(path),
            "verified": True,
        }

    if has_cargo_toml:
        for cargo in path.rglob("Cargo.toml"):
            try:
                content = cargo.read_text(encoding="utf-8", errors="ignore")
                if "solana_program" in content or "anchor_lang" in content or "anchor-lang" in content:
                    framework = "anchor" if "anchor" in content else "native_solana"
                    return {
                        "chain": "solana",
                        "subchain": "solana",
                        "primary_address": None,
                        "framework": framework,
                        "source_available": True,
                        "source_path": str(path),
                        "verified": True,
                    }
            except Exception:
                continue

    # Move / Sui / Aptos — Move.toml is the manifest; .move is the source.
    # Checked before package.json because Sui dApps often ship a frontend package.json.
    has_move_toml = (path / "Move.toml").exists() or any(path.rglob("Move.toml"))
    has_move_files = any(path.rglob("*.move"))
    if has_move_toml or has_move_files:
        subchain = None
        for mt in path.rglob("Move.toml"):
            try:
                c = mt.read_text(encoding="utf-8", errors="ignore")
                if re.search(r"\bSui\b|sui-framework|MystenLabs", c):
                    subchain = "sui"
                elif re.search(r"AptosFramework|aptos-core|\bAptos\b", c):
                    subchain = "aptos"
                if subchain:
                    break
            except Exception:
                continue
        return {
            "chain": "move",
            "subchain": subchain,
            "primary_address": None,
            "framework": "move",
            "source_available": True,
            "source_path": str(path),
            "verified": True,
        }

    # TON — checked before .sol/package.json (TON dApps/blueprint projects ship a frontend
    # package.json; some vendor .sol interfaces). Two surfaces: FunC/Tact/Tolk CONTRACTS (no
    # dedicated engine yet — manual hypothesis-driven + blueprint/sandbox PoC) vs C++ NODE core
    # (routed to scripts/ton/scan.sh). Contract files take priority when both look present.
    ton_contract_ext = None
    for ext in TON_CONTRACT_EXTS:
        if any(path.rglob("*" + ext)):
            ton_contract_ext = ext
            break
    if ton_contract_ext:
        fw = {".fc": "func", ".func": "func", ".tact": "tact",
              ".tolk": "tolk", ".fift": "fift", ".tlb": "tlb"}.get(ton_contract_ext, "func")
        return {
            "chain": "ton",
            "subchain": "contract",
            "primary_address": None,
            "framework": fw,
            "source_available": True,
            "source_path": str(path),
            "verified": True,
            "ton_note": (
                "TON smart-contract target (%s). NO dedicated contract engine — hunt manually, "
                "hypothesis-driven per methodology (T10 model-first is chain-agnostic). PoC via "
                "@ton/blueprint + @ton/sandbox. Seed TON-contract invariants (tx sender/bounce/"
                "message-value/carry-value) into system_model.md." % fw),
        }

    # TON C++ node core — require >=2 marker dirs to avoid matching arbitrary C++ repos.
    ton_node_hits = [d for d in TON_NODE_DIRS if any(p.is_dir() and p.name == d for p in path.rglob(d))]
    if len(ton_node_hits) >= 2:
        return {
            "chain": "ton",
            "subchain": "node",
            "primary_address": None,
            "framework": "cpp",
            "source_available": True,
            "source_path": str(path),
            "verified": True,
            "ton_tool": TON_TOOL,
            "ton_note": (
                "TON C++ node core (markers: %s) — use scripts/ton/scan.sh (cppcheck + "
                "semgrep_ton.yaml over catchain/validator/crypto/tonlib/adnl), then verify each "
                "finding manually." % ", ".join(sorted(ton_node_hits))),
        }

    # Stacks / Clarity — .clar source or Clarinet.toml manifest. No dedicated engine (manual
    # hypothesis-driven; PoC via Clarinet simnet). Checked before .sol/package.json (Stacks dApps
    # ship a frontend package.json; Clarinet projects may vendor interfaces).
    has_clarity = any(path.rglob("*.clar")) or (path / "Clarinet.toml").exists() or any(path.rglob("Clarinet.toml"))
    if has_clarity:
        return {
            "chain": "stacks",
            "subchain": "contract",
            "primary_address": None,
            "framework": "clarity",
            "source_available": True,
            "source_path": str(path),
            "verified": True,
            "clarity_note": (
                "Stacks/Clarity smart-contract target. NO dedicated engine — hunt manually, "
                "hypothesis-driven (T10 model-first is chain-agnostic). PoC via Clarinet simnet "
                "(clarinet test). Seed Clarity invariants (tx-sender/contract-caller confusion, "
                "post-conditions, unwrap/response-handling, trait dispatch allowlist, abort-model "
                "arithmetic) into system_model.md — see methodology/invariant_library.md § Clarity."),
        }

    if has_sol_files:
        framework = None
        if (path / "foundry.toml").exists():
            framework = "foundry"
        elif (path / "hardhat.config.js").exists() or (path / "hardhat.config.ts").exists():
            framework = "hardhat"
        return {
            "chain": "evm",
            "subchain": "evm",
            "primary_address": None,
            "framework": framework,
            "source_available": True,
            "source_path": str(path),
            "verified": True,
        }

    has_package_json = (path / "package.json").exists()
    if has_package_json:
        return {
            "chain": "web2",
            "primary_address": None,
            "framework": "node",
            "source_available": True,
            "source_path": str(path),
            "verified": True,
        }

    return None


# --- Kwil / KGW fingerprint -------------------------------------------------
# When a target is a Kwil node (kwild, usually "mode":"open" behind a KGW gateway)
# the raw black-box tester applies. See scripts/web3/kwil/kwil_blackbox.py.
KWIL_TOOL = "scripts/web3/kwil/kwil_blackbox.py"
_KWIL_SCHEMA_RE = re.compile(
    r"@caller|\baction\s+\w+\s*\([^)]*\)\s*(public|private|owner|view)|kuneiform|kwilteam/kwil-db|trufnetwork/kwil-db|kwild",
    re.IGNORECASE)


def kwil_fingerprint(path: Path) -> bool:
    """True if a cloned repo looks like a Kwil database/extension target."""
    if not path.is_dir():
        return False
    if any(path.rglob("*.kf")):                       # Kuneiform schema
        return True
    for cand in list(path.rglob("schema.sql"))[:8] + list(path.rglob("go.mod"))[:8]:
        try:
            if _KWIL_SCHEMA_RE.search(cand.read_text(encoding="utf-8", errors="ignore")):
                return True
        except Exception:
            continue
    return False


DOMAIN_RE = re.compile(r"^([a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$", re.IGNORECASE)


def detect_from_domain(target: str) -> dict | None:
    if "://" in target:
        target = target.split("://", 1)[1].split("/", 1)[0]
    if DOMAIN_RE.match(target):
        return {
            "chain": "web2",
            "primary_address": None,
            "domain": target,
            "framework": None,
            "source_available": False,
            "verified": None,
        }
    return None


def detect_from_hotlist(spec: str) -> dict | None:
    """spec format: path/to/hotlist.json:INDEX"""
    if ":" not in spec:
        return None
    path_str, idx_str = spec.rsplit(":", 1)
    path = Path(path_str)
    if not path.exists():
        return None
    try:
        idx = int(idx_str)
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list) and 0 <= idx < len(data):
            entry = data[idx]
            chain = entry.get("chain", "").lower()
            if chain in ("evm", "eth", "ethereum"):
                chain = "evm"
            elif chain in ("sol", "solana"):
                chain = "solana"
            else:
                chain = chain or "unknown"
            return {
                "chain": chain,
                "primary_address": entry.get("address"),
                "framework": entry.get("framework"),
                "source_available": entry.get("source_available"),
                "verified": entry.get("verified"),
                "from_hotlist": True,
                "hotlist_entry": entry,
            }
    except Exception:
        pass
    return None


def detect(target: str) -> dict:
    """Main entry point — returns canonical chain detection dict."""
    target = target.strip()

    addr_result = detect_from_address(target)
    if addr_result:
        return addr_result

    repo_result = detect_from_repo(Path(target))
    if repo_result:
        # Kwil node/extension repos look like web2/Go but have their own black-box surface.
        if kwil_fingerprint(Path(target)):
            repo_result["kwil_target"] = True
            repo_result["kwil_tool"] = KWIL_TOOL
            repo_result["kwil_note"] = (
                "Kwil/KGW target — use kwil_blackbox.py: raw read-call IDOR probe + "
                "KGW SIWE auth + write-tx error-oracle (OWNER/PRIVATE/precompile enforcement). "
                "kwild 'mode':open + no per-account gateway binding = @caller IDOR on all VIEWs.")
        return repo_result

    # Pure Kuneiform/schema repo (no package.json/.sol/Cargo) — caught before "unknown".
    tp = Path(target)
    if tp.is_dir() and kwil_fingerprint(tp):
        return {
            "chain": "web2",
            "primary_address": None,
            "framework": "kwil",
            "source_available": True,
            "source_path": str(tp),
            "verified": True,
            "kwil_target": True,
            "kwil_tool": KWIL_TOOL,
            "kwil_note": (
                "Kwil/KGW schema target — use kwil_blackbox.py (read-call IDOR probe + "
                "KGW SIWE auth + write-tx error-oracle for OWNER/PRIVATE/precompile enforcement)."),
        }

    domain_result = detect_from_domain(target)
    if domain_result:
        host = domain_result.get("domain", "")
        # Soft hint: idOS-style node gateways. Confirm by probing kgw.authn_param.
        if re.search(r"(^|\.)(nodes?|gateway|kgw|kwil)\.", host) or "kwil" in host:
            domain_result["kwil_maybe"] = True
            domain_result["kwil_tool"] = KWIL_TOOL
            domain_result["kwil_note"] = (
                "Host name hints a Kwil/KGW node gateway. Probe `kgw.authn_param` at "
                "/rpc/v1; if it answers, use kwil_blackbox.py.")
        return domain_result

    return {
        "chain": "unknown",
        "primary_address": target,
        "framework": None,
        "source_available": None,
        "verified": None,
        "error": "Could not detect chain. Use explicit prefix (eth:0x.../sol:...) or valid repo path.",
    }


def main():
    ap = argparse.ArgumentParser(description="Detect target chain (EVM / Solana / Move[Sui/Aptos] / TON / Web2 / cross-chain)")
    ap.add_argument("--target", help="Address with prefix, repo path, or domain")
    ap.add_argument("--hotlist-entry", help="Spec: path/to/hotlist.json:INDEX")
    ap.add_argument("--output", default=None, help="Write JSON to this path (else stdout)")
    args = ap.parse_args()

    if not (args.target or args.hotlist_entry):
        print("[!] Provide --target or --hotlist-entry", file=sys.stderr)
        sys.exit(1)

    if args.hotlist_entry:
        result = detect_from_hotlist(args.hotlist_entry)
        if not result:
            print(f"[!] Could not load hotlist entry: {args.hotlist_entry}", file=sys.stderr)
            sys.exit(2)
    else:
        result = detect(args.target)

    output = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"[+] Written to {args.output}")
    else:
        print(output)

    if result.get("chain") == "unknown":
        sys.exit(3)


if __name__ == "__main__":
    main()
