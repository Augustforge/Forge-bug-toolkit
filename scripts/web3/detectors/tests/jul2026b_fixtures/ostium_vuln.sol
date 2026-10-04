// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Cat 5.14 VULN — Ostium future-dated oracle: signer authenticated, report timestamp
// bounded only on the LOWER side (too-old), NOT on the upper side (future-dated).
contract OstiumVerifierVuln {
    mapping(address => bool) public authorized;
    uint256 public constant MAX_DELAY = 60;
    uint256 public price;

    function submitReport(
        uint256 reportTimestamp,
        uint256 reportPrice,
        bytes32 hash,
        uint8 v, bytes32 r, bytes32 s
    ) external {
        address signer = ecrecover(hash, v, r, s);
        require(authorized[signer], "unauthorized signer");
        // staleness LOWER bound only — nothing rejects a future-dated report
        require(block.timestamp - reportTimestamp <= MAX_DELAY, "stale");
        // newer timestamp wins -> attacker future-dates to overwrite real price
        price = reportPrice;
    }
}
