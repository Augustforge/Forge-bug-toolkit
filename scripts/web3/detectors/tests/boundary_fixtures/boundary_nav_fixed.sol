contract FleetCommander {
    Ark[] public arks;
    mapping(uint256 => bool) public arkCapped;
    function offboard(uint256 id) external onlyGov { arkCapped[id] = true; }

    function totalAssets() public view returns (uint256 nav) {
        for (uint256 i; i < arks.length; i++) {
            if (arkCapped[i]) continue;          // excluded from NAV
            nav += arks[i].balance();
        }
    }
}
