# Protocol-Type Threat Profiles  (reference-checklist — NOT a matcher model)

`_`-prefixed + `.md` → `apply.py` never loads this (it globs `*.yaml` and skips `_*`). This is a
**human/agent reference**, read at /deephunt J0 BEFORE running `apply.py`, to know — per protocol type —
*who threatens it, which invariants must hold, what to read first*. Condensed from pashov x-ray
`threats.md` ([[reference_pashov_skills]] block F). It does NOT restate our bug taxonomy; each type maps to
the relevant `hypothesis_taxonomy.md` categories. Token-quirk details live in **Cat 11** + the composability
matrix below points there — do NOT duplicate. Invariant formalism → **E `invariant_synthesis.md`**.

## How to use (J0 step 6, before apply.py)
1. Classify target by `protocol_class` (same value apply.py reads from chain.json/_tags.txt — see signals below).
2. Read the matching profile(s). Hybrid targets match multiple — primary = highest signal density.
3. Each "critical invariant" → a T2 STATE A hypothesis "can I break this?". Each "read first" → a score bump in T1.
4. Then run apply.py as usual; profiles are the WHY behind which threat_models fire.

## Classification signals (code-level)
| protocol_class | Detection signals | Maps to taxonomy |
|---|---|---|
| `lending` | `borrow/repay/liquidate`, `healthFactor`, `collateralFactor`, `LTV`, `debtToken`, interest accrual | Cat 1, 5, 8 |
| `dex_amm` | `swap/addLiquidity`, `x*y=k`, `sqrtPriceX96`, `tick`, reserves, `getAmountOut` | Cat 1, 5.2, 6, 11 |
| `vault_yield` | ERC4626 `deposit/withdraw/convertTo*`, strategy + `harvest`, `totalAssets` | Cat 1.6, 3, 8 |
| `stablecoin` | mint/burn vs collateral, `collateralRatio`, `debtCeiling`, PSM, peg/anchor | Cat 1, 4.7, 5 |
| `perps_deriv` | `openPosition/closePosition`, `fundingRate`, `margin`, `leverage`, mark/index price | Cat 1.8, 5, 9 |
| `liquid_staking` | `stake`+derivative mint, `requestWithdrawal`, exchange rate, validator set, queue | Cat 3, 5.4, 9 |
| `bridge` | lock/unlock or burn/mint cross-chain, relayer set, nonce, chainId, merkle proof | Cat 5.5, 18 |
| `governance` | `propose/vote/execute/queue`, quorum, snapshot, timelock, delegation | Cat 4, 9, 18.6 |

---

## Per-type profiles  (adversaries ranked by historical $-loss · critical invariants · read-first)

### lending
- **Adversaries:** flash-loan oracle-manip → oracle-manip → liquidation-MEV → first-depositor share-inflation → compromised-admin.
- **Invariants:** `totalBorrows ≤ Σ(collateral·LTV)` per market AND per account · every position liquidatable before bad debt · liquidation profitable (bonus > gas+slippage) · oracle within deviation+freshness bounds · interest accrual monotonic.
- **Read first:** full price path (oracle read → normalize → collateral value → health factor) — every step a manip point; can ONE tx borrow+manip+liquidate?; share math at `totalSupply==0`; what admin changes instantly vs timelock (esp. oracle address).

### dex_amm
- **Adversaries:** sandwich-MEV → flash-loan price-manip → empty-pool/first-LP → liquidity-manip → compromised-admin.
- **Invariants:** pool invariant holds before/after every op (`k=x·y` or curve) · LP share value monotonic non-decreasing from fees · no extraction without proportional burn / valid swap math · reserves-in-state == real balances (donation surface).
- **Read first:** swap math rounding direction (consistently favor one side?); LP mint/burn at `totalSupply==0` + min-liquidity; does pool expose `getPrice/observe` others call (→ it's an oracle, external blast radius — Cat 5.2 single-block); slippage enforced where, bypassable?; CEI on token callbacks (Cat 6).

### vault_yield
- **Adversaries:** first-depositor share-inflation → malicious/compromised-strategy → callback-reentrancy → donation-attacker → compromised-admin.
- **Invariants:** `totalAssets()` reflects real underlying always · `convertToShares(convertToAssets(s)) ≤ s` and reverse · strategy can't extract beyond allocation · share price rises only from yield, never manip.
- **Read first:** virtual-offset / min-deposit anti-inflation present?; `totalAssets` via `balanceOf(this)` (donatable) or internal accounting?; strategy interface — arbitrary gain/loss report? who adds strategies?; migration drops old approvals? (Cat 7); two-phase accounting delta (Cat 3.2).

### stablecoin
- **Adversaries:** oracle-manip → economic/governance → bank-run/redemption-DoS → flash-loan-minter → compromised-admin.
- **Invariants:** every unit backed ≥ ratio · mint/redeem inverse (no profitable loop) · peg mechanism convergent not divergent under sell pressure · liquidation restores position collateralization · supply ≤ Σ debt ceilings.
- **Read first:** mint path (collateral → valuation → ratio → mutable?); redeem under stress (all at once? priority queue?); death-spiral: at −10% depeg does mechanism push back or amplify?; governance reach + speed + emergency peg-break.

### perps_deriv
- **Adversaries:** oracle-manip (leverage-amplified) → liquidation-MEV → funding-rate-manip → position-size/payout-capacity → compromised-admin.
- **Invariants:** Σ PnL = 0 (zero-sum minus fees) · available liquidity ≥ max payout under worst-case move · liquidation before bad debt · funding converges OI imbalance · mark price within bounds of index.
- **Read first:** PnL correctness at leverage limits + sign edges; margin between liquidation trigger and insolvency; mark vs index, manip within a block?; max-OI/position caps enforced vs pool size; funding-rate cap — can it drain margin? (Cat 1.8 scale mismatch).

### liquid_staking
- **Adversaries:** exchange-rate-manip → validator-set → withdrawal-queue → rate-arbitrageur (stale rate) → compromised-admin.
- **Invariants:** exchange rate = staked+rewards−slashing (true) · derivativeSupply·rate ≤ underlying · queue fair-order · slashing reflected in rate BEFORE any user exits at stale rate.
- **Read first:** who reports rewards/slashing, how often, manipulable?; withdrawal queue delay/griefable?; rebasing vs share token — integrators handle? (Cat 11); massive-slash socialization (Cat 5.4 stale-after-halt).

### bridge
- **Adversaries:** validator/relayer-set-compromise (#1 by $) → message-replay → race/finality-reorg → fake-message-crafter → compromised-admin.
- **Invariants:** locked(src) == minted(dst) 1:1 · every message processed exactly once · message unforgeable without threshold consensus · cross-chain accounting consistent (no double-spend).
- **Read first:** relayer trust model (count, threshold, mutable?); replay protection (nonce checked? overflow?); proof verification edge cases (merkle/sig — Cat 5.5/14); finality wait before mint; admin drain locked funds? See also Cat 18 consensus + `live_targets_bridges.md`.

### governance
- **Adversaries:** flash-loan-vote → slow governance-capture → proposal-spam/obfuscation → timelock-front-run → compromised-guardian.
- **Invariants:** voting power snapshotted at proposal creation (NOT vote-time) · quorum prevents minority capture · timelock long enough to exit · no single role bypasses governance for non-emergency · proposal calldata matches description.
- **Read first:** voting power snapshot vs `balanceOf` (current = flash-loan trivial); quorum/threshold vs token distribution (cheap 51%? → `governance_capture_mint_drain.yaml`, Cat 4.7+18.6); timelock nonzero & sufficient; enumerate every governance-controlled param; emergency powers — who, can they drain?

---

## Temporal phases  (which dominate when — include per code signals)
| Phase | Include when | Dominant transient threats |
|---|---|---|
| Deployment/Init | always | init front-run (unguarded `initialize`), test-param misconfig (DELAY=0), ownership not transferred, empty-state (`totalSupply==0`) — Cat 10 |
| Steady state | always | baseline — covered by per-type profile above, don't re-list |
| Market stress | oracle/liquidation/price-dep logic | oracle latency under volatility, liquidation cascade, liquidity evaporation (liq unprofitable), correlated-asset depeg (1:1 assumptions), gas spikes stall keepers, withdrawal stampede |
| Governance/upgrade window | timelock/governance/proxy | timelock-exploit window, upgrade storage collision (Cat 2.2/2.7), flash-loan vote, slow capture, V1→V2 migration in-transit (Cat 10) |
| Deprecation/wind-down | V2/migrate/multi-version markers | residual funds in dead contracts, abandoned approval chains (Cat 7), dependent-protocol breakage, frozen-state staleness (→ `fund_liveness_reachability.md`) |

Output: a 2-4 bullet "Temporal Risk Profile" per applicable phase in the hunt notes; skip steady-state.

## Composability layers  (classify every external call)
- **Layer 1 — direct deps:** oracle chain (aggregation/staleness/deviation/zero/sequencer/fallback — Cat 5), yield-strategy (external holds funds, upgradeable? pause? migration approvals — Cat 7), **token behavior assumptions → see Cat 11 (Token-specific Quirks) + `severity_cap.weird-tokens`; do NOT duplicate the matrix**, callback reentrancy (ERC-777/1155/flash/swap — Cat 6).
- **Layer 2 — shared state:** liquidity coupling (same pool priced by two protocols → cross-tx move), oracle sharing (correlated liquidations), approval-chain exposure (unlimited approvals + upgradeable = latent drain — Cat 7).
- **Layer 3 — temporal composability:** governance-induced param change in a dep, upgrade-induced behavior change behind proxy, deprecation-without-notification (fail-open try/catch on stale data), dependency-of-dependency upgrade — flag dep chains > 2 levels deep.

For each external call record: target-type · return-value assumption · validation present? · external mutability (proxy/governed?) · fallback on failure (fail-open vs fail-closed). This feeds T6 flow-gap lens (execution×periphery).
