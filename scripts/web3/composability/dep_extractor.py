#!/usr/bin/env python3
"""
dep_extractor.py — Find external dependencies (other protocols) used by target.

Detection sources:
1. `import "..."` statements (local + GitHub-style)
2. Interface usage: `IAave(addr).deposit(...)`, `IUniswapV3Pool(addr).swap(...)`
3. Known address constants (Aave, Uniswap, Pyth, LayerZero, etc. on mainnet)
4. Function call patterns with typical dep names

Output: deps.json list of {name, kind, surface[], confidence}

Usage:
  python3 dep_extractor.py --repo /path/to/target --output sessions/$T/composability/
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# Known dep families with detection patterns
DEP_PATTERNS = {
    "aave-v3": {
        "kind": "lending",
        "interfaces": ["IPool", "IAaveOracle", "IRewardsController", "IAaveIncentivesController"],
        "import_patterns": [r"@aave/", r"aave-v3-core"],
        "keywords": ["aavePool", "aave_pool"],
    },
    "aave-v2": {
        "kind": "lending",
        "interfaces": ["ILendingPool", "ILendingPoolAddressesProvider"],
        "import_patterns": [r"@aave/protocol-v2"],
        "keywords": [],
    },
    "compound-v3": {
        "kind": "lending",
        "interfaces": ["IComet", "ICometRewards"],
        "import_patterns": [r"compound-finance/comet"],
        "keywords": ["comet"],
    },
    "uniswap-v3": {
        "kind": "amm",
        "interfaces": ["IUniswapV3Pool", "IUniswapV3Factory", "ISwapRouter", "IQuoter"],
        "import_patterns": [r"@uniswap/v3-core", r"@uniswap/v3-periphery"],
        "keywords": ["univ3"],
    },
    "uniswap-v2": {
        "kind": "amm",
        "interfaces": ["IUniswapV2Pair", "IUniswapV2Router", "IUniswapV2Factory"],
        "import_patterns": [r"@uniswap/v2-core", r"@uniswap/v2-periphery"],
        "keywords": [],
    },
    "uniswap-v4": {
        "kind": "amm",
        "interfaces": ["IPoolManager", "IHooks", "PoolKey"],
        "import_patterns": [r"@uniswap/v4-core", r"v4-core/"],
        "keywords": [],
    },
    "curve": {
        "kind": "amm",
        "interfaces": ["ICurvePool", "ICryptoPool", "IStableSwap"],
        "import_patterns": [r"curve-contract"],
        "keywords": ["curvePool"],
    },
    "balancer-v2": {
        "kind": "amm",
        "interfaces": ["IVault", "IBasePool", "IBalancerHelpers"],
        "import_patterns": [r"@balancer-labs"],
        "keywords": [],
    },
    "chainlink": {
        "kind": "oracle",
        "interfaces": ["AggregatorV3Interface", "AggregatorInterface", "FeedRegistryInterface", "VRFCoordinatorV2Interface"],
        "import_patterns": [r"@chainlink/contracts"],
        "keywords": ["chainlink"],
    },
    "pyth": {
        "kind": "oracle",
        "interfaces": ["IPyth", "PythStructs"],
        "import_patterns": [r"@pythnetwork"],
        "keywords": ["pyth"],
    },
    "layerzero-v2": {
        "kind": "bridge",
        "interfaces": ["ILayerZeroEndpointV2", "ILayerZeroReceiver", "IOAppCore", "OApp"],
        "import_patterns": [r"@layerzerolabs", r"layerzero-v2/"],
        "keywords": [],
    },
    "wormhole": {
        "kind": "bridge",
        "interfaces": ["IWormhole", "ITokenBridge", "ICircleIntegration"],
        "import_patterns": [r"wormhole-foundation"],
        "keywords": ["wormhole"],
    },
    "axelar": {
        "kind": "bridge",
        "interfaces": ["IAxelarGateway", "IAxelarGasService"],
        "import_patterns": [r"@axelar-network"],
        "keywords": ["axelar"],
    },
    "ccip": {
        "kind": "bridge",
        "interfaces": ["IRouterClient", "Client.EVM2AnyMessage", "CCIPReceiver"],
        "import_patterns": [r"@chainlink/contracts-ccip"],
        "keywords": ["ccip"],
    },
    "eigenlayer": {
        "kind": "restaking",
        "interfaces": ["IDelegationManager", "IStrategyManager", "IAVSDirectory", "IEigenPodManager"],
        "import_patterns": [r"@eigenlayer/", r"layr-labs/eigenlayer-contracts"],
        "keywords": ["eigen"],
    },
    "lido-steth": {
        "kind": "lst",
        "interfaces": ["ILido", "IStETH", "IWstETH"],
        "import_patterns": [r"@lido/"],
        "keywords": ["steth", "lido"],
    },
    "morpho": {
        "kind": "lending",
        "interfaces": ["IMorpho", "IMorphoBlue", "MarketParams"],
        "import_patterns": [r"@morpho/"],
        "keywords": ["morpho"],
    },
    "permit2": {
        "kind": "approval",
        "interfaces": ["IPermit2", "ISignatureTransfer", "IAllowanceTransfer"],
        "import_patterns": [r"@uniswap/permit2"],
        "keywords": ["permit2"],
    },
}

# Mainnet addresses (canonical references)
KNOWN_ADDRESSES = {
    # Aave v3 Pool
    "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2": "aave-v3",
    # Uniswap v3 Factory
    "0x1f98431c8ad98523631ae4a59f267346ea31f984": "uniswap-v3",
    # Pyth main
    "0x4305fb66699c3b2702d4d05cf36551390a4c69c6": "pyth",
    # LayerZero v2 Endpoint
    "0x1a44076050125825900e736c501f859c50fe728c": "layerzero-v2",
    # EigenLayer DelegationManager
    "0x39053d51b77dc0d36036fc1fcc8cb819df8ef37a": "eigenlayer",
    # stETH
    "0xae7ab96520de3a18e5e111b5eaab095312d7fe84": "lido-steth",
    # Permit2
    "0x000000000022d473030f116ddee9f6b43ac78ba3": "permit2",
}

SKIP_DIRS = {".git", "node_modules", "out", "build", "cache", "dist", "lib", "artifacts"}


def find_solidity_files(repo: Path) -> list[Path]:
    out = []
    for p in repo.rglob("*.sol"):
        try:
            rel = p.relative_to(repo).parts
        except ValueError:
            rel = p.parts
        if any(s in rel for s in SKIP_DIRS):
            continue
        out.append(p)
    return out


def scan_file(f: Path) -> dict[str, list[dict]]:
    """Returns {dep_name: [{file:line, evidence}]}"""
    out = defaultdict(list)
    try:
        text = f.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return out

    lines = text.splitlines()
    for dep, spec in DEP_PATTERNS.items():
        for i, line in enumerate(lines, 1):
            ll = line.lower()

            # Import patterns
            for p in spec["import_patterns"]:
                if re.search(p, line, re.IGNORECASE):
                    out[dep].append({"file": str(f), "line": i,
                                      "evidence": f"import: {line.strip()[:120]}"})

            # Interface usage
            for iface in spec["interfaces"]:
                if iface in line:
                    out[dep].append({"file": str(f), "line": i,
                                      "evidence": f"interface: {line.strip()[:120]}"})

            # Keyword markers
            for kw in spec.get("keywords", []):
                if kw.lower() in ll:
                    out[dep].append({"file": str(f), "line": i,
                                      "evidence": f"keyword '{kw}': {line.strip()[:120]}"})

    # Known address constants
    addr_re = re.compile(r"0x[a-fA-F0-9]{40}")
    for i, line in enumerate(lines, 1):
        for m in addr_re.finditer(line):
            addr = m.group(0).lower()
            if addr in KNOWN_ADDRESSES:
                dep = KNOWN_ADDRESSES[addr]
                out[dep].append({"file": str(f), "line": i,
                                  "evidence": f"known addr: {line.strip()[:120]}"})

    return out


def is_self_reference(repo: Path, dep_name: str) -> bool:
    """Self-reference detection: avoid false positive when repo IS the dep itself
    (e.g., Morpho Blue detecting "morpho" as its own dep).

    Signals (any → True):
    1. Repo directory name matches dep
    2. Top-level src/<CapitalizedDep>.sol exists (canonical primary contract)
    3. README.md first 200 chars mentions dep as project title
    4. package.json / foundry.toml name field matches
    """
    base = dep_name.split("-")[0].lower()                 # "aave-v3" → "aave"
    repo_name = repo.name.lower()
    if base in repo_name:
        return True

    # Top-level primary contract file matching dep name
    pascal = base.capitalize()
    candidates = [
        repo / f"{pascal}.sol",
        repo / "src" / f"{pascal}.sol",
        repo / "contracts" / f"{pascal}.sol",
    ]
    if any(c.exists() for c in candidates):
        return True

    # README mentions dep as title
    readme = repo / "README.md"
    if readme.exists():
        try:
            head = readme.read_text(encoding="utf-8", errors="ignore")[:500].lower()
            # Look for "# Morpho" / "# aave" / "Project: <dep>" patterns
            if f"# {base}" in head or f"#{base}" in head:
                return True
        except Exception:
            pass

    # Config files
    for cfg in ["package.json", "foundry.toml"]:
        cfg_path = repo / cfg
        if cfg_path.exists():
            try:
                content = cfg_path.read_text(encoding="utf-8", errors="ignore").lower()
                if f'"name": "{dep_name}' in content or f'name = "{dep_name}' in content:
                    return True
                if f'"name": "{base}' in content or f'name = "{base}' in content:
                    return True
            except Exception:
                continue
    return False


def filter_self_evidence(surface: list[dict], dep_name: str) -> list[dict]:
    """Remove keyword-only matches that look like self-references (e.g., internal interface imports)."""
    filtered = []
    for s in surface:
        ev = s.get("evidence", "")
        # Drop keyword matches that are clearly internal (../path or ./path)
        if "keyword " in ev and ("./" in ev or "../" in ev or "from \"./" in ev or "from \"../" in ev):
            continue
        # Drop interface matches that come from a non-import line that's a struct/contract def
        if "interface:" in ev and any(kw in ev for kw in [" interface ", " contract ", " library "]):
            continue
        filtered.append(s)
    return filtered


def aggregate(repo: Path) -> list[dict]:
    files = find_solidity_files(repo)
    print(f"[info] scanning {len(files)} .sol files", file=sys.stderr)
    by_dep = defaultdict(list)
    for f in files:
        per_file = scan_file(f)
        for dep, hits in per_file.items():
            by_dep[dep].extend(hits)

    deps = []
    for dep, surface in sorted(by_dep.items()):
        if is_self_reference(repo, dep):
            print(f"[info] skipping {dep} — self-reference (repo IS the dep)", file=sys.stderr)
            continue
        surface = filter_self_evidence(surface, dep)
        if not surface:
            continue
        confidence = "high" if len(surface) >= 3 else ("medium" if len(surface) >= 1 else "low")
        deps.append({
            "name": dep,
            "kind": DEP_PATTERNS[dep]["kind"],
            "confidence": confidence,
            "surface_count": len(surface),
            "surface_in_target": surface[:10],  # keep first 10 examples
        })
    deps.sort(key=lambda d: -d["surface_count"])
    return deps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="Target Solidity repo")
    ap.add_argument("--output", required=True, help="Output directory")
    args = ap.parse_args()

    repo = Path(args.repo)
    if not repo.is_dir():
        print(f"[err] not a directory: {repo}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    deps = aggregate(repo)
    out_path = out_dir / "deps.json"
    out_path.write_text(json.dumps(deps, indent=2), encoding="utf-8")
    print(f"[ok] {len(deps)} deps detected → {out_path}")
    for d in deps[:10]:
        print(f"  - {d['name']:<20} [{d['kind']:<10}] {d['confidence']:<6} ({d['surface_count']} hits)")


if __name__ == "__main__":
    main()
