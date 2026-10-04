# DeFi Primitives — Class-Specific Bug Catalogue

For each DeFi primitive, list specific bug classes that affect it. Used in J3 (Specialized Analysis).

---

## Stableswap (Curve-like)

### Architecture
- Constant sum + invariant `D` adjusted by amplification coefficient `A`
- Used by Curve, Saddle, Ellipsis, Platypus

### Bug classes
1. **Imbalanced pool math**: when ratio deviates significantly, math becomes non-linear; rounding can favor attacker
2. **A coefficient manipulation**: if admin can change `A`, may break invariant during transition
3. **Liquidity removal slippage**: `remove_liquidity_one_coin` has specific math; can over-claim due to rounding
4. **TWAP windowing**: stableswap pools often used as oracle; window too short = manipulatable
5. **Read-only reentrancy**: see Curve 2023 attack pattern

### Detection
- `_get_y()`, `get_dy()`, `get_virtual_price()` — read these carefully
- Check for `nonreentrant` on view-mode functions (Curve doesn't have this!)
- Verify A coefficient bounds

---

## Concentrated Liquidity (Uniswap V3 / Algebra / Forks)

### Architecture
- Liquidity concentrated within tick range
- `sqrtPriceX96` price representation
- Position NFTs

### Bug classes
1. **Tick boundary math**: prices at exact tick boundaries cause off-by-one issues
2. **sqrtPriceX96 overflow**: large numbers, easy to overflow without care
3. **Position liquidity calc**: complicated math for partial removes
4. **JIT (just-in-time) liquidity attacks**: providing liquidity for 1 block to capture fees
5. **Oracle manipulation via single-tick liquidity**: provide tiny liquidity at edge tick → manipulate spot price

### Detection
- `liquidityGross` / `liquidityNet` accounting
- Tick spacing math
- Fee growth tracking

---

## veToken Voting (Curve / Convex / Velodrome / Solidly)

### Architecture
- Lock token for X time → get veToken with decaying voting power
- veTokens vote on gauges → gauges direct emissions
- Bribes incentivize specific votes

### Bug classes
1. **Lock decay edge cases**: lock expiry exactly at block boundary
2. **Vote bribe game theory**: bribes can break vote alignment with protocol health
3. **Gauge weight manipulation**: flash-lock just before vote (some impls allow)
4. **Bribe-rebribe loop**: protocol bribes its own veToken holders with treasury
5. **Time-weighted vote replay**: vote counted multiple times across windows

### Detection
- Time math (`block.timestamp / WEEK * WEEK` patterns)
- Lock extension vs new lock semantics
- Gauge controller delegation logic

---

## Bonding Curve (Token issuance)

### Architecture
- Token price = f(supply). Continuous mint/burn.
- Used in Friend.tech-likes, social tokens, Curve-like LP

### Bug classes
1. **Continuous mint/burn invariant**: balance must equal integral of curve
2. **Reserve ratio drift**: if curve has reserve, ratio must stay constant
3. **Sandwich on buy/sell**: small slippage tolerance + frontrun
4. **Price impact rounding**: large purchase → rounding may favor protocol or attacker

### Detection
- `getBuyPrice(supply, amount)` math
- Reserve ratio invariant tests

---

## AMM TWAP (Uniswap V2/V3 oracle)

### Architecture
- Cumulative price stored at each interaction
- Average computed over window

### Bug classes
1. **Window manipulation**: short window (< 30 min) → manipulatable in 1-2 blocks
2. **Observation cardinality**: V3 oracles require observation array configured by LP
3. **Single-pool TWAP without depth**: low-liquidity pool can be manipulated cheaply

### Detection
- TWAP window length
- Multi-pool aggregation present?
- Sanity-check vs Chainlink

---

## Auction (Dutch / English / Sealed)

### Architecture
- Price discovery via competitive bidding
- Various end conditions

### Bug classes
1. **Bid griefing**: bid just before deadline, prevent settlement
2. **Last-minute snipe via gas escalation**
3. **Settlement timing manipulation**: block.timestamp ±15s matters
4. **Refund logic**: if all bids refund except winner, who pays for partial refunds?

### Detection
- Bid extension logic
- Refund flow
- Settlement preconditions

---

## Rebase Tokens (AMPL-like)

### Architecture
- `balanceOf(user)` changes via supply rebase
- User balances stored as `shares`, total tracked separately

### Bug classes
1. **Index drift across operations**: integer rounding accumulates
2. **Cross-protocol confusion**: protocols not knowing it's a rebase token treat balance as static
3. **Snapshot timing**: rebase events at block boundary

### Detection
- Token assumption in protocols
- Cross-protocol integration with rebase tokens

---

## Fee-on-Transfer Tokens

### Architecture
- Transfer deducts fee, recipient gets less

### Bug classes
1. **Recipient credit calc**: protocol assumes full amount received
2. **Double-counting**: protocol charges fee on transfer + fee on transferFrom
3. **Round-trip drift**: deposit + withdraw doesn't return same amount

### Detection
- Token whitelist
- `_actualReceived = balanceAfter - balanceBefore` pattern (correct)
- Or assumes parameter equals received (bug)

---

## ERC-4626 Vault

### Architecture
- Shares represent fractional ownership
- `convertToShares`, `convertToAssets`, `deposit`, `withdraw`, `mint`, `redeem`

### Bug classes
1. **Donation attack**: transfer assets without minting shares → inflate share price
2. **First-depositor inflation**: 1 share for any amount, then victim deposit rounds to 0
3. **Redeem rounding direction**: must round in favor of vault, not user
4. **`maxDeposit` / `maxWithdraw` lying**: protocol returns higher than actual
5. **Async withdrawal griefing**: withdrawal queue manipulation

### Detection
- Virtual shares offset present?
- `_decimalsOffset()` configured?
- First-deposit protection?

---

## Liquid Staking (Lido / Rocket / Frax)

### Architecture
- ETH staked, derivative token (stETH/rETH/frxETH) issued
- Rewards accrue to derivative

### Bug classes
1. **Slash distribution**: how slashes propagate from validators to token holders
2. **Queue position**: withdrawal queue ordering, can it be jumped?
3. **Fee accrual timing**: when fees credited vs when withdrawable
4. **Oracle for ETH/stETH ratio**: how is rate calculated, manipulatable?
5. **Depeg from peg ratio (~1:1) — recovery mechanism**

### Detection
- Withdrawal queue mechanics
- Rate oracle source
- Slash insurance mechanism

---

## Cross-Chain Messaging (LayerZero / Wormhole / Axelar / CCIP)

### Architecture
- Source chain sends message; destination chain receives + executes
- Various verification mechanisms (DVNs, guardians, validators, light clients)

### Bug classes
1. **Replay attacks**: same message processed twice on destination
2. **Message ordering**: assumed FIFO, actually not guaranteed
3. **DVN compromise / collusion**: enough DVNs validate malicious message
4. **Bridge insolvency**: cross-chain accounting drift
5. **Force-finalization**: timeout messages without verification

### Detection
- Nonce tracking
- Verification redundancy (M-of-N where M is sufficient?)
- Liquidity reserves model

---

## Lending Protocols (Aave / Compound forks)

### Architecture
- Suppliers deposit, borrowers borrow with collateral
- Interest rate model, liquidation incentive

### Bug classes
1. **Liquidation MEV**: liquidator overpays due to oracle staleness
2. **Interest model edge cases**: rate explodes at high utilization
3. **Bad debt socialization**: liquidator underpaid, debt absorbed by suppliers
4. **Collateral oracle manipulation**: borrower deposits manipulated collateral
5. **Flash-loan repayment race**: borrow, manipulate, repay → state inconsistent mid-tx

### Detection
- Liquidation profit calc
- Interest rate at edge utilization
- Bad debt absorption mechanism (insurance fund?)
- Oracle source diversity

---

## Synthetic Assets (Synthetix / UMA / Mirror)

### Architecture
- Collateralized debt position issues synthetic
- Oracle determines liquidation threshold

### Bug classes
1. **Oracle dependence**: synthetic value derived entirely from oracle
2. **Liquidation thresholds**: too tight = MEV; too loose = bad debt
3. **Debt position math**: socialized debt with global pool
4. **Snapshot timing for liquidation**

### Detection
- Oracle update frequency
- Liquidation incentive
- Global debt pool math

---

## Restaking (EigenLayer-like)

### Architecture
- LSTs/ETH restaked into security pool
- AVSs (services) consume security, can slash for misbehavior
- Withdrawal delay enforced

### Bug classes
1. **Slash race**: withdraw before slash propagates
2. **AVS commitment**: AVS slashing logic itself bugs
3. **Withdrawal queue ordering**
4. **Reward distribution**: how rewards from multiple AVSs allocated
5. **Operator collusion**: multiple operators slash each other or collude

### Detection
- Withdrawal delay vs slash delay
- AVS slashing logic review
- Operator selection / removal

---

## Insurance Protocols (Nexus / InsurAce)

### Architecture
- Capital pool covers risks
- Claims verified by voters or oracles

### Bug classes
1. **Claim verification**: bad voting incentive
2. **Capital lockup**: voters can't withdraw during active claims
3. **Premium calc**: under-priced premiums → insolvency
4. **Bond-jumping**: vote on profitable side of claim

### Detection
- Vote incentive alignment
- Premium model

---

## Yield Aggregators (Yearn / Beefy)

### Architecture
- Strategy contracts deposit user assets into other protocols
- Fees charged on profit

### Bug classes
1. **Strategy switching**: timing of switch can extract value
2. **Fee calc**: charged on gross vs net profit
3. **Share dilution at rebalance**: rebalance issues new shares mispriced
4. **Underlying protocol invariant break**: aggregator inherits underlying bugs

### Detection
- Rebalance authorization
- Fee accrual timing
- Underlying protocol dependency scope

---

## Stablecoins (DAI / FRAX / LUSD)

### Architecture
- Peg defense via collateral, redemption, market operations

### Bug classes
1. **Peg defense mechanism**: PSM (Peg Stability Module) bugs
2. **Redemption math**: fixed-rate or market-rate redemptions
3. **Depeg recovery**: how does protocol respond at +/-5%?
4. **Stability fee accrual**

### Detection
- PSM swap fees
- Redemption permissions
- Stability fee model

---

## DEX Aggregators (1inch / Paraswap / Cowswap)

### Architecture
- Route across multiple DEX sources
- Quote API + on-chain executor

### Bug classes
1. **Routing trust**: server lies about route, user signs malicious calldata
2. **Per-hop slippage**: overall slippage OK but intermediate hops drainable
3. **Calldata injection**: malicious calldata in route causes unexpected behavior
4. **Fee accrual**: protocol fee on hidden slippage

### Detection
- minOut computed client or server?
- Per-hop validation
- Calldata signature verification

---

## Account Abstraction (ERC-4337)

### Architecture
- UserOp → EntryPoint → smart-account validation → execution
- Bundler, Paymaster

### Bug classes
1. **Bundler griefing**: validation passes simulation, fails on-chain
2. **Validation bypass**: signature/permission check bypassable
3. **Paymaster abuse**: paymaster pays for ops it shouldn't
4. **Aggregated signature attacks**: aggregator forges sig

### Detection
- Validation logic complexity
- Paymaster terms
- Aggregator trust

---

## How to use this file

When `/deephunt` J3 specialized phase runs:
1. Identify which primitives are in target
2. Open relevant section above
3. Apply each bug class as hypothesis
4. Verify each via tools or manual analysis

Each section's "Detection" subsection → quick grep/regex patterns to find suspicious code.
