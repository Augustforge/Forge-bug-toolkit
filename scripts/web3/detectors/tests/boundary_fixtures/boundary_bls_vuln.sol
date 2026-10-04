// Reconstruction of the Supra BLS price-update verifier consumed by Bonzo Lend (Hedera).
contract SupraPullOracle {
    // VULN: pairing result trusted, inputs never checked for zero/subgroup.
    function verifyUpdate(uint256[2] memory sig, uint256[2] memory pubkey, bytes32 msgHash)
        internal returns (bool)
    {
        uint256[2] memory hm = hashToG1(msgHash);
        // e(sig, g2) == e(hm, pubkey) ; with sig=[0,0] & pubkey=[0,0] -> identity == identity
        return blsPairing(sig, G2_GEN, hm, pubkey);
    }

    function pushPrice(uint256 price, uint256[2] memory sig, uint256[2] memory pubkey, bytes32 h) external {
        require(verifyUpdate(sig, pubkey, h), "bad sig");
        feed[msg.sender] = price;      // attacker sets SAUCE ~1e30
    }
}
