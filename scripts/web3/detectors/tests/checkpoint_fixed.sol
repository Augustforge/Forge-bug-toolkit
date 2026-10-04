// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Fixture: sync always recomputes, no per-block skip. Expected 0 flags.
contract StakingFixed {
    uint256 public recordedSupply;
    uint256 public actualBalance;

    function _checkpoint() private {
        recordedSupply = actualBalance;
    }

    function deposit(uint256 amount) external {
        _checkpoint();
        uint256 spareAmount = actualBalance - recordedSupply;
        _mintShares(msg.sender, amount + spareAmount);
    }

    function _mintShares(address to, uint256 n) internal {}
}
