#!/usr/bin/env python3
"""
composability_matrix.py — Map external protocol dependencies.

Long-undiscovered bugs often live at the SEAM between protocols:
- Protocol A reads from B.
- B can be manipulated (cheaply via flash loan, or specific market condition).
- A breaks even though A's own code is "fine".

Real example: Cream Finance relied on Curve LP price → Curve had TWAP windowing
issue → Cream became drainable.

This script extracts:
- All `address` immutables / state vars that point to external protocols
- All external `call` / `interface call` patterns
- Builds an interaction graph

Usage:
  python3 composability_matrix.py --target path/to/Contract.sol --output sessions/X/hypothesis/

Output: composability_matrix.json + composability_matrix.md
"""

import argparse
import json
import re
from pathlib import Path

# External call patterns
INTERFACE_CALL_RE = re.compile(
    r"(?:I[A-Z]\w*|[A-Z]\w*Interface)\((\w+)\)\.(\w+)\s*\(",
)

# Address-typed state variables
ADDRESS_VAR_RE = re.compile(
    r"\baddress\s+(?:public\s+|private\s+|internal\s+|immutable\s+|constant\s+)*(\w+)\s*[=;]",
)

# Interface imports
IMPORT_RE = re.compile(r'import\s+["\']([^"\']+)["\']')

# Known external protocols (heuristic — extend as needed)
KNOWN_PROTOCOLS = {
    "uniswap": ["UniswapV2", "UniswapV3", "IUniswap", "ISwapRouter", "INonfungiblePositionManager"],
    "curve": ["Curve", "ICurve", "ICRVPool", "IPlainPool", "IStableSwap"],
    "balancer": ["Balancer", "IVault", "IBalancer", "IWeightedPool"],
    "aave": ["Aave", "IAave", "ILendingPool", "IPool", "IFlashLoanReceiver"],
    "compound": ["Compound", "IComptroller", "ICToken", "ICompoundV3"],
    "chainlink": ["Chainlink", "AggregatorV3", "FeedRegistry", "VRFCoordinator"],
    "lido": ["Lido", "stETH", "wstETH", "ILido"],
    "rocketpool": ["RocketPool", "rETH", "IRocket"],
    "frax": ["FRAX", "frxETH", "sfrxETH", "IFrax"],
    "makerdao": ["MakerDAO", "DSS", "Maker", "IVat"],
    "yearn": ["Yearn", "IYearn", "IVault"],
    "layerzero": ["LayerZero", "ILayerZero", "IEndpoint", "ILzEndpoint"],
    "wormhole": ["Wormhole", "IWormhole", "ITokenBridge"],
    "axelar": ["Axelar", "IAxelar"],
    "ccip": ["CCIP", "IRouterClient"],
    "permit2": ["Permit2", "ISignatureTransfer", "IAllowanceTransfer"],
    "weth": ["WETH", "IWETH", "IWETH9"],
    "tokens": ["IERC20", "IERC721", "IERC1155", "IERC4626"],
}


def detect_protocol(interface_name: str) -> str:
    """Classify an interface name to a known protocol."""
    iname = interface_name.lower()
    for protocol, patterns in KNOWN_PROTOCOLS.items():
        for pat in patterns:
            if pat.lower() in iname:
                return protocol
    return "unknown"


def extract_external_calls(source: str) -> list[dict]:
    """Find all `IInterface(addr).method(...)` patterns."""
    calls = []
    for m in INTERFACE_CALL_RE.finditer(source):
        # Get interface name from full match
        full_match = source[m.start() : m.end()]
        interface_match = re.match(r"(\w+)", full_match)
        interface_name = interface_match.group(1) if interface_match else ""
        addr_var = m.group(1)
        method = m.group(2)
        line = source[: m.start()].count("\n") + 1
        protocol = detect_protocol(interface_name)
        calls.append({
            "interface": interface_name,
            "address_var": addr_var,
            "method": method,
            "protocol": protocol,
            "line": line,
        })
    return calls


def extract_address_vars(source: str) -> list[dict]:
    """Find all address state variables."""
    vars_ = []
    for m in ADDRESS_VAR_RE.finditer(source):
        name = m.group(1)
        line = source[: m.start()].count("\n") + 1
        vars_.append({"name": name, "line": line})
    return vars_


def analyze_dependencies(calls: list[dict]) -> dict:
    """Build dependency summary."""
    by_protocol: dict[str, list[dict]] = {}
    for c in calls:
        by_protocol.setdefault(c["protocol"], []).append(c)

    # Risk scores per protocol
    PROTOCOL_RISK = {
        "uniswap": {"twap_manip": "high", "flash_loan": "high"},
        "curve": {"readonly_reentrancy": "critical", "twap_manip": "high"},
        "balancer": {"readonly_reentrancy": "high", "flash_loan": "high"},
        "aave": {"flash_loan_source": "high", "liquidation_MEV": "medium"},
        "compound": {"liquidation_MEV": "medium"},
        "chainlink": {"stale_price": "medium", "sequencer_downtime": "medium"},
        "lido": {"depeg": "high", "withdrawal_queue": "medium"},
        "rocketpool": {"depeg": "medium"},
        "frax": {"depeg": "high"},
        "layerzero": {"dvn_compromise": "critical", "replay": "high"},
        "wormhole": {"replay": "high", "guardian_compromise": "critical"},
        "permit2": {"witness_binding": "high"},
    }

    risks = {}
    for protocol, protocol_calls in by_protocol.items():
        if protocol == "unknown" or protocol == "tokens":
            continue
        risks[protocol] = {
            "calls_count": len(protocol_calls),
            "methods_used": list({c["method"] for c in protocol_calls}),
            "known_risks": PROTOCOL_RISK.get(protocol, {}),
        }

    return {
        "by_protocol": by_protocol,
        "protocol_risks": risks,
    }


def scan_file(path: Path) -> dict:
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {"error": "read failed"}

    calls = extract_external_calls(source)
    addr_vars = extract_address_vars(source)
    deps = analyze_dependencies(calls)

    return {
        "file": str(path),
        "external_calls": len(calls),
        "address_vars": addr_vars,
        "dependencies": deps,
    }


def scan_dir(target: Path) -> dict:
    if target.is_file():
        return {"files": [scan_file(target)]}
    files = sorted(target.rglob("*.sol"))
    files = [
        f for f in files
        if "node_modules" not in f.parts
        and "/lib/" not in str(f)
        and ".t.sol" not in f.name
        and "/test/" not in str(f)
    ]

    all_protocols: dict[str, dict] = {}
    file_reports = []
    for f in files:
        r = scan_file(f)
        if r.get("external_calls", 0) > 0:
            file_reports.append(r)
            for protocol, info in r["dependencies"]["protocol_risks"].items():
                if protocol not in all_protocols:
                    all_protocols[protocol] = {"calls_count": 0, "files": [], "methods_used": set()}
                all_protocols[protocol]["calls_count"] += info["calls_count"]
                all_protocols[protocol]["files"].append(r["file"])
                all_protocols[protocol]["methods_used"].update(info["methods_used"])

    for p in all_protocols.values():
        p["methods_used"] = sorted(p["methods_used"])

    return {
        "files": file_reports,
        "aggregate_protocol_dependencies": all_protocols,
    }


def format_md(report: dict) -> str:
    lines = [
        "# Composability Matrix",
        "",
        "External protocol dependencies = potential bug surfaces.",
        "If a protocol can be manipulated/compromised, this target inherits risk.",
        "",
        "## Aggregate Dependencies",
        "",
    ]

    PROTOCOL_RISKS_DESC = {
        "uniswap": "TWAP manipulation, flash loans sourceable here",
        "curve": "**Read-only reentrancy** (2023 attack class), TWAP manipulation",
        "balancer": "Read-only reentrancy, flash loans",
        "aave": "Flash loan source — unlimited capital for atomic exploits",
        "compound": "Liquidation MEV, interest model bugs",
        "chainlink": "Stale price risk, L2 sequencer downtime",
        "lido": "stETH depeg risk, withdrawal queue griefing",
        "rocketpool": "rETH/ETH peg deviations",
        "frax": "frxETH depeg risk, FRAX peg",
        "layerzero": "**DVN compromise (KelpDAO 2024)**, replay attacks",
        "wormhole": "Guardian compromise risk, replay",
        "permit2": "Witness binding edge cases, phishing surface",
    }

    for protocol, info in sorted(report.get("aggregate_protocol_dependencies", {}).items()):
        desc = PROTOCOL_RISKS_DESC.get(protocol, "")
        lines.append(f"### {protocol.upper()}")
        lines.append(f"- Calls: {info['calls_count']}")
        lines.append(f"- Methods used: `{', '.join(info['methods_used'][:10])}`")
        lines.append(f"- Files: {len(info['files'])}")
        if desc:
            lines.append(f"- **Known risks**: {desc}")
        lines.append("")
        lines.append("**Hypothesis**: Can attacker manipulate this dependency to break our target's invariants?")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("## Per-File Detail")
    lines.append("")
    for fr in report.get("files", []):
        if "error" in fr:
            continue
        if not fr.get("dependencies", {}).get("by_protocol"):
            continue
        lines.append(f"### `{fr['file']}`")
        lines.append(f"- {fr['external_calls']} external calls")
        for protocol, calls in fr["dependencies"]["by_protocol"].items():
            if protocol in ("unknown", "tokens"):
                continue
            methods = sorted({c["method"] for c in calls})
            lines.append(f"  - **{protocol}**: {len(calls)} calls, methods: `{', '.join(methods[:5])}`")
        lines.append("")

    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description="Map external protocol dependencies for composability analysis")
    p.add_argument("--target", required=True)
    p.add_argument("--output", default=".")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"ERROR: {target} does not exist")
        return 1

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.quiet:
        print(f"[*] Building composability matrix for {target}...")

    report = scan_dir(target)
    (output_dir / "composability_matrix.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (output_dir / "composability_matrix.md").write_text(format_md(report), encoding="utf-8")

    protocols = list(report.get("aggregate_protocol_dependencies", {}).keys())
    if not args.quiet:
        print(f"[+] External protocols found: {len(protocols)}")
        for p in protocols:
            info = report["aggregate_protocol_dependencies"][p]
            print(f"  - {p}: {info['calls_count']} calls, {len(info['files'])} files")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
