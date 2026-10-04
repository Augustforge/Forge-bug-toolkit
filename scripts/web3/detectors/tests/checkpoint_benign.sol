// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Fixture: ordinary deadline/timestamp use, no recorded-vs-real delta. Expected 0 flags.
contract Auction {
    uint256 public deadline;
    uint256 public startBlock;

    function bid() external payable {
        if (block.timestamp > deadline) revert();
        if (block.number < startBlock) revert();
        _record(msg.sender, msg.value);
    }

    function _record(address who, uint256 amt) internal {}
}
