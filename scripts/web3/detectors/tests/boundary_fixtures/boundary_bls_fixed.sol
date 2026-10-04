contract SupraPullOracle {
    function verifyUpdate(uint256[2] memory sig, uint256[2] memory pubkey, bytes32 msgHash)
        internal returns (bool)
    {
        require(sig[0] != 0 || sig[1] != 0, "zero sig");
        require(pubkey[0] != 0 || pubkey[1] != 0, "zero pk");
        require(isInSubgroup(sig) && isInSubgroup(pubkey), "subgroup");
        uint256[2] memory hm = hashToG1(msgHash);
        return blsPairing(sig, G2_GEN, hm, pubkey);
    }
    function pushPrice(uint256 price, uint256[2] memory sig, uint256[2] memory pubkey, bytes32 h) external {
        require(verifyUpdate(sig, pubkey, h), "bad sig");
        feed[msg.sender] = price;
    }
}
