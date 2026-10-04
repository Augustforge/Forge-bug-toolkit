contract RollupProcessor {
    // VULN (Aztec): trusts verifier success, recipient from calldata, not a proven public input.
    function escapeHatch(bytes calldata proof, bytes32[] calldata publicInputs, address recipient) external {
        require(verifier.verify(proof, publicInputs), "invalid proof");
        _transfer(recipient, extractAmount(publicInputs));   // recipient unbound -> attacker substitutes self
    }
}
contract Hinkal {
    // VULN (Hinkal): a deposit path with no cryptographic binding at all.
    function prooflessDeposit(uint256 amount, address token) external {
        _credit(msg.sender, token, amount);
    }
    function transact(bytes calldata proof) external { _withdrawAll(proof); }
}
