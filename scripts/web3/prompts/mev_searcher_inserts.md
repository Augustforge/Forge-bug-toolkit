# Prompt: MEV Searcher Inserts

Lens: a searcher with capital + flashloan + mempool visibility can insert an adversarial tx between the victim's tx and the target state. What patterns enable extraction?

> Examples: Curve readonly-reentrancy ($70M, 2023), sandwich on every DEX, JIT liquidity on UniV3, every flashloan exploit ever.

## Questions

1. **Public mempool exposure**: protocol on a chain with public mempool (ETH mainnet, BSC)? L2 with private order flow?
2. **Atomic profit possible?** Can searcher: take flashloan → exploit → repay in one tx?
3. **Sandwich surface**: large swap without slippage protection? AMM rebalance? Liquidation?
4. **JIT liquidity**: provide liquidity right before fee-generating tx, remove after
5. **Backrun**: protocol creates exploitable state (e.g., oracle update without guard) — searcher backruns
6. **Frontrun setup**: user setup tx (approval, deposit) — searcher frontruns with adversarial state change
7. **Capital required**: flashloan-accessible? (Aave/Maker/Balancer pools)
8. **Cross-protocol**: profit only possible by chaining N protocols? (Curve+Convex+Aave class)

## Specific exploit classes

- **Sandwich**: large swap → MEV inserts buy before, sell after
- **Liquidation race**: oracle update → searcher liquidates before user can rescue
- **Flashloan + price manipulation**: borrow → manipulate pool → trigger oracle dependent action → restore → repay
- **Readonly reentrancy**: read external protocol state mid-call when state is invalid
- **JIT LP**: provide liquidity 1 block before fee tx, remove next block
- **Backrun mint**: oracle stale → mint at favourable price → wait normal mint to bring back

## MEV venue specifics

- **Ethereum mainnet**: Flashbots, MEV-Boost — searcher pays validator for inclusion
- **L2s** (Arbitrum/Optimism/Base): private sequencer, BUT public order flow visible — different MEV surface
- **Solana**: Jito bundles, sequencer-level MEV
- **DEX-specific**: CoW/UniswapX/1inch Fusion — solver-level MEV, different attack surface

## Output

1. **Attack pattern**: sandwich / liquidate / backrun / flashloan / JIT
2. **Code location**: where state change creates extractable value
3. **Capital required**: flashloan amount + gas
4. **Profit estimate**: extraction value
5. **Mitigation gap**: slippage / commit-reveal / TWAP / private mempool — what's missing
6. **Severity**: Medium (small per-tx extraction) or High (large one-shot manipulation)

## Anti-pattern

Don't say "use Flashbots" — that is a user-side mitigation. Find the protocol-side gap that enables extraction in the first place.

---

## Source:

(paste DEX / AMM / lending / batch-auction code where ordering or atomic state matters)
