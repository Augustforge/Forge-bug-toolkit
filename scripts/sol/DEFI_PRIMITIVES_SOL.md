# Solana DeFi Primitives — Math Models & Bug Surfaces

| Primitive | Implementations | Specific bug surfaces |
|---|---|---|
| **Concentrated Liquidity (CLMM)** | Raydium CLMM, Orca Whirlpools | Tick array account validation (Raydium 2024), sqrt-price overflow at extreme ticks, tick crossing math, fee accumulation drift |
| **Stableswap** | Saber-class | A-coefficient manipulation, imbalanced pool drain, removal slippage |
| **Bonding Curves** | pump.fun, MoonPump | Graduation threshold gaming, anti-sniper bypass, withdrawal trust, virtual reserves manipulation |
| **Lending Pools** | Solend, MarginFi, Kamino | Flash loan state flag (Marginfi 2025), health factor paths, oracle dependency, exchange rate precision (Kamino), bad debt absorption |
| **LST / Restaking** | Marinade, Jito, Sanctum | Withdrawal queue FIFO violation, slash race, LST oracle TTL, fee accrual rounding |
| **Orderbook DEX** | OpenBook v2, Phoenix | Order matching priority, self-trade detection, partial fill atomicity, maker rebate underflow |
| **Bridges** | Wormhole, Allbridge, Mayan | VAA replay, signature account validation (Wormhole 2022), guardian set transitions, chainId binding |
| **Memecoin Launchers** | pump.fun, MoonPump | Bonding curve gaming, graduation threshold, anti-sniper bypass, fair launch fairness |
| **Token-2022 Wrappers** | Various | Transfer hook reentrancy, confidential transfer ZK, interest-bearing rate manipulation |
| **Compressed NFT** | Bubblegum/Metaplex | Merkle proof verification, canopy depth abuse, concurrent mutation race |
| **ZK State Compression** | Light Protocol | Validity proof completeness, state root attacks, nullifier set, batch verify |
| **MEV Infrastructure** | Jito, MEV-relay | Bundle inclusion, cross-slot sandwich, validator equivocation, priority fee front-running |
| **Governance** | Squads, Realms, Spl-Governance | Threshold drift, durable nonce admin (Drift 2026), zero-timelock, approval revocation gaps |
| **Insurance / Coverage** | Various | Claim verification trust, vote-based payout gaming, premium calc drift |

## Common Math Surfaces

### Share Pricing (vault/lending)
- Exchange rate calc: `share_value = (assets * supply) / total_assets`
- **Bug surface**: rounding direction asymmetry between mint and redeem → profit round-trip (Sec3 pattern)

### AMM Constant Product / Concentrated
- `x * y = k` or `liquidity = sqrt(x * y)`
- **Bug surface**: sqrt overflow at extreme ranges, tick boundary off-by-one, fee deducted before or after math

### Interest Accrual
- Compound vs linear interest
- Time delta from `Clock::get()`
- **Bug surface**: time delta overflow, accrual ordering between deposits/withdrawals

### Liquidation Math
- Health factor: `collateral_value * threshold / debt_value`
- Liquidation bonus: `bonus_bps / 10000`
- **Bug surface**: oracle manipulation (Mango 2022), partial liquidation incentive, dust amounts

## DeFi-Specific Solana Quirks

- **Compute Unit budget** affects complex DeFi math (sqrt, log, exp) — could DoS
- **Account model** means liquidity pools are separate accounts → validation gap surface
- **PDA derivation** for vault authorities — seeds must be unique
- **Token-2022 extensions** in DeFi pools — must handle hooks, transfer fees, freeze
