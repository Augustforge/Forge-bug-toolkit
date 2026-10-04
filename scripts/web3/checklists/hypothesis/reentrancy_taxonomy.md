# Hypothesis: Reentrancy Taxonomy (8 sub-types)

**Trigger**: target has external calls. Apply each sub-type lens.

## 1. Classic single-function reentrancy
- Function transfers to user, then updates state
- DAO attack pattern
- `nonReentrant` modifier prevents

## 2. Cross-function reentrancy
- Function A and B both touch state X
- A calls external (callback enters B), B reads X mid-flight
- `nonReentrant` per-function INSUFFICIENT — need shared lock

## 3. Cross-contract reentrancy
- Contract A calls B. B calls back into A through different entry.
- Both A and B may have `nonReentrant` independently — still vulnerable.

## 4. Read-only reentrancy (Curve pattern)
- View function reads state that mutating function changes mid-flight
- View function doesn't have `nonReentrant` (it's view)
- Caller of view doesn't realize state is mid-update

## 5. ERC-721 onERC721Received callback
- `safeTransferFrom` triggers receiver callback
- During liquidation, NFT transfer can callback
- Hyperseismic class — many protocols

## 6. ERC-777 tokensReceived callback
- Receiver callback during token transfer
- Most protocols don't realize ERC-777 has this
- imBTC and others

## 7. Same-chain cross-tx reentrancy
- Not classical reentrancy, but state-based
- Tx[N] sets state, Tx[N+1] reads stale state
- MEV-amplified

## 8. ERC-4626 hook reentrancy
- Vaults with deposit/withdraw hooks
- Hook can callback before share accounting

## Verification approach

For each sub-type:
1. Identify functions with external calls
2. Identify what state is updated AFTER the external call
3. Build receiver contract that re-enters
4. Test if invariant breaks

## Mitigations to check

- Checks-Effects-Interactions order
- `nonReentrant` modifier (must cover ALL related functions)
- Reentrancy lock visible to view functions (cross-type 4)
- Explicit reentrancy protection on view (`whenNotEntered` pattern)
