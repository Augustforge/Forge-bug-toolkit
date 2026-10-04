contract Token {
    mapping(address => uint256) balanceOf;
    function transfer(address to, uint256 amt) external returns (bool) {
        balanceOf[msg.sender] -= amt;
        balanceOf[to] += amt;
        return true;
    }
    function totalSupply() external view returns (uint256) { return _supply; }
}
