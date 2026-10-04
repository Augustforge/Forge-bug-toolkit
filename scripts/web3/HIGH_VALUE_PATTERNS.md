# High-Value Patterns Library — Critical Bugs Catalogue

35+ patterns that historically caused $1M+ losses. Each pattern → hypothesis template + detection signals.

For `/deephunt` Phase J7 (Past Exploit Match) and Phase J0 (Hypothesis Generation).

---

## How to Use

For each target, scan this list and ask: **does this protocol have surface for any pattern below?**

If yes → spin up dedicated hypothesis for that pattern.

---

## Pattern 1: ERC-4626 Donation Attack

**Class**: Vault inflation
**Historical losses**: Cream Finance (~$130M), Compound (Sep 2022)

**Mechanism**: Attacker directly transfers tokens to vault without going through `deposit()`. This inflates `totalAssets` without inflating `totalShares`. Next depositor's shares get rounded down to 0 due to high share price.

**Detection signals**:
- ERC-4626 vault with no virtual shares offset
- `totalAssets()` reads contract balance directly
- No "first deposit" protection
- No share price ceiling

**Hypothesis template**:
```
H: Vault is donation-attackable. Adversary mints first share at tiny ratio,
   donates large amount, then victim deposit rounds to 0 shares.
```

**Verification**: Foundry test in `scripts/web3/foundry_corpus/Erc4626Inflation.t.sol.template`

---

## Pattern 2: First-Depositor Share Inflation

**Class**: Vault math
**Historical losses**: Multiple smaller protocols, ongoing class

**Mechanism**: First depositor calculates shares = amount × 1e18 / 0 (div by zero handled as identity). They get 1 share for any deposit. Later depositors compute shares = amount × X / totalAssets where totalAssets is huge.

**Detection signals**: Same as Pattern 1, but check first-deposit code path.

---

## Pattern 3: Read-Only Reentrancy

**Class**: Reentrancy
**Historical losses**: Curve / Balancer (~$60M+ across protocols, 2022-2023)

**Mechanism**: View function (e.g., `get_virtual_price()`) returns state mid-write. Attacker calls reentrant function during `remove_liquidity`, which is non-reentrant for state writes but allows read-only callbacks. Reads stale `totalSupply` while balance temporarily different.

**Detection signals**:
- Vault uses Curve/Balancer LP token price oracle
- Vault calls `get_virtual_price()` or similar without checking reentrancy lock
- Curve pool's `remove_liquidity` callable in chain

**Hypothesis template**:
```
H: Vault X reads price from Curve pool Y. Pool Y has remove_liquidity which
   triggers attacker callback. Inside callback, get_virtual_price returns inflated value.
   X's mint/borrow logic uses this stale price.
```

**Verification**: `scripts/web3/foundry_corpus/ReadOnlyReentrancy.t.sol.template`

---

## Pattern 4: Cross-Chain Replay (no chainId in domain)

**Class**: Signature
**Historical losses**: Multiple bridges and signature-based protocols

**Mechanism**: EIP-712 domain separator built once at construction, doesn't include chainId. Same signed message valid on testnet → mainnet, or L1 → L2 fork.

**Detection signals**:
- `DOMAIN_SEPARATOR` computed in `constructor` (immutable)
- No `_buildDomainSeparator()` per-call
- No chainId check anywhere

---

## Pattern 5: EIP-1271 Trust Lying

**Class**: Signature verification
**Historical losses**: Smart-contract wallet exploits

**Mechanism**: Protocol accepts EIP-1271 `isValidSignature(hash, sig)` from any contract. Malicious contract returns valid magic value for any input. Bypasses sig check entirely.

**Detection signals**:
- Code calls `IERC1271(signer).isValidSignature(...)`
- No fallback to ECDSA-only path for EOAs
- Signer can be ANY contract user-provided

---

## Pattern 6: Storage Slot Collision (Proxy Upgrade)

**Class**: Upgradeability
**Historical losses**: Audius ($1.1M, July 2022), various

**Mechanism**: New implementation has different state variable ORDER. Storage slot 5 was `lastUpdate` in V1, becomes `admin` in V2. Old data corrupts new logic.

**Detection signals**:
- Upgradeable proxy
- Implementation V1 → V2 has variable reorder
- No `__gap` placeholder

---

## Pattern 7: Initialization Race

**Class**: Access control
**Historical losses**: Multiple proxies hijacked

**Mechanism**: Implementation deployed but not initialized atomically. Attacker calls `initialize()` first, becomes admin.

**Detection signals**:
- `initialize()` function public
- No `initializer` modifier or it doesn't check `msg.sender`
- Deploy and init in separate txs

---

## Pattern 8: Permit2 Phishing Surface

**Class**: Approval trap
**Historical losses**: Ongoing, $millions per phishing campaign

**Mechanism**: User pre-signs Permit2 approval for "spender = malicious_contract". Or signs witnesseed permit with wrong witness data trusting frontend.

**Detection signals**:
- Frontend doesn't display ACTUAL spender in user-readable form
- Witness type not displayed in detail
- Permit2 with large allowance

---

## Pattern 9: Withdrawal Queue Cancel Cascade

**Class**: Griefing
**Historical losses**: Smaller, multiple

**Mechanism**: Withdrawal queue has cancel function. Attacker submits many withdrawals, cancels at moments to grief honest users / manipulate epoch.

**Detection signals**:
- Withdrawal queue exists
- Cancel function callable
- No anti-spam mechanism

---

## Pattern 10: Liquidation MEV / Profit Underflow

**Class**: Liquidation
**Historical losses**: Aave/Compound minor; mainly liquidator-side

**Mechanism**: Liquidator profit calculation underflows when collateral price drops further during execution. Bad debt socialised to LPs.

**Detection signals**:
- Liquidation with fixed bonus%
- No price-window check
- No bad-debt absorption mechanism

---

## Pattern 11: Same-Block TWAP Manipulation

**Class**: Oracle
**Historical losses**: ~$50M across protocols

**Mechanism**: TWAP observation window too short OR price-impact same-block usable. Attacker manipulates pool price in tx[N], reads stale TWAP in tx[N+1] same block.

**Detection signals**:
- Uniswap V2/V3 TWAP used
- Window < 30 minutes
- Or single-pool TWAP without depth

---

## Pattern 12: Approve+TransferFrom Race (approve(0) workflow)

**Class**: ERC-20 race
**Historical losses**: Minor, persistent class

**Mechanism**: User calls `approve(spender, X)` while previous `approve(spender, Y)` not yet spent. Spender frontruns: spends Y first, then spends new X = total Y+X stolen.

**Detection signals**:
- Token uses standard `approve` (not increaseAllowance)
- Critical spenders

---

## Pattern 13: ERC777 Callback Reentrancy

**Class**: Token surprise
**Historical losses**: imBTC ~$25M, multiple

**Mechanism**: Protocol thinks it's using "safe" ERC-20. ERC-777 token has `tokensReceived` callback. During `safeTransfer`, callback re-enters protocol.

**Detection signals**:
- Protocol accepts arbitrary tokens
- Uses `safeTransfer` from OpenZeppelin (no reentrancy guard on caller)
- Token whitelist absent or weak

---

## Pattern 14: Block.timestamp Manipulation

**Class**: Time
**Historical losses**: Minor

**Mechanism**: Miner/validator manipulates timestamp ±15s. Used as randomness source, deadline, lock unlock.

**Detection signals**:
- `block.timestamp` used for randomness
- Deadlines within ±60s of block

---

## Pattern 15: Off-By-One in Loop

**Class**: Numerical
**Historical losses**: Various, often DoS

**Mechanism**: `for (i=0; i<arr.length-1; i++)` misses last element. Or `i<=arr.length` overflows.

---

## Pattern 16: Reentrancy via NFT onERC721Received

**Class**: Reentrancy
**Historical losses**: Multiple protocols

**Mechanism**: Protocol uses `safeTransferFrom` for NFTs during liquidation/auction. Receiver callback re-enters.

**Detection signals**:
- `safeTransferFrom(IERC721)` used inside critical path
- No reentrancy guard

---

## Pattern 17: State Migration Assumption Broken

**Class**: Upgrade
**Historical losses**: Various

**Mechanism**: V1 → V2 migration assumes initial state. Edge case in production state breaks migration.

**Detection signals**:
- `_migrateV1ToV2()` function
- Assumes certain state preconditions

---

## Pattern 18: Signature Malleability

**Class**: Crypto
**Historical losses**: Pre-EIP-2 era; some lingering

**Mechanism**: ECDSA signature has 2 valid forms (high-s, low-s). Old code accepts either. Replay possible with different sig same content.

**Detection signals**:
- `ecrecover` direct usage
- No `s < SECP256K1_N / 2` check

---

## Pattern 19: Gas Refund Griefing (pre-EIP-3529)

**Class**: Gas
**Historical losses**: Older incidents

**Mechanism**: SELFDESTRUCT gas refund could be exploited for gas extraction. Post-EIP-3529 (London) refunds capped.

**Detection signals**:
- Pre-London chain (rare now)

---

## Pattern 20: Flash Mint Manipulation

**Class**: Tokenomics
**Historical losses**: Pickle Finance ($20M), various

**Mechanism**: Token has flash mint feature (mint then burn within tx). Some protocols don't account for this, treat mint as real supply increase.

**Detection signals**:
- DAI flash mint
- Frax flash mint
- Protocol reads `totalSupply()` for accounting

---

## Pattern 21: EIP-4337 Bundler Griefing

**Class**: Account abstraction
**Historical losses**: Theoretical / minor

**Mechanism**: Malicious UserOp consumes bundler resources without paying. Paymaster validation bypass.

**Detection signals**:
- Custom paymaster with complex validation
- No simulation result validation

---

## Pattern 22: Intent-Based Settlement Race

**Class**: Intent protocols
**Historical losses**: Emerging (CowSwap-likes)

**Mechanism**: Filler frontruns intent. Or settles intent on multiple chains.

**Detection signals**:
- Filler selection mechanism
- Cross-chain intents
- No nonce/replay protection per chain

---

## Pattern 23: Restaking Slash Race

**Class**: Restaking
**Historical losses**: EigenLayer-likes, emerging

**Mechanism**: Attacker withdraws before slash propagates from AVS to core. Slash hits empty position.

**Detection signals**:
- Withdrawal delay < slash propagation delay
- AVS-to-core slash communication async

---

## Pattern 24: Cross-Rollup Desync

**Class**: L2 messaging
**Historical losses**: Theoretical, emerging

**Mechanism**: L1→L2 message takes 10 min, L2→L1 takes 7 days. State drifts during window. Attacker exploits drift.

---

## Pattern 25: Modular Protocol Module-Swap

**Class**: Diamond proxy, modular
**Historical losses**: Various

**Mechanism**: Protocol allows hot-swap of modules. Attacker triggers swap mid-tx, breaks invariants.

**Detection signals**:
- Diamond proxy (EIP-2535)
- `diamondCut` callable not just by admin
- Or module registry without strict access

---

## Pattern 26: MEV-Boost Relay Trust

**Class**: PBS
**Historical losses**: Theoretical

**Mechanism**: Relay equivocates blocks. Proposer fooled into signing two blocks.

**Detection signals**:
- Smart-contract trusts MEV-Boost block timing
- Same-block dependencies

---

## Pattern 27: Donation Attack Timing

**Class**: Vault math
**See Pattern 1**.

---

## Pattern 28: Liquidator Profit Underflow

**See Pattern 10**.

---

## Pattern 29: Withdrawal Queue Cancel Cascade

**See Pattern 9**.

---

## Pattern 30: Cross-Chain Replay

**See Pattern 4**.

---

## Pattern 31: Sequencer Downtime Exploitation

**Class**: L2
**Historical losses**: Theoretical (Arbitrum, Optimism)

**Mechanism**: L2 sequencer paused → L2 reads/writes paused. Liquidations don't fire. Borrowers escape.

**Detection signals**:
- L2 deployment
- Liquidation logic doesn't check sequencer status (Chainlink sequencer uptime feed)

---

## Pattern 32: Approve+TransferFrom Race

**See Pattern 12**.

---

## Pattern 33: DeFi Lego Invariant Cascade

**Class**: Composability
**Historical losses**: Many composable exploits

**Mechanism**: Protocol A reads from B. B has invariant violation under specific market condition. A's invariant breaks too.

**Detection signals**:
- Protocol depends on external oracle/protocol value
- That external can be manipulated for cost < expected profit on A

---

## Pattern 34: Token Donation to Pool

**Class**: AMM
**Historical losses**: Various

**Mechanism**: Attacker directly transfers token to AMM pool. Manipulates `reserves`. Affects price.

**Detection signals**:
- Pool reads reserves via `balanceOf(this)` not sync
- Or sync function callable
- Spot price used downstream

---

## Pattern 35: Function Selector Collision

**Class**: Diamond / proxy
**Historical losses**: Minor

**Mechanism**: Two functions with different signatures but same 4-byte selector (hash collision). Wrong implementation called.

**Detection signals**:
- Diamond proxy with many facets
- Or custom selector routing
- No collision check at upgrade time

---

## Pattern Index for Quick Reference

| # | Pattern | Class | Lowest Tier | Key Tool |
|---|---------|-------|-------------|----------|
| 1, 2 | ERC-4626 inflation | Vault | T3 | vault_hunter |
| 3 | Read-only reentrancy | Reentrancy | T4 | readonly_reentrancy detector |
| 4 | Cross-chain replay | Sig | T3 | crypto_audit |
| 5 | EIP-1271 trust | Sig | T4 | eip1271_lying detector |
| 6 | Storage collision | Upgrade | T5 | storage_layout_drift |
| 7 | Init race | Access | T1 | init_race_detector |
| 8 | Permit2 phishing | Approval | T1 | manual |
| 10 | Liquidation MEV | Lending | T4 | lending_hunter |
| 11 | Same-block TWAP | Oracle | T4 | same_block_manipulator |
| 13 | ERC-777 reentrancy | Token | T3 | token_compatibility_tester |
| 31 | Sequencer downtime | L2 | T1/T3 | op_stack_quirks |
| 33 | Lego cascade | Composability | T4 | composability_matrix |

---

## How New Patterns Get Added

When rekt.news or Cantina publishes a new $1M+ exploit:
1. Extract mechanism
2. Add as new pattern here
3. Add detection signals
4. Add hypothesis template
5. Add Foundry test template if applicable

Keep this file living. The toolkit improves with every new known exploit.
