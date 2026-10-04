# Hypothesis: DeFi Primitives Quirks

**Trigger**: target uses specific DeFi primitive (Stableswap, ConcentratedLiq, veToken, Bonding curve).

Cross-reference: see `DEFI_PRIMITIVES.md` (top-level doc) for full catalogue.

## Quick reference per primitive

### Stableswap (Curve-like)
Specific quirks:
- A coefficient transitions (admin changes)
- Imbalanced pool math non-linearity
- `remove_liquidity_one_coin` slippage favor

### Concentrated Liquidity (V3)
- Tick boundary math
- sqrtPriceX96 overflow at extremes
- Position liquidity calc on partial removes
- JIT (just-in-time) liquidity attacks

### veToken voting
- Lock decay over time
- Bribe game theory
- Gauge weight via flash-lock (if possible)

### Bonding curve
- Continuous mint/burn integral invariant
- Reserve ratio drift

### AMM TWAP
- Window size adequacy
- Observation cardinality
- Single-pool depth

### Rebase tokens
- Index drift across operations
- Cross-protocol confusion

### Fee-on-transfer
- Recipient credit calc
- Double-counting

### ERC-4626 vault
- Donation attack
- First-depositor inflation
- Redeem rounding direction

### Liquid staking
- Slash distribution
- Queue position
- Fee accrual timing

## Application

For each primitive in target:
1. Open this section
2. Read specific quirks
3. Apply as hypothesis
4. Build PoC if applicable

Most quirks have dedicated checklist files in `hypothesis/` or `specialized/` folder.
