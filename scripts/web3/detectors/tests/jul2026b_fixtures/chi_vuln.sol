// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Cat 3.16 VULN — Chi Protocol: mint path peg-aware (reads oracle), burn path redeems
// collateral at a hardcoded $1 peg with NO price/depeg guard.
interface IOracle { function getPrice() external view returns (uint256); }

contract ChiArbitrageVuln {
    IOracle public oracle;
    address public collateral;
    uint256 public constant PEG_PRECISION = 1e18;

    // mint: peg-aware, consults the oracle before issuing
    function mint(uint256 collateralIn) external returns (uint256 usc) {
        uint256 p = oracle.getPrice();
        require(p >= PEG_PRECISION, "below peg on mint");
        usc = collateralIn * p / PEG_PRECISION;
    }

    // burn: pays collateral at a hardcoded $1 peg, no depeg check
    function burn(uint256 uscAmount) external returns (uint256 collateralOut) {
        collateralOut = uscAmount * 1e18 / PEG_PRECISION; // assumes $1, no price read
        _payout(msg.sender, collateralOut);
    }

    function _payout(address to, uint256 amt) internal {}
}
