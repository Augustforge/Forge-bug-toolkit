# Comment Mining — Hypothesis Candidates

Extracted from Solidity comments: invariants, TODOs, audit-mentions, warnings.
Each is a candidate hypothesis: "the developer DOCUMENTED this; verify it actually holds."

**Priority key**: audit/todo/warning = 3pt, invariant/assumption = 2pt, others = 1pt.

---

## `..\..\..\sessions\alchemix-v3\v3\src\strategies\SFraxETHStrategy.sol`

### H1: `..\..\..\sessions\alchemix-v3\v3\src\strategies\SFraxETHStrategy.sol:67` — priority 6

**Signals**: edge_case, natspec_dev, depeg_or_economic, oracle_concern
**Comment** (natspec_line):
```
@dev This is an oracle-independent downside guard against pathological quotes or severe frxETH depegs.
```
**Nearby code**:
```solidity
  67:     /// @dev This is an oracle-independent downside guard against pathological quotes or severe frxETH depegs.
  68:     function setMinFrxEthOutBps(uint256 newMinFrxEthOutBps) external onlyOwner {
  69:         require(newMinFrxEthOutBps <= 10_000, "Invalid min frxETH out bps");
  70:         minFrxEthOutBps = newMinFrxEthOutBps;
  71:         emit MinFrxEthOutBpsUpdated(newMinFrxEthOutBps);
  72:     }
  73: 
  74:     function _deallocate(uint256, bytes memory) internal pure override returns (uint256) {
```

**Verification plan**: Verify if statement in comment actually holds in all code paths. 
If invariant — write Foundry invariant test. If TODO/FIXME — check if condition was fixed in code.

---

### H2: `..\..\..\sessions\alchemix-v3\v3\src\strategies\SFraxETHStrategy.sol:66` — priority 1

**Signals**: natspec_notice
**Comment** (natspec_line):
```
@notice Updates the minimum raw frxETH output floor enforced after swap-based allocations.
```
**Nearby code**:
```solidity
  66:     /// @notice Updates the minimum raw frxETH output floor enforced after swap-based allocations.
  67:     /// @dev This is an oracle-independent downside guard against pathological quotes or severe frxETH depegs.
  68:     function setMinFrxEthOutBps(uint256 newMinFrxEthOutBps) external onlyOwner {
  69:         require(newMinFrxEthOutBps <= 10_000, "Invalid min frxETH out bps");
  70:         minFrxEthOutBps = newMinFrxEthOutBps;
  71:         emit MinFrxEthOutBpsUpdated(newMinFrxEthOutBps);
  72:     }
  73: 
```

**Verification plan**: Verify if statement in comment actually holds in all code paths. 
If invariant — write Foundry invariant test. If TODO/FIXME — check if condition was fixed in code.

---
