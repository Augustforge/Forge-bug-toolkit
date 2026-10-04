// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Fixture: the Tranchess-shaped per-block skip. Expected risk 3.
contract StakingVuln {
    uint256 public recordedSupply;
    uint256 public actualBalance;
    uint256 public lastCheckpoint;

    function _checkpoint() private {
        if (lastCheckpoint >= block.timestamp) return;
        lastCheckpoint = block.timestamp;
        recordedSupply = actualBalance;
    }

    function deposit(uint256 amount) external {
        _checkpoint();
        uint256 spareAmount = actualBalance - recordedSupply;
        _mintShares(msg.sender, amount + spareAmount);
    }

    function _mintShares(address to, uint256 n) internal {}
}
