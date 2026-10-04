# Prompt: Oracle Lies

Lens: protocol trusts oracle/DVN/price feed. What if it returns adversarial value? Most "oracle hacks" are not code bugs, but the **protocol's assumption** that the oracle is honest/fresh/bounded.

> Examples: Cream Finance ($130M, 2021), Mango Markets ($117M, 2022), KelpDAO ($292M, 2025 — single DVN trust).

## Questions

1. **Where do oracle reads happen?** Grep `latestAnswer | latestRoundData | price() | getPrice | getPyth | getRate | exchangeRate`
2. **What if oracle returns 0?** Division-by-zero? Free mint? Bypassed check?
3. **What if oracle returns MAX_UINT?** Overflow? Liquidation of everyone? Mint cap broken?
4. **What if oracle returns stale value?** Check `updatedAt` timestamp — is there a staleness guard? Bound? (>1 hour stale = stale in most protocols)
5. **What if oracle returns valid-but-extreme value?** $1 ETH? $100k USDC? Manipulation possible?
6. **What sources?** Single oracle vs N-of-M? Single sequencer vs decentralized?
7. **TWAP vs spot?** TWAP can be manipulated with large enough capital — what's the manipulation cost vs payoff?
8. **Confidence interval (Pyth)?** Does protocol check `priceFeed.conf` is reasonable? (Drift v2 missed this — Critical)

## Specific oracles

- **Chainlink**: check `latestRoundData()` returns `answer > 0`, `updatedAt > block.timestamp - HEARTBEAT`, `answeredInRound >= roundId`
- **Pyth Lazer**: check slot staleness, confidence interval, authority pin
- **Uniswap V3 TWAP**: check observation cardinality, manipulation cost
- **Custom oracles**: who can push? bond requirement? slashing on lie?

## Output

For each "what if oracle lies" hypothesis:
1. **Code location**: file:line where protocol reads oracle
2. **Adversarial value**: 0 / MAX / stale / extreme / manipulated
3. **Path to value**: which functions to call with this oracle state
4. **Mitigation gap**: what the protocol should check but does not
5. **Severity**: typically High/Critical for economic protocols

## Anti-pattern

Don't ask "is there an oracle?" — ask "where exactly is trust placed without verification, and what's the cost to lie?"

---

## Source:

(paste relevant contracts that read oracle / DVN below)
