# Hypothesis: Cross-Chain Drift

**Trigger**: same protocol deployed on multiple chains. Compare bytecode.

## Pattern

Protocol P deployed on Ethereum + Arbitrum + Optimism. Should be identical. If bytecode differs:
- Intentional (e.g., L2-specific gas optimization)
- Bug fix on one chain, not propagated
- Backdoor on one chain

Either way: investigate.

## Identification

```bash
# Get bytecode on multiple chains via cast
cast code 0xPROTOCOL --rpc-url $ETH_RPC > eth.hex
cast code 0xPROTOCOL --rpc-url $ARB_RPC > arb.hex
diff eth.hex arb.hex
```

Or use `scripts/web3/hypothesis/cross_chain_drift.py`.

## Storage layout drift

Particularly dangerous for upgradeable contracts:
- V1 storage layout on Ethereum
- V2 deployed on Arbitrum with reordered vars
- Same `setOwner()` call has different effect on different chains

## Drift signals

- Bytecode hash differs (>1% characters)
- Selector list differs (functions added/removed)
- Storage layout (if verified source available) shows new variables

## Verification

1. Decompile both versions (`scripts/web3/bytecode/decompile.py`)
2. Identify which functions differ
3. For different function, test behavior on both chains:
   ```solidity
   // Same call, different results = drift bug
   uint256 ethResult = simulateCall_Ethereum(...);
   uint256 arbResult = simulateCall_Arbitrum(...);
   assertEq(ethResult, arbResult);
   ```

## Past examples

- Lombard LBTC: Arbitrum vs Base deployments had +1 storage slot drift (we found earlier)
- Multiple bridges have drift bugs that allowed theft on one chain only

## Severity

- Functional drift (different behavior) → typically High
- Storage layout drift → Critical (state corruption possible)
- Cosmetic drift (compiler version) → Informational
