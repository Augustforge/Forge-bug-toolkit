// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Cat 5.14 FIXED — upper-bound guard added: report timestamp bounded on BOTH sides.
contract OstiumVerifierFixed {
    mapping(address => bool) public authorized;
    uint256 public constant MAX_DELAY = 60;
    uint256 public constant MAX_SKEW = 5;
    uint256 public price;

    function submitReport(
        uint256 reportTimestamp,
        uint256 reportPrice,
        bytes32 hash,
        uint8 v, bytes32 r, bytes32 s
    ) external {
        address signer = ecrecover(hash, v, r, s);
        require(authorized[signer], "unauthorized signer");
        require(block.timestamp - reportTimestamp <= MAX_DELAY, "stale");
        // upper bound (future-dated guard) present -> safe
        require(reportTimestamp <= block.timestamp + MAX_SKEW, "future-dated");
        price = reportPrice;
    }
}
