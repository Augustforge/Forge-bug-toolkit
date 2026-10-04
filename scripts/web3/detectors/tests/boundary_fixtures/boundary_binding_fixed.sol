contract RollupProcessor {
    function escapeHatch(bytes calldata proof, bytes32[] calldata publicInputs) external {
        require(verifier.verify(proof, publicInputs), "invalid proof");
        // recipient is a PROVEN public input, not attacker-supplied
        address recipient = address(uint160(uint256(publicInputs[OWNER_SLOT])));
        _transfer(recipient, extractAmount(publicInputs));
    }
}
contract Hinkal {
    function deposit(uint256 amount, address token, bytes calldata proof, bytes32 commitment) external {
        require(verifier.verify(proof, commitment), "no binding");
        _credit(msg.sender, token, amount);
    }
    function transact(bytes calldata proof, bytes32 nullifier) external {
        require(verifier.verify(proof, nullifier), "bad");
        _withdraw(proof);
    }
}
