# Oracle Manipulation Checklist (6 patterns) — Immunefi V03 Top 10 gap

For every contract that reads prices/rates — go through all the items.

## 1. Single-source oracle
- [ ] The contract reads price from only one source (Chainlink / Uniswap TWAP / custom feed)
- [ ] No fallback on unavailability
- [ ] No cross-validation (comparison with another feed)
- **Risk:** compromise of one source = full compromise of the price

## 2. Manipulable AMM oracle (spot price)
- [ ] `getReserves()` is used directly from a Uniswap V2 pool
- [ ] `slot0()` from Uniswap V3 is used without TWAP
- [ ] No protection against flash loan manipulation
- **Risk:** flash loan → swap → read price → swap back. Mango ($116M), Cream Finance ($130M)
- **Fix:** use TWAP with a period ≥ 30 minutes, or Chainlink

## 3. Stale price data
- [ ] Chainlink's `latestRoundData()` doesn't check `updatedAt`
- [ ] No heartbeat check (max age)
- [ ] A frozen price can be exploited during a market crash
- **Pattern in code:**
  ```solidity
  (, int256 price, , uint256 updatedAt, ) = oracle.latestRoundData();
  // ❌ MISSING: require(updatedAt > block.timestamp - 3600, "stale");
  ```

## 4. Decimals mismatch
- [ ] The oracle returns a price with decimals = 8 (Chainlink standard)
- [ ] The contract expects decimals = 18 — no conversion
- [ ] When integrating an ERC20 with non-standard decimals (USDC=6) they forgot to scale
- **Risk:** off-by-1e10 errors, price 10^10 times larger/smaller than real

## 5. Missing minAnswer/maxAnswer bounds
- [ ] Chainlink has circuit breakers (if price < minAnswer, minAnswer is returned)
- [ ] The contract doesn't check whether `price == minAnswer` or `price == maxAnswer`
- [ ] During extreme market movement — a fixed price is exploited
- **Real case:** Venus Protocol during the LUNA crash

## 6. Cross-chain oracle inconsistency (bridges)
- [ ] The price arrives via a bridge (LayerZero, Wormhole)
- [ ] No validation that the message isn't replayed
- [ ] Latency between chains permits arbitrage
- **Fix:** require monotonic nonce + freshness check + multiple validators

---

## Manual checks (auto tools won't cover)

```bash
# Find all oracle reads in the code
grep -rn "latestRoundData\|getReserves\|slot0\|getPriceOf" contracts/

# Check decimals mismatch
grep -rn "oracle\." contracts/ | grep -v "decimals()"
```

## Confirmation pattern (Foundry)

```solidity
function testFlashLoanOracleManipulation() public {
    uint256 priceBefore = target.getPrice();

    // Flash loan from Aave/Balancer/dYdX
    flashLoan.flashLoan(largeAmount);
    // inside flash loan callback:
    //   1. swap to manipulate pool
    //   2. call target function that reads price
    //   3. swap back
    //   4. repay flash loan

    // Verify price was manipulated and target was exploited
    uint256 priceDuring = target.getPrice();
    assertGt(priceDuring, priceBefore * 10);
}
```

## Solodit search keywords
`oracle manipulation`, `price feed`, `flash loan oracle`, `TWAP`, `single source`, `Chainlink stale`, `decimals mismatch`
