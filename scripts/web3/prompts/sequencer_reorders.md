# Prompt: Sequencer Reorders

Lens: L2 protocols (Arbitrum/Optimism/Base/zkSync/Linea/Scroll) rely on centralized sequencer. What if sequencer reorders txs for MEV? Censors? Goes down?

> Examples: Arbitrum sequencer outages, Optimism downtime, theoretical L2 censoring of liquidations.

## Questions

1. **Does protocol assume tx ordering?** "User submits A then B, expects A processed first"
2. **What if sequencer reorders A and B?** Liquidation race? Sandwich enabled? MEV extracted?
3. **What if sequencer delays specific user?** Censorship — liquidation blocked, governance vote missed
4. **What if sequencer down?** Escape hatch via L1? Force-include mechanism?
5. **L1 vs L2 timing**: assumes block.timestamp monotonic? Same as L1? (Arbitrum L2 timestamp lags L1)
6. **block.number meaning**: L1 block? L2 block? Different chains different semantics
7. **MEV via sequencer**: PGA possible? Public mempool? Private order flow?

## Chain-specific

- **Arbitrum**: sequencer enforced order, NO public mempool. L1 force-include after 24h
- **Optimism**: similar — sequencer order, no public mempool
- **Base** (OP-stack): same as Optimism + Coinbase-operated sequencer
- **zkSync Era**: priority queue from L1, sequencer-ordered L2
- **Linea/Scroll**: zk-rollup sequencer can prove arbitrary ordering — trust assumption

## Specific bug classes

- **Slippage attacks via sequencer reorder**: protocol assumes price doesn't change between user's swap A → expects price, sequencer can insert B before A
- **Liquidation race**: keeper submits liquidation, sequencer reorders user's "rescue" tx first (or censors keeper)
- **Governance**: signer submits "rescue" proposal, sequencer reorders attacker's drain first
- **TWAP manipulation on L2**: shorter blocktime → cheaper to manipulate TWAP

## Output

1. **Code location**: where ordering matters
2. **Reorder scenario**: which txs in which (un)expected order
3. **Profit/loss**: who pays, who gains
4. **L1 force-include feasibility**: can user escape?
5. **Severity**: usually Medium-High (sequencer rarely fully malicious, but MEV/censoring common)

## Anti-pattern

Don't say "L2 is decentralized" — most L2s have single sequencer in 2026. Check actual decentralization status.

---

## Source:

(paste L2-deployed contracts + protocol's assumptions about ordering)
