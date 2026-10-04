// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Cat 3.16 FIXED — burn path now re-checks the peg via oracle before redeeming.
interface IOracle { function getPrice() external view returns (uint256); }

contract ChiArbitrageFixed {
    IOracle public oracle;
    address public collateral;
    uint256 public constant PEG_PRECISION = 1e18;
    uint256 public constant PEG_FLOOR = 99e16;

    function mint(uint256 collateralIn) external returns (uint256 usc) {
        uint256 p = oracle.getPrice();
        require(p >= PEG_PRECISION, "below peg on mint");
        usc = collateralIn * p / PEG_PRECISION;
    }

    function burn(uint256 uscAmount) external returns (uint256 collateralOut) {
        uint256 p = oracle.getPrice();
        require(p >= PEG_FLOOR, "depeg: redemption blocked"); // depeg guard
        collateralOut = uscAmount * p / PEG_PRECISION;
        _payout(msg.sender, collateralOut);
    }

    function _payout(address to, uint256 amt) internal {}
}
