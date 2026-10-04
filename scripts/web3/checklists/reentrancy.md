# Reentrancy Checklist (8 patterns)

For a finding tagged `reentrancy*` or a suspicion of reentrancy — go through each item explicitly.

## 1. Classic ETH reentrancy (SWC-107)
- [ ] An `external call` (call/send/transfer) is made **before** the state update
- [ ] `.call{value:}` is used without a gas limit — the attacker's receive() can re-enter
- [ ] No `ReentrancyGuard` modifier (`nonReentrant`)
- **Example:** `(bool ok,) = msg.sender.call{value: amt}(""); balances[msg.sender] -= amt;`

## 2. No-ETH reentrancy (token callback)
- [ ] ERC777 `tokensReceived` hook
- [ ] ERC721 `onERC721Received` hook
- [ ] ERC1155 `onERC1155Received` hook
- [ ] The contract transfers first, then updates state
- **Example:** an ERC777 transfer triggers a receive callback that re-enters

## 3. Read-only reentrancy
- [ ] A view function reads state in the middle of an external call
- [ ] Another contract reads getPrice/totalSupply/balanceOf during the first call — sees inconsistent state
- [ ] Curve, Balancer pools are historically vulnerable
- **Example:** Vault.getPriceOfShare() is called from another protocol, sees an intermediate state

## 4. Cross-function reentrancy
- [ ] The same state variable is changed in `funcA` and `funcB`
- [ ] `funcA` has `nonReentrant`, `funcB` does not
- [ ] Reentry from `funcA` into `funcB` bypasses the mutex
- **Example:** withdraw() and transferAccount() update balance, both must be guarded

## 5. Cross-contract reentrancy
- [ ] Contract A holds state about contract B
- [ ] Reentry via contract C which calls B then A
- [ ] Lending protocols are vulnerable (collateral on one contract, debt on another)

## 6. Reentrancy in modifier
- [ ] A modifier makes an external call **before** the function body
- [ ] The body executes in a re-entered context
- [ ] Often overlooked — the modifier looks safe

## 7. Reentrancy in fallback/receive
- [ ] `fallback()` makes important state changes
- [ ] Receiving ETH triggers logic that calls other functions
- [ ] Very rare but costly if present

## 8. Reentrancy in constructor
- [ ] The constructor makes an external call to a user-provided address
- [ ] Reentry before init completes = uninitialized state exploit
- [ ] Can be combined with CREATE2 attacks

---

## Confirmation pattern

To confirm via Foundry:
```solidity
contract Attacker {
    Target target;
    bool reentered;

    function attack() external payable {
        target.deposit{value: 1 ether}();
        target.withdraw();  // triggers receive() → re-entrate
    }

    receive() external payable {
        if (!reentered && address(target).balance >= 1 ether) {
            reentered = true;
            target.withdraw();  // recursive call
        }
    }
}
```

## Solodit search keywords
`reentrancy`, `re-entry`, `read-only reentrancy`, `cross-function reentrancy`, `ERC777 hook`, `ERC721 callback`
