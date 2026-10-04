# Foundry Test Corpus

Pre-built Foundry test templates for common attack vectors.

Each `.t.sol.template` is a fork-mode exploit test that needs minor edits:
- Set target contract address
- Set forked block number
- Optionally set initial state

## Templates

| File | Attack class |
|------|--------------|
| `Reentrancy.t.sol.template` | Classic external-call reentrancy |
| `OracleManipulation.t.sol.template` | Spot/TWAP price manipulation |
| `FlashLoanDrain.t.sol.template` | Flash-loan amplified protocol exploit |
| `GovernanceTakeover.t.sol.template` | Quorum + proposal stuffing |
| `Erc4626Inflation.t.sol.template` | First-depositor share inflation (Cream pattern) |
| `ReadOnlyReentrancy.t.sol.template` | Curve r/o reentrancy pattern |
| `StorageCollision.t.sol.template` | Proxy upgrade storage drift |
| `Permit2Witness.t.sol.template` | Permit2 witness binding edge cases |

## Usage

```bash
cp Reentrancy.t.sol.template sessions/$TARGET/poc/Reentrancy_F001.t.sol
# Edit: target address, block, expected state
forge test --match-test test_Exploit -vvv --fork-url $RPC
```
