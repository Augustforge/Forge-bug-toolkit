// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Cat 9.7 VULN — ArcadiaFi composite: (A) breaker with re-arm cooldown, (B) unchecked
// router call, (C) dual-role registry (router AND account whitelist).
contract ArcadiaVuln {
    bool public paused;
    uint256 public lastUnpause;
    uint256 public constant cooldown = 4 hours;

    mapping(address => bool) public isRouter;   // registry 1
    mapping(address => bool) public isAccount;   // registry 2

    // (A) re-arm cooldown: cannot pause again for `cooldown` after an unpause
    function pause() external {
        require(block.timestamp > lastUnpause + cooldown, "rearm cooldown");
        paused = true;
    }

    function unpause() external {
        paused = false;
        lastUnpause = block.timestamp;
    }

    function setRouter(address r) external { isRouter[r] = true; }
    function whitelistAccount(address a) external { isAccount[a] = true; }

    // (B) unchecked external router call — target + data unvalidated
    function _swapViaRouter(address swapRouter, bytes calldata data) internal {
        (bool ok, ) = swapRouter.call(data);
        require(ok, "swap failed");
    }

    function rebalance(address swapRouter, bytes calldata data) external {
        _swapViaRouter(swapRouter, data);
    }
}
