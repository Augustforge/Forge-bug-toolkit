# Hypothesis: Oracle/Slippage Guard Bypass

**Trigger**: 2+ functions reach the same financial outcome, but one path has an oracle/slippage check and other doesn't.

**Real example**: Alchemix V3 had two allocation paths:
- `allocateWithSwap()` — used Curve swap with oracle validation
- `allocate()` — direct deposit, no oracle check
During wstETH/SFraxETH depeg, direct path allocated at par while market was at discount → instant NAV loss.

---

## Checklist

### 1. Map all paths to same outcome
- [ ] What's the "outcome" (e.g., minting shares, allocating to strategy, swapping)?
- [ ] List ALL functions that produce this outcome
- [ ] Group by: oracle-protected vs unprotected

### 2. Guard analysis
For each path, identify:
- [ ] Oracle source (Chainlink? Curve TWAP? Internal price?)
- [ ] Slippage bound (min amount out specified?)
- [ ] Sanity checks (price within X% of expected?)

### 3. Cross-path comparison
- [ ] Path A has guard X. Path B has guard Y or none.
- [ ] If Path B has WEAKER guard — exploit opportunity during anomaly
- [ ] "Anomaly" examples: depeg, oracle staleness, market volatility, low-liquidity

### 4. Trigger condition
For unprotected path to be exploitable:
- [ ] What market condition must hold? (e.g., LST trading below par)
- [ ] Is this condition reasonable? (Historical precedent? May 2022 stETH depeg, etc.)
- [ ] How long does condition need to last? (1 block / 1 hour / 1 day)

### 5. Attacker incentive
- [ ] Can attacker CAUSE the anomaly cheaply? (manipulate liquidity, dump volume)
- [ ] OR is attacker WAITING for natural anomaly? (lower severity but still real)
- [ ] Capital required, expected profit

### 6. Verification — Foundry fork PoC
- [ ] Fork mainnet
- [ ] Setup market with anomaly (or wait for one to happen in past block)
- [ ] Execute attack via unprotected path
- [ ] Measure: NAV before, NAV after, USD extracted

### 7. Severity
- [ ] Anomaly common (stablecoin depegs happen) AND no admin reaction time → **High/Critical**
- [ ] Anomaly rare (only major LST crash) AND admin can pause → **Medium**

---

## Past examples

### Alchemix WstETH (May 2022 stETH precedent)
- Paths: `_allocate()` direct vs `_allocateWithSwap()` 
- Direct path uses stETH price = 1 ETH (par)
- During depeg, wstETH market price = 0.95 ETH
- Result: each direct allocation marks down vault by 5%
- PoC: simulate depeg, run direct allocation, measure NAV loss

### Alchemix SFraxETH (same pattern, different LST)
- Same architecture as WstETH
- Same bug class
- Same severity argument
- **Class-of-bug expansion** (J6 phase)

### Hypothetical: NFT marketplace
- `buy()` uses Chainlink price oracle
- `acceptOffer()` uses offer price directly
- If offer price manipulable → bypass oracle

---

## Detection signals to look for

Search target code:
```bash
grep -rn "swap\|allocate\|deposit\|mint" --include="*.sol" | grep -i "withoracle\|withcheck\|withslippage"
```

If function names have both `_X` and `_XWithSwap` variants → likely candidate.

If you see comments like:
- `"oracle-independent guard"` — protected path
- `"direct"` / `"raw"` — likely unprotected path

---

## Output format

```markdown
## Oracle Bypass H<N>: <FunctionA (protected)> vs <FunctionB (unprotected)>

### Paths
- `<FunctionA>` (`file:line`) — guarded by `<oracle/slippage mechanism>`
- `<FunctionB>` (`file:line`) — NO equivalent guard

### Anomaly required
- Market condition: <e.g., LST trades below par by X%>
- Reasonable historical occurrence: <yes/no, cite past>

### Attack profile
- Capital: $<X>
- Expected profit: $<Y>
- Time required: <Z blocks>
- Lowest threat tier: T<N>

### Verification
- [ ] Foundry fork PoC: `verify/H<N>.t.sol`
```
