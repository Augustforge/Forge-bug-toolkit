# Governance Attack Checklist (6 patterns) — Immunefi V10 Top 10 gap

For a DAO / protocol with governance — go through each item. The $285M Drift attack was exactly governance.

## 1. Timelock too short
- [ ] Timelock delay < 48 hours
- [ ] Do critical operations (upgrade, pause, set fee) go through the timelock?
- [ ] Emergency execution can bypass the timelock
- **Threshold:** 48h minimum, 7 days recommended for high-TVL
- **Check:** `Timelock.delay()`, `Timelock.MIN_DELAY()` via `cast call`

## 2. Multisig threshold weak
- [ ] Threshold < 50% of owners (e.g. 2-of-5 = 40%)
- [ ] Owners not diverse (all from one company, or all hot wallets)
- [ ] No hardware wallet requirement
- **Pattern:** via Gnosis Safe `getOwners()` + `getThreshold()`
- **Threshold:** ≥ 51% AND ≥ 4 signers for serious DeFi

## 3. Voting period too short
- [ ] Voting lasts < 3 days
- [ ] The snapshot block is taken at proposal create time (and not earlier) — flash loan voting possible
- [ ] No proposal cancellation mechanism
- **Real case:** Beanstalk ($182M) — flashloan governance attack

## 4. Flash loan voting power
- [ ] Voting power = current balance (not a snapshot)
- [ ] Can flash loan tokens → vote → return
- [ ] Compound-style governance with GovernorBravo is protected, custom ones are often vulnerable
- **Fix:** use `getPriorVotes(addr, blockNumber)` where blockNumber is at the time of the proposal

## 5. Quorum / veto missing
- [ ] No minimum quorum (a proposal can pass with 1 vote if nobody votes)
- [ ] No veto authority (if a bad proposal passes — no emergency stop)
- [ ] No minimum proposal threshold (anyone can flood proposals)
- **Recommendation:** quorum ≥ 4% TVL, veto authority via a separate multisig

## 6. Cheap majority + atomic execution (govtoken supply economics)
Pattern 4 catches flash-loan voting (borrow→vote→return). This one is about **cheaply BUYING a majority** and
**executing atomically**, WITHOUT a flash loan. Root cause of TOP 2026 ($1.585M) — both factors at once.
- [ ] **Cost-to-acquire-majority vs drainable-value.** Calculate: how much does it cost to acquire quorum/51%
      voting power on the market? If `cost_to_acquire_majority << value_drainable_via_proposal` (treasury,
      mint authority, AMM exit liquidity) → the attack is profitable WITHOUT any flash loan.
- [ ] **Tiny / illiquid govtoken supply** — a minuscule `totalSupply()` or most of it in one
      pool / held by the default project → 51% is bought for pennies. TOP: supply 16,384, attacker bought 8,192+1.
- [ ] **Atomic create→vote→execute in one tx** — `votingDelay==0 && (votingPeriod==0 || instant) &&
      executionDelay==0` → the whole governance cycle passes in one block, the community has NO time to react.
      Aragon v1 Voting App without a separate timelock contract = this hole (TOP).
- [ ] **Proposal-reachable mint / treasury / param-set** — what CAN a proposal call? Uncapped
      `TokenManager.mint()` / treasury transfer / setMinter → quantify worst-case. Cross-ref Cat 4.7.
- [ ] **Exit liquidity present?** Freshly minted/withdrawn tokens need to be dumped somewhere — is there an
      AMM pool (Balancer V1 / UniV2) with real liquidity and without a circuit-breaker? = exit path.
- **Real case:** Token of Power (TOP) 2026 ($1.585M) — Aragon v1 no-timelock atomic governance +
  supply 16k (bought 51% on the market, not a flash loan) + uncapped TokenManager.mint (10B) + Balancer V1 exit.
- **Composite:** this pattern = threat_model [`governance_capture_mint_drain.yaml`](../threat_models/governance_capture_mint_drain.yaml)
  (gov-capture × uncapped mint × AMM exit). Beanstalk = the same class + flash loan.

---

## Manual on-chain checks via `cast`

```bash
# Timelock delay
cast call <timelock> "delay()(uint256)" --rpc-url $RPC

# Gnosis Safe owners + threshold
cast call <safe> "getOwners()(address[])" --rpc-url $RPC
cast call <safe> "getThreshold()(uint256)" --rpc-url $RPC

# Governor voting params
cast call <governor> "votingDelay()(uint256)" --rpc-url $RPC
cast call <governor> "votingPeriod()(uint256)" --rpc-url $RPC
cast call <governor> "proposalThreshold()(uint256)" --rpc-url $RPC
cast call <governor> "quorumNumerator()(uint256)" --rpc-url $RPC

# Pattern 6 — govtoken supply economics (cheap-majority check)
cast call <govtoken> "totalSupply()(uint256)" --rpc-url $RPC      # tiny supply = cheap 51%
# Compare the market cost of 51% supply with the value the proposal can reach (treasury/mint/AMM pool).
# Aragon v1: votingDelay==0 + no separate Timelock = atomic create+vote+execute (TOP class).
```

## Severity calculation for governance findings

| Threshold | Voting | Timelock | Severity |
|-----------|--------|----------|----------|
| <50% multisig | <3 days | <48h | Critical |
| ≥50% multisig | <3 days | <48h | High |
| ≥50% multisig | ≥3 days | <48h | Medium |
| ≥50% multisig | ≥3 days | ≥48h | Low/Info |
| atomic vote+exec + cheap 51% + reachable mint/treasury | — | none | Critical (TOP class) |

## Solodit search keywords
`governance attack`, `flash loan voting`, `timelock bypass`, `multisig`, `veto`, `quorum`, `Beanstalk`, `Drift`, `Aragon`, `cheap majority`, `atomic governance`, `TokenManager mint`
