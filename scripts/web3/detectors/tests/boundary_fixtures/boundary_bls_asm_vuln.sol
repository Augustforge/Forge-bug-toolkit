// Real-world BN254 BLS shape (modeled on the Supra verifier read during the 2026-07-11 hunt).
// The pairing precompile is called via inline assembly staticcall(gas, 8, ...) with 8 as the 2nd arg,
// and the ONLY equality-to-zero in the function is the pairing RESULT check out[0] != 0 (not on inputs).
// Both facts previously made the detector silent on every real BN254 verifier (two FNs, since fixed).
// VULN: verifySingle trusts the pairing result without validating the curve inputs it was handed.
library BLS {
    function verifySingle(uint256[2] memory signature, uint256[4] memory pubkey, uint256[2] memory message, uint256 gasCost)
        internal view returns (bool, bool)
    {
        uint256[12] memory input = [signature[0], signature[1], uint256(0),0,0,0, message[0], message[1], pubkey[1], pubkey[0], pubkey[3], pubkey[2]];
        uint256[1] memory out;
        bool ok;
        assembly {
            ok := staticcall(gasCost, 8, input, 384, out, 0x20)
        }
        if (!ok) { return (false, false); }
        return (out[0] != 0, true);   // result check — must NOT be mistaken for an input guard
    }
}
