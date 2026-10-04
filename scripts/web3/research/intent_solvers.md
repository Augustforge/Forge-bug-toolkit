# Intent-Based Solvers

**Status**: studying
**Priority**: high
**Why hunter cares**: UniswapX/CoWSwap solver pools — solver-side MEV is grey area, batch auction surface largely unexplored. Each major intent protocol = $500k+ Immunefi typically.

## Core concept

Traditional DEX: user submits exact swap, on-chain executes. **Intent-based**: user signs "I want X for at least Y", solver competes to fulfill at best price. Solver pays gas, executes swap, takes spread.

Architecture:
1. User signs intent off-chain (gasless)
2. Solver pool (or single solver) picks up intent
3. Solver constructs optimal route (possibly multiple DEXes)
4. Solver submits execution tx — collects intent
5. User receives result, solver takes profit (or pays loss)

## Top bug classes

### 1. Solver MEV / collusion
- Single solver wins all auctions (no real competition)
- Solver provides worse price than possible (extracts value from user)
- Solver coordinates with searcher (re-extracts via sandwich)
- Solver fronts user's intent on adjacent protocol

### 2. Batch auction manipulation
CoWSwap: multiple intents batched, single solver clears.
- Solver picks order to maximize self-profit
- Solver excludes profitable user intents
- Solver simulates competitive proposal but actually doesn't execute

### 3. Settlement races
- Two solvers submit conflicting executions — first-in wins
- Network reorg cancels solver's execution after user signed
- Permit replay across attempts

### 4. Signature replay across solvers
- User signs intent, multiple solvers race
- Solver A executes first, but solver B replays signature (different tx)?
- Permit2 / EIP-712 nonce reuse

### 5. Slippage / quote staleness
- User signs intent based on quote at T0
- Solver executes at T0 + 5s
- Price moved — should solver still execute? Cancellation mechanism?

### 6. Cross-chain intent fulfillment (Across)
- User wants ETH→USDC on Polygon, has ETH on mainnet
- Solver bridges, swaps, delivers
- Multi-chain settlement race

### 7. Solver bond / collateral
- Solver posts bond to participate
- Bond slashing for misbehavior — encoded correctly?
- Withdraw bond before slash propagates

## Implementations to read

### UniswapX
- Repo: https://github.com/Uniswap/UniswapX
- Architecture: Dutch auction with off-chain orderbook
- Key contracts: `ExclusiveDutchOrderReactor`, `DutchOrderReactor`
- Auction parameters: deadline, exclusive period

### CoWSwap
- Repo: https://github.com/cowprotocol/contracts
- Architecture: batch auctions every 5 minutes
- Key contracts: `GPv2Settlement`, `GPv2VaultRelayer`
- Solver competition: off-chain auction, on-chain settlement

### Across
- Repo: https://github.com/across-protocol/contracts-v2
- Architecture: cross-chain intent fulfillment via relayer network
- Key contracts: `SpokePool`, `HubPool`
- Settlement: optimistic with challenge period

### 1inch Fusion
- Architecture: Dutch auction over 1inch aggregator
- Limited public source

## Notable past bugs

- **CoWSwap early disclosures** — solver permission bugs
- **UniswapX** — historical exclusive period race conditions
- **Across** — bridge-bridge composability issues

## Hunting workflow once we reach `can-hunt`

1. Identify intent protocol
2. Check signature scheme:
   - EIP-712 domain separator correct?
   - Permit2 vs custom?
   - Replay protection across solvers / chains?
3. Check solver competition:
   - Single-solver fallback path?
   - Solver bond / slashing?
4. Check settlement:
   - Front-running by other solvers?
   - Reorg handling?
   - Quote staleness mitigation?
5. Cross-chain (if applicable):
   - Bridge integration trust assumption?
   - Settlement finality across chains?

## Active programs

- **Uniswap (incl UniswapX)** — Immunefi $2.25M cap
- **CoW Protocol** — Immunefi
- **1inch** — Immunefi
- **Across Protocol** — Immunefi

## To-author once can-hunt status is reached

- `scripts/web3/checklists/specialized/intent_solver.md` (extend existing `intent_based.md`)
- `scripts/web3/threat_models/solver_collusion.yaml`
- `scripts/web3/threat_models/intent_signature_replay.yaml`
- `scripts/web3/threat_models/batch_auction_manipulation.yaml`

## Reading list

1. **UniswapX whitepaper**
2. **CoWSwap docs** — solver guide
3. **Across whitepaper** — relayer economics
4. **"MEV in Intent-Based Markets"** — Flashbots research
5. **EIP-712 / Permit2 specs** — signing fundamentals

## Cross-link

- Existing `prompts/mev_searcher_inserts.md` — MEV lens applies
- Existing `prompts/frontend_compromised.md` — frontend signs intent
- Existing `checklists/specialized/dex_aggregator.md` — related
- Existing `checklists/specialized/intent_based.md` — base, expand
