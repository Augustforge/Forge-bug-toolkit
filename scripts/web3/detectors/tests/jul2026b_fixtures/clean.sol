// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Clean baseline — plain ERC20, no oracle verifier, no mint/burn peg asymmetry,
// no breaker/router. Every jul2026b detector must stay silent here.
contract PlainToken {
    mapping(address => uint256) public balanceOf;
    uint256 public totalSupply;

    function transfer(address to, uint256 amt) external returns (bool) {
        balanceOf[msg.sender] -= amt;
        balanceOf[to] += amt;
        return true;
    }

    function approve(address spender, uint256 amt) external returns (bool) {
        return true;
    }
}
