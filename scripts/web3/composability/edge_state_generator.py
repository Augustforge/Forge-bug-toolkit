#!/usr/bin/env python3
"""
edge_state_generator.py — Generate Foundry mock contracts with edge states for each dep.

For each dep (e.g., aave-v3, chainlink, pyth): emits `MockX.sol` with:
- Implementation of dep's interface
- State switches: `setPaused(bool)`, `setReturnExtremeValue(bool)`, etc.
- Helper view functions

Output: Foundry-compatible .sol files in output dir/Mocks/

Usage:
  python3 edge_state_generator.py --deps sessions/$T/composability/deps.json \\
      --output sessions/$T/composability/Mocks/
"""
import argparse
import json
import sys
from pathlib import Path

# Mock templates per dep kind
MOCK_TEMPLATES = {
    "lending": """\
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @notice Mock {DEP_NAME} (lending) with configurable edge states
contract Mock{DEP_NAME_PASCAL} {
    bool public paused;
    uint256 public liquidityAvailable = 1e18;
    uint256 public utilizationBps = 5000;          // 50%
    bool public oracleStale;

    // Edge-state setters
    function setPaused(bool _v) external { paused = _v; }
    function setLiquidity(uint256 _v) external { liquidityAvailable = _v; }
    function setUtilization(uint256 _bps) external { utilizationBps = _bps; }
    function setOracleStale(bool _v) external { oracleStale = _v; }

    // Common interface fns — adapt to actual interface called by target
    function supply(address, uint256 _amount, address, uint16) external {
        require(!paused, "Paused");
        require(liquidityAvailable >= _amount, "InsufficientLiquidity");
    }
    function withdraw(address, uint256 _amount, address) external returns (uint256) {
        require(!paused, "Paused");
        require(liquidityAvailable >= _amount, "InsufficientLiquidity");
        liquidityAvailable -= _amount;
        return _amount;
    }
    function getReserveData(address) external view returns (uint256 currentLiquidityRate) {
        return utilizationBps;
    }
}
""",
    "amm": """\
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract Mock{DEP_NAME_PASCAL} {
    bool public paused;
    uint256 public poolReserveA = 1e18;
    uint256 public poolReserveB = 1e18;
    uint160 public sqrtPriceX96 = 79228162514264337593543950336;  // 1:1
    uint24 public feeBps = 30;

    function setPaused(bool _v) external { paused = _v; }
    function setReserves(uint256 _a, uint256 _b) external { poolReserveA = _a; poolReserveB = _b; }
    function setSqrtPrice(uint160 _p) external { sqrtPriceX96 = _p; }
    function setFee(uint24 _bps) external { feeBps = _bps; }

    // Common AMM interface fns
    function swap(address, bool, int256 _amountSpecified, uint160, bytes calldata)
        external returns (int256 amount0, int256 amount1) {
        require(!paused, "Paused");
        require(poolReserveA > 0 && poolReserveB > 0, "DrainedPool");
        return (-_amountSpecified, _amountSpecified);
    }
    function slot0() external view returns (
        uint160 sqrtPriceX96_, int24 tick, uint16, uint16, uint16, uint8, bool unlocked
    ) {
        return (sqrtPriceX96, 0, 0, 0, 0, 0, !paused);
    }
}
""",
    "oracle": """\
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract Mock{DEP_NAME_PASCAL} {
    int256 public price = 1e8;                      // $1.00 in 8-decimals
    uint256 public updatedAt = block.timestamp;
    bool public returnZero;
    bool public returnMax;
    bool public returnStale;
    uint256 public stalenessSeconds = 7200;          // 2 hours

    function setPrice(int256 _v) external { price = _v; }
    function setReturnZero(bool _v) external { returnZero = _v; }
    function setReturnMax(bool _v) external { returnMax = _v; }
    function setReturnStale(bool _v) external { returnStale = _v; }

    function latestRoundData() external view returns (
        uint80 roundId, int256 answer, uint256 startedAt, uint256 updatedAt_, uint80 answeredInRound
    ) {
        if (returnZero) return (1, 0, block.timestamp, block.timestamp, 1);
        if (returnMax) return (1, type(int256).max, block.timestamp, block.timestamp, 1);
        if (returnStale) {
            uint256 stale = block.timestamp > stalenessSeconds ? block.timestamp - stalenessSeconds : 0;
            return (1, price, stale, stale, 1);
        }
        return (1, price, block.timestamp, block.timestamp, 1);
    }
    function latestAnswer() external view returns (int256) {
        if (returnZero) return 0;
        if (returnMax) return type(int256).max;
        return price;
    }
    function decimals() external pure returns (uint8) { return 8; }
}
""",
    "bridge": """\
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract Mock{DEP_NAME_PASCAL} {
    bool public paused;
    bool public revertOnSend;
    bool public messageReplayable;                   // edge: same msgId accepted twice

    function setPaused(bool _v) external { paused = _v; }
    function setRevertOnSend(bool _v) external { revertOnSend = _v; }
    function setMessageReplayable(bool _v) external { messageReplayable = _v; }

    function send(bytes calldata) external payable returns (bytes32) {
        require(!paused, "BridgePaused");
        require(!revertOnSend, "RevertOnSend");
        return keccak256(abi.encodePacked(block.timestamp));
    }
    function quoteFee(bytes calldata) external pure returns (uint256) {
        return 0.001 ether;
    }
}
""",
    "restaking": """\
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract Mock{DEP_NAME_PASCAL} {
    bool public operatorSlashed;
    uint256 public withdrawalQueueDelay = 7 days;
    bool public queueFull;
    uint256 public sharePrice = 1e18;

    function setOperatorSlashed(bool _v) external { operatorSlashed = _v; }
    function setQueueDelay(uint256 _s) external { withdrawalQueueDelay = _s; }
    function setQueueFull(bool _v) external { queueFull = _v; }
    function setSharePrice(uint256 _v) external { sharePrice = _v; }

    function delegateTo(address) external {}
    function queueWithdrawal(uint256 _shares) external returns (bytes32) {
        require(!queueFull, "QueueFull");
        return keccak256(abi.encode(_shares, block.timestamp));
    }
    function completeQueuedWithdrawal(bytes32) external {
        require(!operatorSlashed, "OperatorSlashedDuringQueue");
    }
}
""",
    "lst": """\
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract Mock{DEP_NAME_PASCAL} {
    uint256 public exchangeRate = 1e18;
    bool public negativeYield;
    bool public paused;

    function setExchangeRate(uint256 _v) external { exchangeRate = _v; }
    function setNegativeYield(bool _v) external { negativeYield = _v; }
    function setPaused(bool _v) external { paused = _v; }

    function getPooledEthByShares(uint256 _shares) external view returns (uint256) {
        require(!paused, "LSTPaused");
        if (negativeYield) return _shares * 9 / 10;
        return _shares * exchangeRate / 1e18;
    }
}
""",
    "approval": """\
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract Mock{DEP_NAME_PASCAL} {
    bool public alwaysApprove;
    bool public denyAll;

    function setAlwaysApprove(bool _v) external { alwaysApprove = _v; }
    function setDenyAll(bool _v) external { denyAll = _v; }

    function permit(address, address, uint160, uint48, uint48, bytes calldata) external {
        if (denyAll) revert("PermitDenied");
    }
}
""",
}

DEFAULT_TEMPLATE = """\
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @notice Generic dep mock — extend manually for target's specific calls
contract Mock{DEP_NAME_PASCAL} {
    bool public paused;
    function setPaused(bool _v) external { paused = _v; }
    // TODO: add functions used by target
}
"""


def pascal_case(name: str) -> str:
    return "".join(part.capitalize() for part in name.replace("_", "-").split("-"))


def gen_mock(dep: dict) -> str:
    template = MOCK_TEMPLATES.get(dep["kind"], DEFAULT_TEMPLATE)
    return template.replace("{DEP_NAME}", dep["name"]).replace("{DEP_NAME_PASCAL}", pascal_case(dep["name"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deps", required=True, help="deps.json from dep_extractor")
    ap.add_argument("--output", required=True, help="Output Mocks/ directory")
    ap.add_argument("--min-confidence", default="medium",
                    choices=["low", "medium", "high"],
                    help="Skip deps below this confidence")
    args = ap.parse_args()

    deps = json.loads(Path(args.deps).read_text(encoding="utf-8"))
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    conf_order = {"low": 0, "medium": 1, "high": 2}
    min_conf = conf_order[args.min_confidence]

    generated = []
    for dep in deps:
        if conf_order.get(dep.get("confidence", "low"), 0) < min_conf:
            continue
        mock_src = gen_mock(dep)
        out_file = out_dir / f"Mock{pascal_case(dep['name'])}.sol"
        out_file.write_text(mock_src, encoding="utf-8")
        generated.append((dep["name"], dep["kind"], out_file.name))

    print(f"[ok] generated {len(generated)} mock(s) in {out_dir}")
    for name, kind, fname in generated:
        print(f"  - {name:<20} [{kind:<10}] → {fname}")
    if not generated:
        print(f"[warn] no deps passed confidence threshold ({args.min_confidence})")


if __name__ == "__main__":
    main()
