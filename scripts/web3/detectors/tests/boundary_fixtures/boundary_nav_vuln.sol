contract FleetCommander {
    Ark[] public arks;
    mapping(uint256 => bool) public arkCapped;   // pause/cap flag DEFINED
    function offboard(uint256 id) external onlyGov { arkCapped[id] = true; }

    // VULN: totalAssets sums EVERY ark, capped ones still weighted in NAV.
    function totalAssets() public view returns (uint256 nav) {
        for (uint256 i; i < arks.length; i++) {
            nav += arks[i].balance();
        }
    }
}
