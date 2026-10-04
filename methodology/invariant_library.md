# invariant_library.md — primitive invariants (cross-hunt capital)

> **Why.** `system_model.md` is born and dies inside a single hunt, so T10 costs the same every time,
> and knowledge gained on Wormhole-NTT does not make the next NTT fork any cheaper. This library
> outlives hunts. The key is the **primitive**, not the target.
>
> It lives in `methodology/`, not in `sessions/_methodology/`, precisely because it is not tied to a session.

**Three effects:**

1. **T10 gets cheaper with every hunt** — on a familiar primitive the model is not built from scratch but
   instantiated from here (the 30-45 minute time-box drops to minutes).
2. **T10-B becomes a machine** — a fork that does not enforce its parent's invariant = `ABSENT` for free,
   by a simple diff against the library entry.
3. **`ENFORCED` stops being wasted work** — today "the invariant holds" = zero value;
   here a confirmed guard of the reference becomes the reference for the whole family.

---

## Maintenance rules (otherwise it bloats into a dump)

1. Each closed hunt appends **only** those `I-NN` entries that relate to the **primitive**, not to the
   target's business logic.
2. An entry must carry **`ref:`** — `file:line` in the reference implementation. Without it, it is an opinion, not a reference.
   An unpinned entry is marked **`[UNPINNED]`**: usable as a hint, **not usable as a diff
   baseline** (otherwise "absent in the fork" would mean "I did not check the parent").
3. 🔴 **`fingerprint:`** — a machine fingerprint of the canonical mechanism: import / base contract /
   characteristic signature / storage shape. This is what catches `SUBSTITUTED`.
4. Do not create duplicates: grep the primitive key first.

### How to use `fingerprint:` (detecting `SUBSTITUTED`)

**Rule: functionality present + fingerprint absent = a `SUBSTITUTED` candidate.**

Do **not look at the calling code** — it always looks canonical (`getPastVotes(user, block)` reads
the same for OZ and for a home-grown version). Look at **what backs the data source**.

A detector script (`canonical_fingerprint.py`) only makes sense to write once **≥10
entries with `fingerprint:`** accumulate here — earlier it would be searching an empty space (the same rule by which we did not build
the magnitude-gate until 2 cases). Until then, grep the column by hand.

---

## Machine Fingerprints (regex bank — A7/A8, Wave 1 2026-08-08)

> **Why a machine layer on top of the tabular prose.** The tables below are for a HUMAN (rich `check:` +
> context). This bank is for CODE: canonical fingerprints in the STRICT format `- **fingerprint:** `<regex>``
> (the same as `undup_pattern_library.md`, parsed by `pattern_replay._FP_RE`). It feeds TWO Wave 1 engines:
> **A7** (transitive composition) attaches a fingerprint to an edge with a recognized primitive → auto-`SUBSTITUTED`
> (functionality is present + the canon regex does not match); **A8** (family-fork-diff) recognizes a fork's parent by
> fingerprint → `differential(parent, fork)`. `- **anti-fingerprint:**` = a fingerprint of a SUBSTITUTION (for the
> `SUBSTITUTED` judgment; pattern_replay ignores it, A7/A8 read it). It is extended together with the tables below.

### ERC20Votes / Votes snapshot
- **fingerprint:** `getPast(?:Votes|TotalSupply)\s*\(`

### Governor timelock delay
- **fingerprint:** `getMinDelay\s*\(`

### Pyth pull-oracle freshness
- **fingerprint:** `getPriceNoOlderThan\s*\(`
- **anti-fingerprint:** `getPriceUnsafe\s*\(`

### Pyth two-phase validate (bounded publish-time)
- **fingerprint:** `parsePriceFeedUpdatesUnique\s*\(`

### ReentrancyGuard (OZ)
- **fingerprint:** `\bnonReentrant\b`

### ERC4626 inflation offset (virtual shares)
- **fingerprint:** `_decimalsOffset\s*\(`

### UniswapV2-fork constant-product k-check
- **fingerprint:** `balance0Adjusted\s*\*\s*balance1Adjusted`

### Two-phase pull-oracle monotonic timestamp guard
- **fingerprint:** `if\s*\(\s*\w+\s*<=\s*\w*[Ll]ast\w*[Tt]imestamp\s*\)`

### EIP-1153 transient reentrancy lock (per-key)
- **fingerprint:** `TransientLock(Unsafe)?Lib|_raw\.inc\(\)\s*==\s*_LOCKED|\.lock\(\)\s*;`
- **anti-fingerprint:** lock keyed per-orderHash/per-item (`mapping(bytes32 => TransientLock)`) WITHOUT a global/per-maker guard → cross-item reentry is allowed (check shared state outside the key; 1inch-aqua: state is orderHash-isolated → safe)

### Aqua-style registry-allowance pull (non-custodial shared liquidity)
- **fingerprint:** `_balances\[\w+\]\[\w+\]\[\w+\]\[\w+\]|safeTransferFrom\(\s*maker`
- **anti-fingerprint:** `pull` without `msg.sender`-as-app in the key OR without a checked-sub (`prevBalance - amount` inside unchecked) → a foreign app drains / underflow-bypass (1inch-aqua Aqua.sol: app=msg.sender + checked uint248 sub = ENFORCED)

---

### Post-op solvency-gate modifier (DeltaPrime-class leverage)
- **fingerprint:** `(remainsSolvent|canRepayDebtFully|onlyOwnerOrLiquidation)`
- **canon:** the modifier re-reads LIVE balances AFTER `_` (getTotalValue=Σ balanceOf×price at read-time) → value-out is safe without a cache. Check: EVERY external value-out (borrow/withdraw/swap/unstake) carries such a post-op gate; absence on a single path = a hole. DeltaPrime v1.2.0: a never-cache architecture structurally blocks value-caching/double-count.

### Outcome-measured arbitrary-swap (calldata untrusted, delta trusted)
- **fingerprint:** `balanceOf\(address\(this\)\)\s*-\s*\w*[Ii]nitial\w*[Bb]alance`
- **anti-fingerprint:** router `.call(abi.encodePacked(selector, data))` WITHOUT a subsequent `boughtAmount < minOut → revert` on the real balance-delta OR WITHOUT a fixed-router-const + exact-approve-then-reset-0 → beneficiary-redirect/over-approval drain. DeltaPrime ParaSwapHelper: fixed PARA_ROUTER + approve(fromAmount)+reset0 + balanceOf-delta≥toAmount = decode-vs-execute divergence is dead.

### Redstone-required-for-borrowable oracle guard
- **fingerprint:** `BorrowableAssetRedstoneRequired|getOracleNumericValuesWithDuplicatesFromTxMsg`
- **canon:** borrowable assets MUST use a pull-oracle (Redstone caller-signed fresh ~3min), non-borrowable→Chainlink; ONE snapshot for all solvency legs = no cross-leg timestamp-arb. Check: source mixing (Redstone debt vs Chainlink 6h collateral) — but a coverage-haircut of 17-50% + the Chainlink deviation-trigger buffer staleness.

### Composite-token pricing: signed-oracle vs on-chain-reserve (manipulation-resistance)
- **fingerprint:** `getOracleNumericValuesWithDuplicatesFromTxMsg|getOracleNumericValueFromTxMsg`
- **anti-fingerprint:** on-chain LP/vault price COMPUTATION from reserves (`totalSupply()`.*`balanceOf`, `getReserves`, `quotePotential.*price`, `get_virtual_price` used FOR solvency) → donation/swap/coverage manipulation inflates collateral-value → over-borrow (ERC4626/LP-inflation class). DeltaPrime: ALL tokens (LP/vault/GM/TJv2) = Redstone-signed off-chain, NO on-chain reserve-price → on-chain manipulation does not move the solvency price. Check: how the protocol prices COMPOSITE-collateral (LP/vault-share) — signed-oracle (safe) OR on-chain-reserve (manipulable)?

## § 0x Settler (stateless swap/bridge executor — banked 2026-08-19)

> Canonical mechanisms verified on 0x Settler. Open when a 0x fork / stateless executor is recognized.
> `fingerprint:` = the canon; `anti-fingerprint:` = its substitution (SUBSTITUTED, where the criticals live).

- **Transient-slot reentrancy mutex** (payer/witness/operator = 3 implicit mutexes)
  - **fingerprint:** `Reentrant(Payer|Callback|Metatransaction)|tstore\(_(PAYER|OPERATOR|WITNESS)_SLOT`
  - **anti-fingerprint:** an entrypoint without the setPayer slot-occupancy → a reentrant execute passes (executably: nested execute → ReentrantPayer revert = ENFORCED)
- **Self-cleaning full-balance sweep** (no funds at rest → any foreign balance is swept by any caller)
  - **fingerprint:** `_checkSlippageAndTransfer` + `fastBalanceOf\(address\(this\)\)` in the final transfer + bps=BASIS hops
  - **anti-fingerprint:** a flavor WITHOUT a final full-sweep (BridgeSettler.execute) → native/token residual survives the tx (⚠ but a documented known-issue "ETH available to any action, MEV-bounded")
- **Pool-derivation from trusted factory+initHash** (canonical) vs push-model (SUBSTITUTED)
  - **fingerprint:** `AddressDerivation\.deriveDeterministicContract\(\s*factory`
  - **anti-fingerprint:** `pool`/`pair` as a function-param without derivation + a callback that self-reports sellToken/sellAmount (MaverickV2/EulerSwap/Hanji/UniV2/Velodrome/CurveTricrypto) → but bounded: Permit2-token/amount-binding + slippage-floor + self/trusted-composer = self-inflicted OOS
- **Per-entry-point witness typeSuffix** (sig-type-confusion prevention)
  - **fingerprint:** `_witnessTypeSuffix\(\)` hardcoded per-flavor + constructor `assert(...TYPEHASH == keccak256`
  - **anti-fingerprint:** a shared/submitter-chosen witnessTypeString → cross-flow replay (0x: distinct pinned → ENFORCED)
- **CREATE3-from-deployer-context** (address-squat impossible)
  - **fingerprint:** `create2\(0x00, 0x00, _SHIM_LENGTH, salt\)` from the Deployer context + a `_requireAuthorized` gate on deploy
  - **anti-fingerprint:** a shared/public CREATE3-factory + a predictable salt → front-run squat
- **Merkle-committed-digest ERC1271** (CrossChainReceiver submarine)
  - **fingerprint:** `_hashLeaf.*block\.chainid` + Merkle-root-in-salt (`keccak(root‖owner)` deploy) + `_verifyDeploymentRootHash`
  - **anti-fingerprint:** ERC1271 without a pre-committed leaf / without chainid-leaf-separation → second-preimage / cross-chain replay
- **`_hashActionsAndSlippage` length-guard** (action-smuggling prevention)
  - **fingerprint:** `or(gt(0x04, length), err)` in the hashing-loop (checks that each action is ≥4 bytes)
  - **anti-fingerprint:** hashing by `length` bytes WITHOUT a ≥4-check + a `decodeCall` slice `[4:]` → underflow → action smuggling (relative to the metaTxn signature); **⚠ already known to the auditors → dup; look for a SIBLING at other signed-bytes-array hashing sites**

**Un-dup lesson (0x):** a well-audited target with an external auditor → its bugs = **known/dup/OOS**; the payable path = a SIBLING of the class that the auditor missed (check ALL instances of the pattern, not just the fixed one). A cross-chain const collision is not a bug until the **live bytecode** is checked (deterministic deploy legitimately yields identical addresses — 2 false positives were caught by T4).

## EVM

### Custom bytecode-VM swap engine (1inch Aqua/SwapVM class)

| Invariant | `check:` | canon `fingerprint:` | `ref:` |
|---|---|---|---|
| taker slippage-threshold is enforced UNCONDITIONALLY by the engine AFTER the instruction-loop, not by an opcode | is `takerTraits.validate(...)` called outside the dispatch loop, before the transfers? or is the protection a maker-placed opcode (skippable jump/omit)? | `validate(` right after `runLoop()`, before `_transferIn/_transferOut` | 1inch-aqua SwapVM.sol:222 (ENFORCED) |
| the order-hash binds ALL execution-affecting fields (program/hooks/tokens in signed data; traits in full) | `keccak256(order.data)` as a blob + traits in the typed-hash? program-slice `end`=hashed data.length (not maker-suppliable)? | `_hashTypedDataV4(keccak(TYPEHASH, maker, traits, keccak(data)))` | 1inch-aqua SwapVM.sol:108-119 (ENFORCED) |
| `amountNetPulled += X` is symmetric with the REAL pull of X of the same tokenIn (fee-accounting) | is every netPulled increment paired with a pull of the same amount/token? does a non-Aqua fee NOT touch netPulled? | Aqua-fee: `netPulled += fee` next to `AQUA.pull(...,tokenIn,fee)` | 1inch-aqua Fee.sol:117-121,216-219 (ENFORCED) |
| concentrated-liq exactIn/exactOut are symmetric with respect to the capacity-cap (a round-trip gives the taker no profit) | on `out>balanceOut`, cap + recompute with ceilDiv (maker-favoring)? is backIn compared with the ACTUAL quotedIn, not the requested amount (symmetry-test trap)? | cap: `out=balanceOut; amountIn=ceilDiv(out*vIn, vOut-out)` | 1inch-aqua XYCConcentrate.sol:146-149 (ENFORCED; false-positive lesson: a symmetry test must compare against quotedIn) |
| the settlement _transferOut→_transferIn flash window is bounded by whole-tx atomicity; cross-order reentry does not extract value | is Context memory-local (fresh on reenter)? is per-order state isolated? does a revert in _transferIn unwind _transferOut? | `Context memory ctx` local + per-orderHash storage keys | 1inch-aqua (ENFORCED, executable PoC). ⚠ **hook-author note:** a maker-hook that reads a LIVE `balanceOf`/AMM-price inside the flash window (not a static ledger) = exploitable — the hook author's responsibility |

### LSD / staking distribute — balance-delta-as-rewards antipattern

| Invariant | `check:` | canon `fingerprint:` | `ref:` |
|---|---|---|---|
| "pending rewards" MUST be reconciled against the expected principal of staked positions, NOT = a raw balance-delta | what backs `getPendingRewards`/`_harvest`: `balance − earmarked` WITHOUT subtracting the staked principal (nodeBond/userCapital/depositedPrincipal)? is the distribution gate only off-chain-settable state counters? | CANON: `pending = balance − earmarked − stakedPrincipal` OR reconcile against an oracle/proof of the expected balance BEFORE the split | Rocket Pool RocketMegapoolDelegate.sol:152-158 (**ABSENT**: an exit-sweep of principal is treated as rewards) |
| a permanent principal inflow (beacon withdrawal-sweep / bridge-credit / raw `receive()`) must NOT end up in the reward-split | does the principal arrive as a raw balance credit (without a code call)? is the protection only a flag set by a permissionless+unincentivized off-chain call? | CANON: a principal inflow is marked on-chain ATOMICALLY (proof on entry), and does not rely on a timely external notify | Rocket Pool: `receive()` sweep + distribute() gated by `numExitingValidators` (set by the permissionless `notifyExit`) = **ABSENT** |

> **Class (reusable on ANY LSD / restaking / vault that accepts principal as a raw credit):**
> where a contract receives both principal and yield into one pool, and computes "rewards" as a balance-delta — look for
> a path by which principal enters WITHOUT synchronous on-chain accounting (beacon 0x01-sweep, bridge-mint, donation),
> and check that distribute/harvest will not split it as income. A gate on an off-chain-settable counter
> (`numExiting`/notify flag) = a hole: a silent miss → theft + a possible permanent freeze (finalize reverts
> on a drained balance). Executable PoC: drain via distribute → honest finalize reverts → freeze.

### EIP-4788 beacon-state-proof (SSZ merkle against BEACON_ROOTS) — Rocket Pool Saturn (ENFORCED — reference)

| Invariant | `check:` | canon `fingerprint:` | `ref:` |
|---|---|---|---|
| the root is taken from the BEACON_ROOTS predeploy by exact timestamp + revert-on-empty (4788 itself validates ts==stored in the 8191-slot ring) | `staticcall(0x000F3df6...Beac02, abi.encode(ts))` + revert if `!success/empty`? | `beaconRoots.staticcall(abi.encode(_slotTimestamp))` → revert "Block root is not available" | Rocket Pool BeaconStateVerifier.sol:124-131 (ENFORCED) |
| an SSZ List-proof includes the mix-in-length (membership cannot be forged from a list of a different length) | does List navigation use depth `log2+1` (length as a witness leaf)? | `intoList(idx, log2)` → depth `log2+1` | Rocket Pool SSZ.sol:29-32 (ENFORCED) |
| **caller-side (where the bugs live!):** the proof consumer binds proof→validatorIndex→pubkey→its own contract + freshness + anti-replay | a stateless `view` verifier + the caller: `WC==self` + `keccak(pubkey)==stored` + `slotTs+recency>=now` + a one-way state-machine? | CANON: Manager.stake `require(WC==getWithdrawalCredentials)` + pubkey-match + `slotRecencyThreshold` (1h) + exited-latch | Rocket Pool RocketMegapoolManager.sol:74,81,90,217 (ENFORCED — the crypto is clean; the bugs went into the accounting-seam, not the proof) |

> **Lesson:** SSZ/gindex crypto = a HOT zone (the crowd and the auditors re-derive it; it was clean against the Electra scheme).
> The un-dup critical lived in the **composition-seam** between the stateless proof verifier and stateful accounting
> (freshness/replay/binding + the balance-delta-rewards above), NOT in the crypto itself.

### `ERC20Votes` / `Votes` (OZ) — voting power

| Invariant | `check:` | canon `fingerprint:` | `ref:` |
|---|---|---|---|
| Vote weight is taken from a **snapshot at a past block**, not from current state | what backs the function the governor calls for weight: a checkpoint array with a binary search — or reading `balanceOf`/`shares` "as is"? | base `ERC20Votes`/`Votes`; `_checkpoints[account]` + `_binarySearch`; `getPastVotes(addr, blockNumber)` / `getPastTotalSupply` | `[UNPINNED]` OZ `contracts/governance/utils/Votes.sol` |
| Delegation is reflected in the snapshot the same way as a direct balance | does `delegate()` write a checkpoint to both parties? | `_moveDelegateVotes` writes a checkpoint to both the old and the new delegate | `[UNPINNED]` |

> **Why the first row is first here.** This is case C of phase 0: the governor looked correct as a whole, the weight
> was derived from its own accounting subsystem without per-block history → a "weight at a past moment" query
> degenerated into current state → capture with borrowed tokens in a single transaction. The canonical mechanism
> was **substituted**, not absent.

### `Governor` (OZ) — delays

| Invariant | `check:` | canon `fingerprint:` | `ref:` |
|---|---|---|---|
| Between proposal and execution the **sum** of all intervals passes (voting delay + voting period + timelock), and it cannot be bypassed by any path | enumerate ALL execution paths: is there a second one (batch overload, guardian/emergency/cancel-and-requeue)? | `TimelockController` with `getMinDelay()`; `queue()` → `execute()` via `_timelock` | `[UNPINNED]` |

### Round/epoch-clock `ERC5805` governance (Livepeer BondingVotes) — snapshot at the clock-tick boundary

> A variant of OZ `Votes` where `CLOCK_MODE` = round/epoch rather than block. The primitive is real
> even though the specific lead was ruled out as mitigated / out of scope.

| Invariant | `check:` | canon `fingerprint:` | `ref:` |
|---|---|---|---|
| The vote-weight snapshot is frozen at propose-time, NOT at the end of the clock tick | does `getPastVotes(_, R)` read the checkpoint `startRound=R` or `R+1`? a round-clock is coarse (~5760 blocks) → the flash-acquire window = a WHOLE tick if the snapshot = END-of-round | `getPastVotes(addr, round)`; **round-clock fingerprint** `CLOCK_MODE.*mode=\w+_round` / `getPastVotes.*_round\s*\+\s*1` | Livepeer `BondingVotes.sol:145,164-167` (MITIGATED by the pool-insertion cap `tryToJoinActiveSet`) |
| Vote numerator (per-account votes) ⊆ quorum denominator (active-set totalSupply) | is the `getVotes` source active-gated the same way as `getTotalActiveStakeAt`? if not — a phantom-quorum seam | canon: numerator & denominator from ONE active-gated base; **anti-fingerprint**: `getVotes` = delegatedAmount without an active-gate, totalSupply = active-only | Livepeer `BondingVotes.sol:171-173,369-372` (SUBSTITUTED but DOCUMENTED as intentional; capped OOS) |

### `assert`-as-invariant staking accounting (monotone-reward-counter ≤ shrinkable-stake)

| Invariant | `check:` | canon `fingerprint:` | `ref:` |
|---|---|---|---|
| `assert(cumulativeRewards ≤ totalStake)` holds ONLY thanks to a delegator-side cap (unbond ≤ own bondedAmount) | what prevents a third party from dropping totalStake below the accumulated reward counter? is commission baked into delegatedAmount? | `assert\(.*[Cc]umulative.*<=.*[Ss]take` next to reward-accrual | Livepeer `BondingManager.sol:391,1550` (ruled out; **transfer-candidate: FIRES on forks where autoClaimEarnings-before-unbond is removed**) |

### Cross-repo mint-cap trust seam (the core trusts a bridge supply-cache)

| Invariant | `check:` | canon `fingerprint:` | `ref:` |
|---|---|---|---|
| A core mint-cap is safe ONLY if the parent supply is monotonically non-decreasing + mint/cache are atomic | does the mint limit read a cross-repo/bridge `totalSupply` cache? who writes it, can it lag or roll back? | `getGlobalTotalSupply\|l1CirculatingSupply\|external.*totalSupply.*mint` | Livepeer `Minter` ↔ `L2LPTDataCache`/`L1LPTDataCache` (ruled out; conservation holds via floor-at-0 + atomic) |

### `Pyth` (pull model) — price freshness

| Invariant | `check:` | canon `fingerprint:` | `ref:` |
|---|---|---|---|
| The price is not older than N seconds | is `getPriceNoOlderThan(id, age)` called — or `getPriceUnsafe` + a custom `publishTime` check? | `getPriceNoOlderThan(...)`; **anti-fingerprint**: `getPriceUnsafe` | `[UNPINNED]` |
| `conf` (the confidence interval) participates in the safety buffer and is not discarded | look for `price.conf` in the arithmetic; `conf = 0` or an unused `conf` = strip | `conf` enters the boundary calculation (`price ± conf`) | Templar (conf-strip class) |
| The **free/no-data fallback path** (when the user did not pass a VAA) must not accept a stale cached price WITHOUT a cross-oracle divergence-check | is there a `data.length==0` → `getPriceUnsafe` cached branch bounded only by a loose staleness limit? is it compared against a second oracle (Chainlink) by DIVERGENCE (not just "which is newer")? | canon: cross-check `abs(pyth − chainlink) ≤ band` OR a tight fresh-window; **anti-fingerprint**: `getPriceUnsafe` cached + only `publishTime ≥ block.timestamp − staleLimit`, without a divergence-band | USDN `OracleMiddlewareWithPyth.sol:93-137` (ABSENT; the Redstone branch DOES a ±3x cross-check = reference) |

### Oracle aggregation (median / multi-feed) + fallback asset-parity

| Invariant | `check:` | canon `fingerprint:` | `ref:` |
|---|---|---|---|
| Aggregation of several feeds (median/average/loop) is protected by a deviation-bound OR a quorum — a single manipulated feed does not move the result | is there a `require(minQuorum)` / `require(abs(a−b) < maxDev)` next to `median(`/`sort(`/`prices[]`/a loop over feeds? **N price-reads ≠ safety** (the inverse heuristic was the source of an old FP) | canon: `median(prices)` + `require(minAnswers ≥ quorum)` + `require(deviation ≤ maxDeviation)`; **anti-fingerprint**: aggregation WITHOUT a deviation/quorum-guard | `[UNPINNED]`; detector `oracle_single_source.py` (`aggregate-no-deviation-bound`, P0-fix) |
| The fallback feed describes THE SAME asset as the primary (feed-ID / base-quote / decimals match) | with primary+fallback: are feed-IDs/aggregator addresses reconciled to one asset? a fallback can be LIVE but of a different asset → staleness stays silent | canon: `require(fallback.feedId == primary.feedId)` / assert base-quote parity before the fallback; **anti-fingerprint**: a fallback by index/name without an asset-check (Cat 5.15) | `[UNPINNED]`; detector `oracle_single_source.py` (`fallback-cross-asset-verify`, P0-fix) |

### `ReentrancyGuard` (OZ)

| Invariant | `check:` | canon `fingerprint:` | `ref:` |
|---|---|---|---|
| No re-entry into protected functions | an OZ modifier — or a custom `bool locked`? a custom one often does not cover the cross-function path | `nonReentrant` from `@openzeppelin/.../ReentrancyGuard.sol` | `[UNPINNED]` |

### `UniswapV2` fork — constant product

| Invariant | `check:` | canon `fingerprint:` | `ref:` |
|---|---|---|---|
| `k` does not decrease after a swap, accounting for the fee | **both sides** of the inequality use the same scale constants; the left and right parts are in the same scale | `require(balance0Adjusted * balance1Adjusted >= uint(_reserve0) * _reserve1 * 1000**2)`; adjusted = `balance*1000 - amountIn*3` | `[UNPINNED]` UniswapV2Pair.swap |

> This is case A of phase 0: the defect was a **scale mismatch** between the parts of the inequality (`10000`
> versus `1000**2`). The blind modeler described the mechanism imprecisely, but its `check:` ("both sides — the same
> constants") led to the defect. The `check:` matters more than the accuracy of the guess.

### Vault / share-accounting (ERC4626-like)

| Invariant | `check:` | canon `fingerprint:` | `ref:` |
|---|---|---|---|
| The first depositor cannot shift the share rate (inflation attack) | are there virtual shares/assets or dead-shares on the first deposit? | ERC4626 `_decimalsOffset()` / virtual assets | `[UNPINNED]` |
| The payout asset on redeem == the asset deposited on mint | where is the position's **unit of measurement** stored? if nowhere — `ABSENT` | — | Ethereal C-01 |
| **An ERC4626 wrapper over a REBASING token**: the share rate is pegged to the token's INDEX/divisor ratio, NOT to the balance-based `totalAssets()/totalSupply()` | how is the wrapper's exchange rate computed? if `totalAssets()` = `token.balanceOf(this)` (which REBASES) → the share price jumps on a rebase → inflation/frontrun. The canon for rebasing: `rate = f(token.index)` independent of the held balance | `rate = MAX_DIVISOR / token.divisor()` (index-pegged), NOT `balanceOf`-based | USDN `Usdn4626.sol` / `Wusdn.sol` (ENFORCED, kills donation/inflation for rebasing wrappers) |

### Two-phase pull-oracle action (initiate/validate with a deferred price)

| Invariant | `check:` | canon `fingerprint:` | `ref:` |
|---|---|---|---|
| Applying a price to state is monotonic in time: a price is applied only if its timestamp is STRICTLY newer than the last applied one | is there a guard `if (newTs <= lastAppliedTs) return old` before mutating `lastPrice`/funding/liquidation? otherwise a stale/reused price moves state | `if (timestamp <= s._lastUpdateTimestamp) return {old lastPrice}` before `s._lastPrice = currentPrice; s._lastUpdateTimestamp = timestamp` | USDN `UsdnProtocolCoreLibrary.sol:327,373-375` (ENFORCED) |
| The validation price corresponds to timestamp ≥ initiate + delay (a favorable historical one cannot be chosen) | how does validate derive the target timestamp? is it bounded from below by the initiate-timestamp + validationDelay? | validate → `parsePriceFeedUpdatesUnique(minPublishTime = actionTs + delay)` (tight), NOT `getPriceUnsafe` | USDN `OracleMiddlewareWithPyth.sol:68-84` (low-latency validate — reference vs a free initiate ABSENT) |

### Protocol-owned swap / fee-conversion — slippage floor

| Invariant | `check:` | canon `fingerprint:` | `ref:` |
|---|---|---|---|
| The min-out floor of a protocol swap is anchored to an INDEPENDENT price, not to the same pool the swap executes against | where does `minOut` come from? if from `getReserves()/getPriceAverage()` of THE SAME pair in the same tx → quote == actual → the floor is tautological, zero protection against manipulation | canon: `minOut` from an external oracle/Lido-rate/TWAP wider than the manipulation window; **anti-fingerprint**: the quote and `pair.swap()` read the same live reserves in one tx | USDN `AutoSwapperWstethSdex.sol` (SDEX leg: ABSENT, self-referential; the wstETH leg is anchored to Lido `getStETHByWstETH` = the reference within the same file) |

### Gas-based keeper/liquidation reward

| Invariant | `check:` | canon `fingerprint:` | `ref:` |
|---|---|---|---|
| The gas price in the reward is clamped so that a liquidator cannot inflate it via `tx.gasprice` | how is `γ` obtained? if raw `tx.gasprice` → manipulable | `gasPrice = min(block.basefee + offset, tx.gasprice)` | USDN `LiquidationRewardsManager.sol:122-127` (ENFORCED canon) |
| The final reward is clamped to maxReward AFTER summing over all ticks AND to the available balance | is the maxReward cap applied to the SUM (fixed+gas+value·Σticks) or per-tick? is it clamped to `balanceVault`? | sum over ticks → `min(total, maxReward)`; then `min(reward, balanceVault)` | USDN `LiquidationRewardsManagerWstEth.sol:69-71` + `UsdnProtocolLongLibrary.sol:527-530` (ENFORCED — but per-call, not aggregate: >iterationCap ticks get fragmented) |

### Off-chain signed order (EIP-712) — fill/usage cap + anti-replay (Seaport/0x/Blur/Decentraland-offchain)

| Invariant | `check:` | canon `fingerprint:` | `ref:` |
|---|---|---|---|
| An order cannot be executed more times than declared in its `uses` (over-consumption) | is the execution counter per order hash COMPARED (`< uses`) AND incremented **atomically** before/inside execution? or is there an increment but no cap comparison (or vice versa)? does a duplicate order within a single atomic accept pass? | `signatureUses[hashTrade]` (a mapping by EIP-712 hash) `require(uses < trade.checks.uses)` then `signatureUses[...]++` in the same call | Decentraland offchain-marketplace `Marketplace.sol` I-05 — **ENFORCED, T11-validated**: 128k fuzz call-seq, the invariant `settled(sig) ≤ uses(sig)` holds |
| Every accepted trade consumes a unique `tradeId`/salt (no replay of the same order) | is anti-replay bound to a nonce/salt/the used hash, and not only to expiration? | `tradeId` in the EIP-712 payload → marked as used; the domain separator is bound to chainid+verifyingContract | Decentraland offchain-marketplace (neighbor of I-05) |
| Expiration/`checks.expiration` is enforced BEFORE execution | is there a `require(block.timestamp <= expiration)` on EVERY order execution path? | `require(... expiration >= block.timestamp)` before settle | `[UNPINNED]` offchain-orderbook class |

### Meta-transaction `_msgSender` (ERC-2771 / NativeMetaTransaction)

| Invariant | `check:` | canon `fingerprint:` | `ref:` |
|---|---|---|---|
| `_msgSender()` in a meta-tx = the SIGNER, and it cannot be forged by appending bytes to calldata | are the trailing 20 bytes read ONLY when `msg.sender == address(this)` (i.e. via the verified `executeMetaTransaction`)? or does `_msgSender` trust the calldata tail unconditionally (any relayer can append a fake sender)? | canon: `_msgSender` returns the tail ONLY if `msg.sender == trustedForwarder`/`address(this)`; `executeMetaTransaction` verifies the sig over `(nonce, from, functionData)` BEFORE appending `from`. **anti-fingerprint**: unconditional reading of the last 20 bytes | `[UNPINNED]` OZ `ERC2771Context` / Decentraland `NativeMetaTransaction.sol` |
| The meta-tx nonce is monotonic (no replay of a signed meta-tx) | is `nonces[from]` incremented inside `executeMetaTransaction` before the external call? | `require(sig over nonces[from])` → `nonces[from]++` | `[UNPINNED]` |

### Interchain Mailbox (Hyperlane-family cross-chain messaging) — process CEI

| Invariant | `check:` | canon `fingerprint:` | `ref:` |
|---|---|---|---|
| `delivered[id]` is marked BEFORE `ism.verify` and `recipient.handle` (the recipient cannot re-process the same id via reentrancy) | is the write to `deliveries[_id]` in EFFECTS before INTERACTIONS, or are verify/handle called before the marking? | canon: `deliveries[_id] = ...` (EFFECTS) comes BEFORE `ism.verify(...)` and `IMessageRecipient(recipient).handle{value}(...)` (INTERACTIONS); the replay check `require(delivered(_id)==false)` in CHECKS | Hyperlane `Mailbox.sol:216-245` (ENFORCED — classic CHECKS/EFFECTS/INTERACTIONS) |
| The message is bound to the version + destination domain before processing | are `version==VERSION` and `destination==localDomain` checked at the start of `process()`? | `require(_message.version()==VERSION)` + `require(_message.destination()==localDomain)` first in `process` | Hyperlane `Mailbox.sol:209-213` |
| The recipient chooses its own ISM (permissionless) with a fallback to the default | how is the ISM obtained — from the recipient or from a global config? (this is NOT a hole but a trust model: the recipient is responsible for its own security) | `recipientIsm(recipient)` = staticcall `recipient.interchainSecurityModule()`, otherwise `defaultIsm` | Hyperlane `Mailbox.sol:219-221` |

### MultisigISM (m-of-n validators) — signer counting

| Invariant | `check:` | canon `fingerprint:` | `ref:` |
|---|---|---|---|
| No signature is counted twice: the threshold requires m DISTINCT validators in canonical order | are signatures matched with a forward-only two-pointer; does the index grow monotonically so a signer cannot be paired twice? **anti-fingerprint**: a nested loop that can rescan an already matched validator | two-pointer: `_validatorIndex` only `++`, never reset; `while(_signer != _validators[_validatorIndex]) ++_validatorIndex;` then `++_validatorIndex` after a match → a strictly increasing index = no dup-signer | Hyperlane `AbstractMultisigIsm.sol:106-121` (ENFORCED) |

### Interchain Account (ICA) — cross-owner isolation (SUBSTITUTED for Router-enrollment)

| Invariant | `check:` | canon `fingerprint:` | `ref:` |
|---|---|---|---|
| A remote caller controls ONLY the ICA derived from its own (origin, owner, router, ism, salt) — it cannot hijack someone else's account | is the account address a CREATE2 derivation over ALL identity fields, or is control via a mutable enrollment-mapping? | **canon (Router):** `handle` requires `_router==_sender` from an `onlyOwner` enrollment (`Router.sol:102-104`). **ICA SUBSTITUTES** this with a CREATE2-salt over all 5 fields `_getSalt(origin,owner,router,ism,userSalt)` → the account address itself is the authorization (no enrollment needed) | Hyperlane `AbstractInterchainAccountRouter.getDeployedInterchainAccount:135-163` + `_getSalt` (ENFORCED-equivalent; a canonical substitution, not a hole) |

### Off-chain reveal/commitment server — auth parity of sibling routes

| Invariant | `check:` | canon `fingerprint:` | `ref:` |
|---|---|---|---|
| Every route that serves THE SAME secret data applies ONE authorization | list ALL handlers returning secret X; do ALL carry an auth-gate, or does one serve it openly? **anti-fingerprint**: a signature/allowlist on route A, while a sibling GET returns the same field with only a rate-limit | canon: a single auth-middleware around all secret-serving handlers; sibling asymmetry = a finding | `[UNPINNED]` |

---

## Solana / Anchor

| Primitive | Invariant | `check:` | canon `fingerprint:` | `ref:` |
|---|---|---|---|---|
| Anchor account-context | The account chain is closed: the `mint` of the user's token account == the `mint` of precisely THAT vault which is used | is there an explicit vault↔position-mint binding, or is only "the vault belongs to the program" checked? | `#[account(constraint = ...)]` / `has_one = mint` | `[UNPINNED]` |
| CPI | After a CPI the account state is reloaded | is there a `.reload()` after the call? | `ctx.accounts.x.reload()?` | asymmetric.re (Cat 2.6) |
| PDA | The account owner cannot be reassigned | `assign()` without a subsequent owner check | — | asymmetric.re |
| whitelist/gating | The gate is applied on **all** paths, not only on `open_position` | enumerate all instructions that lead to the same state | — | phase 0 case B |
| **Pinocchio↔Anchor cross-impl** (Orca Whirlpools 2026-08) | A partial Pinocchio re-implementation reads/writes THE SAME accounts as Anchor → the byte layout of the `#[repr(C)]` MemoryMapped structs MUST match the Anchor Borsh-packed one | all MemoryMapped fields = **align-1** (`type BytesU128=[u8;16]` etc.), otherwise `#[repr(C)]` inserts alignment padding → offset drift → cross-impl corruption (Critical) | `type BytesU\d+ = \[u8; \d+\]` + `#[repr(C)]` with all align-1 fields (safe); a native `u128`/`u16` in a `#[repr(C)]` mmap struct = **anti-fingerprint** (padding drift) | Orca `pinocchio/state/mod.rs:4-9` (ENFORCED) |
| **Token-2022 extension whitelist** (Orca v2 2026) | Dangerous extensions (PermanentDelegate/TransferHook/DefaultAccountState/Pausable/freeze-authority) are admitted into a pool ONLY with an admin TokenBadge; NonTransferable/unknown → reject-by-default | is there a `_ => return Ok(false)` (reject-unknown) + an admin-badge gate on dangerous ones, rather than an allow-list only? | `is_token_badge_initialized` gate + a terminal `_ => Ok(false)`; **anti-fingerprint:** a dangerous extension in a permissionless-allow branch OR the absence of a reject-unknown default | Orca `util/v2/token.rs:208-320` (ENFORCED) |
| **Share-vault escrowed-accounting** (xORCA 2026) | rate = (non_escrowed+VIRT)/(supply+VIRT), where `non_escrowed = vault.amount − escrowed`; escrowed == Σ outstanding pending-tickets; unstake `escrowed+=W` + PDA(user,index) with `assert_owner==SYSTEM` (no double-escrow on an active index), withdraw `escrowed−=W` checked | round-down BOTH conversions (favor the protocol); a virtual offset against inflation; escrowed checked_add/sub; pending-PDA owner==SYSTEM at creation | `checked_sub(escrowed).ok_or(InsufficientVaultBacking)` + a virtual const + PDA(unstaker,index); **anti-fingerprint:** non_escrowed from raw vault.balance without subtracting escrowed, OR a re-usable withdraw_index | Orca xORCA `stake/unstake/withdraw.rs` (ENFORCED) |
| **CLMM tick liquidity_net conservation** (UniV3/Whirlpool CLMM) | On modify: lower.net += Δ, upper.net −= Δ (symmetric) → the invariant Σ(liquidity_net of all ticks)=0; a swap consumes net symmetrically on cross | rounding: increase rounds up-in/decrease rounds down-out; is_upper→net−=Δ, else net+=Δ; gross+=Δ, gross==0→uninit | `if is_upper_tick { net.checked_sub(Δ) } else { net.checked_add(Δ) }`; **anti-fingerprint:** an asymmetric net-update (both += or both −=), an off-by-one at the boundary, a lost upper-update on the same tick-array (`Option<upper>=None` without an `else` branch to lower) | Orca `manager/tick_manager.rs` + pinocchio port (ENFORCED) |

---

## Bridges / attested payload

| Invariant | `check:` | canon `fingerprint:` | `ref:` |
|---|---|---|---|
| The amount on the destination side == the amount confirmed by the source (conservation) | is there at least one amount-conservation assertion on the bridge's entry functions? | — | `scripts/web3/bridge_tests/source_amount_grep.sh`; Verus 2026 |
| Cryptographic validity of a signature ≠ semantic validity of the payload | what exactly is signed: the whole payload or a hash part of it? | — | Wormhole 2022 / Nomad 2022 |
| A log topic is parsed together with `Topics[0]` | `UnpackLog` without a topic0 check = event spoofing | `abi.UnpackLog` + an explicit check of `Topics[0]` | Heimdall ($2B), asymmetric.re |

---

## Consensus / node

| Invariant | `check:` | canon `fingerprint:` | `ref:` |
|---|---|---|---|
| Slashing validators cannot drop the set below quorum | is there a guard "quorum is preserved after removal"? | — | Axelar ($1B halt) |
| The transport limit ≥ the maximum size of a liveness-critical message | compare `max_body_bytes` with the maximum attacker-inflatable payload | Tendermint `max_body_bytes` | Axelar |
| Two implementations of a format parse identically (differential) | run T8 involution fuzzing | — | asymmetric.re (SSZ ghost-region, JSON `0x0B`) |

---

## ZK / halo2

| Invariant | `check:` | canon `fingerprint:` | `ref:` |
|---|---|---|---|
| Every assigned value is **tied by a constraint** to what it should be | `assign_advice()` without a corresponding `copy_advice()`/constraint = the prover is free to choose | `copy_advice(...)` / `constrain_equal` next to each `assign_advice` | Zcash Orchard (Taylor Hornby, $billions) |

---

## § Move (Sui / Aptos)

> The model is NOT EVM: no reentrancy by default (no dynamic dispatch), no integer-overflow-wrap (Move
> aborts), no `msg.sender` spoofing. Its own security model = the **ability system** (`key/store/copy/drop`)
> + **resource-oriented** (a value cannot be copied/lost) + object-ownership (Sui) / global-storage
> (Aptos). Bugs live in the substitution of these primitives, generic/phantom-type confusion, a leaked capability.
> `chain_detect` routes (`.move`/`Move.toml` → `chain move`), the scan is `scripts/move/move_safety_scanner.py`;
> the T10-B cross-port diff (Solidity→Move) is already built in (see `## Primitive: Liquid-staking vault`). PoC —
> `sui move test` / Aptos `move prover` (formal verification) in Docker.

| Primitive | Invariant | check: | canon fingerprint: | ref: | anti-fingerprint (SUBSTITUTED) |
|---|---|---|---|---|---|
| ability on an asset struct | a value-bearing struct does NOT have `copy`/`drop` (otherwise duplication/silent destruction of the balance) | do the Coin/position/receipt struct's abilities include only the necessary ones? | `struct Coin<phantom T> has store { value: u64 }` (no `copy`/`drop`) | `[UNPINNED]` | `has copy`/`has drop` on a struct that carries value → mint/burn-bypass |
| hot-potato | a struct WITHOUT abilities must be consumed in the same tx (flash-loan/receipt) → return/repayment is enforced | is there a no-ability `Receipt`/`FlashLoan` that `repay` requires, and does `repay` check the amount? | a no-ability struct is returned from `borrow`, accepted by `repay` with an `amount+fee` check | `[UNPINNED]` | `repay` does not reconcile the returned amount / the potato is wrapped in an object with `store` → repayment skipped |
| generic/phantom type | `Coin<T>` is not mixed: the phantom type guards against substituting USDC accounting with a junk coin | do functions generic over `T` retain the phantom-type binding between accounting and transfer? | the phantom `T` is carried through the whole path (`Balance<T>`→`Coin<T>`), there is no `T`-agnostic branch | `[UNPINNED]` | accounting in one `T`, payout in another / a cast through an intermediate generic function without the phantom |
| Sui object ownership | a shared object (anyone can submit it to an entry fn) gates authz INSIDE; owned-assumptions are not made on shared ones | do functions with `&mut SharedObj` check the caller's Cap/field before mutating? | `&AdminCap` or `assert!(field == sender)` inside the fn that takes `&mut Shared` | `[UNPINNED]` | a `&mut` shared object is mutated without checking the actor (everyone can call it) |
| capability | a Cap object (`AdminCap`/`TreasuryCap`) is the carrier of rights; not publicly mintable, not stealable | is the cap created only in `init`/gated; does a cap-gated fn require `&Cap`? | `fun admin(_: &AdminCap, …)`; a cap without `store` or with a controlled transfer | `[UNPINNED]` | a cap mintable by anyone / `TreasuryCap` leaked → unlimited mint / a cap with `store`+public_transfer = theft of rights |
| Sui OTW / currency | the currency is created once (one-time-witness in `init`), `TreasuryCap` does not leak | is `coin::create_currency` called with an OTW in `init`, is `TreasuryCap` stored/burned? | an OTW struct (name = module, `drop`), created once in `init` | `[UNPINNED]` | `TreasuryCap` is returned outside/stored in shared without a guard → mint |
| Aptos global storage | `borrow_global_mut<T>(addr)` on an arbitrary `addr` is gated by ownership | does a fn that takes `addr: address` and `borrow_global_mut<T>(addr)` check `signer::address_of`? | authz via `signer` (`signer::address_of(account)`), not via a passed `address` | `[UNPINNED]` | `borrow_global_mut<T>(user_supplied_addr)` without an owner check |
| Aptos SignerCapability | `SignerCapability` (the resource-account signature) does not leak = otherwise full control of the account | where is `SignerCapability` stored, who can extract it? | the cap in a private resource under the module's control, extraction gated | `[UNPINNED]` | `SignerCapability` is returned/readable publicly → resource-account takeover |
| arithmetic (abort-model) | Move aborts on overflow/underflow — an attacker must not be able to force an abort on a critical path (griefing/DoS) + rounding in favor of the protocol | is there an `a - b` where `b>a` is reachable → permanent abort? rounding direction? | explicit operation order / `math64`/`math128` helpers, rounding-down on payout | `[UNPINNED]` | `x - y` in accounting where y is attacker-inflatable > x → DoS; round-up on payout |

---

## § Clarity / Stacks (Bitcoin-L2)

> The model is NOT EVM: the language is **decidable, not Turing-complete** (no unbounded loops), int/uint 128-bit
> **abort** (do not wrap) on overflow/underflow/div0, there is no reentrancy in the EVM sense (but `contract-call?`
> to a passed trait = the equivalent of an arbitrary external call). Its own model: `tx-sender`/`contract-caller`
> caller-confusion, **post-conditions** (client-specified asset assertions), response types (`unwrap!`/`try!`).
> `chain_detect` routes (`.clar`/`Clarinet.toml`/`stacks:`/`clarity:` → `chain stacks`; there is no engine —
> manual, hypothesis-driven). PoC — **Clarinet simnet** (`clarinet test`, TS/Rust) in Docker. A live
> reference target: Zest V2 (Bitcoin lending, Stacks).

| Primitive | Invariant | check: | canon fingerprint: | ref: | anti-fingerprint (SUBSTITUTED) |
|---|---|---|---|---|---|
| caller identity | authz uses the CORRECT caller: `tx-sender` (the original signer, survives a contract-call — like tx.origin) vs `contract-caller` (the immediate one) | is a privileged `asserts!` placed on `tx-sender` while the function is reachable via an intermediate contract? | authz by `contract-caller` (or an explicit principal parameter + a check); `as-contract` only where the contract acts as itself | Zest V2 (live reference target) | `(asserts! (is-eq tx-sender ADMIN))` on a fn reachable via a foreign contract-call → confused-deputy |
| post-conditions | contract security does NOT rely on post-conditions (they are set by the CLIENT and may be sent in `allow` mode = forbidding nothing) | does the contract itself check the amounts/transfer recipient, rather than "the wallet will catch it"? | contract `asserts!` on the amount/address before `ft-transfer?`/`stx-transfer?` | `[UNPINNED]` | a comment/assumption "a post-condition will protect" instead of an on-chain check |
| response handling | every `(ft-transfer? …)`/`(contract-call? …)` result is checked; `unwrap-panic` does not sit on an attacker-influenced value (a forced abort = DoS) | are transfer results wrapped in `try!`/`unwrap!`? where there is `unwrap-panic` — is the input controlled? | `(try! (ft-transfer? …))` / `(unwrap! (…) ERR-CODE)` | `[UNPINNED]` | an ignored `(ft-transfer? …)` without unwrap (silent failure) / `unwrap-panic` on `(map-get? …)` with a user key |
| trait dynamic dispatch | `(contract-call? <trait> …)` with a caller-passed trait = an arbitrary contract → allowlist/verification before trusting | is the trait parameter (`<ft-trait>`/`<vault-trait>`) checked against an allowlist of accepted principals? | a check `(asserts! (is-some (index-of APPROVED (contract-of token))))` before the contract-call | `[UNPINNED]` | `(contract-call? token transfer …)` where `token` is an untrusted trait parameter without an allowlist (a fake token lies about the balance) |
| visibility / authz | state-mutating privileged logic does not end up as `define-public` without an authz guard | does every sensitive `define-public` have an `asserts!` guard at the start? | an authz `asserts!` as the first expression in `define-public`; internal logic — `define-private` | `[UNPINNED]` | a `define-public` without a guard, reachable from outside (everyone can call it) |
| arithmetic (abort-model) | Clarity aborts on overflow/underflow — an attacker does not force an abort on a critical path; rounding in favor of the protocol (fixed-point lending: interest/collateral/liquidation) | is there a `(- a b)` where `b>a` is reachable → permanently stuck? rounding direction on division? | explicit order (a `>=` check before `-`), round-down on payout/round-up on debt | `[UNPINNED]` | `(- collateral debt)` where debt>collateral is reachable → abort-DoS of the position; rounding in the user's favor |
| block anchoring | Stacks-block vs Bitcoin-burn-block are distinguished; time/rates on a non-manipulable source | are interest/expiry computed by `burn-block-height` (BTC-anchored) where BTC anchoring is needed, not `block-height`? | `burn-block-height` for BTC-anchored timings; `at-block` read-only with a correct block-hash | `[UNPINNED]` | `block-height` where `burn-block-height` is needed (or vice versa) in accrual → desync/manipulation |

---

## § Frontend (dapphunt — web3-frontend primitives)

> The mechanics are the same (see "How to use `fingerprint:`"): functionality present + canon fingerprint
> absent = a `SUBSTITUTED` candidate. `ref:` is mandatory (otherwise `[UNPINNED]`, like the flagship rows).
> The starter set is 7 primitives (§5, completed in Plan 4 Task 6): postMessage origin, EIP-712 chainId, SIWE
> nonce, auth allowed_domains, Permit/Permit2 deadline, iframe frame-ancestors, token decimals.

| Primitive | Invariant | check: | canon fingerprint: | ref: | anti-fingerprint (SUBSTITUTED) |
|---|---|---|---|---|---|
| postMessage origin | the origin is checked strictly (not by substring) | grep the message handlers: an exact origin comparison? | `event.origin === "https://exact"` / an allowlist `.has(origin)` | `[UNPINNED]` | `.includes()` / `.indexOf()` / `.startsWith()` / a regex on the origin |
| EIP-712 chainId | chainId comes from the wallet, not hardcoded | is domain.chainId from walletClient or a literal? | `domain.chainId` ← `walletClient.getChainId()` / `useChainId()` | `[UNPINNED]` | a literal `chainId: 1` in a multi-chain deployment |
| SIWE nonce | a server-issued single-use nonce, invalid after verify | does the nonce come from the server (not client-generated) and is it not reused on a repeated verify? | nonce ← a server endpoint, short TTL/marked used after verify | idOS/Kwil KGW — `kgw.authn_param` server-issued nonce (~30s TTL), consumed by POST `kgw.authn` → cookie session | `Math.random()`/a client-generated nonce, no server-side invalidation |
| auth allowed_domains | an exact list of domains, no wildcard | the auth provider's config (Privy/Magic/Web3Auth/...) — an exact host-list or a wildcard? | an exact host-list in the provider config's `allowed_domains` | `[UNPINNED]` | a wildcard `*.domain.com` in `allowed_domains` |
| Permit2/Permit deadline | a finite lifetime of the signature | is `deadline`/`sigDeadline` a bounded forward window or unbounded? | `deadline = now + Δ` (a short, finite window) | `[UNPINNED]` | `type(uint256).max` / "Forever" / no deadline check on the execution path |
| iframe frame-ancestors | CSP `frame-ancestors` + XFO are set and in sync with the auth `allowed_domains` | are the headers present on EVERY sibling host and do they match the auth provider's list? | CSP `frame-ancestors 'self' https://exact` + a synchronized `X-Frame-Options` | `[UNPINNED]` — sibling asymmetry: one sibling sets `frame-ancestors 'self'` while another sets NOTHING (neither XFO nor CSP) → clickjacking on the less hardened sibling | `frame-ancestors *` / the header is absent / out of sync between siblings or with the auth config |
| token decimals | decimals are read from the token's on-chain metadata | are the amount/balance formatted via the contract's `decimals()` before display, or via a literal/user input? | `decimals()` is called on the token contract before formatting the amount | `[UNPINNED]` | hardcoded `18` / decimals taken from a user-supplied/URL/metadata parameter · ⚠ `e.decimals\|\|18` (JS `0\|\|18=18` loses decimals=0) — it should be `??` |
| signable fund-routing addr | approve-spender / tx-`to` = a build-time-hardcoded per-chain config OR on-chain-verified, NOT from an unsigned API | capture the REAL tx in the browser (a mock catches `eth_sendTransaction`) → grep the spender/`to` in the bundle: hardcoded or from an API response? | spender ← `contracts:{router:"0x…"}` per-chain const / on-chain `getAllInstruments()`-verified | `[UNPINNED]` — lesson: **static provenance lies, the runtime tx is the truth** | the spender/`to` is taken VERBATIM from an unsigned per-instrument API response (`fetchInstrument().gate`) without a hardcoded/on-chain cross-check |

---

## § Web2 (hunt — web2 primitives)

> The mechanics are the same (see "How to use `fingerprint:`"): functionality present + canon fingerprint
> absent = a `SUBSTITUTED` candidate. `ref:` is mandatory (otherwise `[UNPINNED]`, like the flagship rows).
> The full set is 10 primitives (§18, completed in Plan 5 Task 8 + Plan 9): authz, JWT verify, SSRF guard,
> password-reset, CORS, SQL/parametrized, session, **+ BOPLA-write, object-provenance, revocation-staleness (Plan 9)**.

| Primitive | Invariant | check: | canon fingerprint: | ref: | anti-fingerprint (SUBSTITUTED) |
|---|---|---|---|---|---|
| authz | the check goes through a framework guard, not inline | endpoint handlers: a decorator/middleware or a manual if? | `@requires_auth` / Django perms / Rails `before_action` / middleware | `[UNPINNED]` | a manual inline `if user.id==...` across handlers |
| JWT verify | verify with alg from config + secret | verify: is the algorithm from config or from the header? | lib `verify(token, secret, {algorithms:[...]})` | `[UNPINNED]` | `alg:none` accepted / verify off / alg from the header |
| SSRF guard | an allowlist of hosts / deny private ranges AFTER DNS-resolve | how is the URL checked before fetch? | `resolve→check-against-allowlist / deny RFC1918+169.254` | `[UNPINNED]` | a string blocklist (bypassed via decimal/octal/DNS-rebind) |
| password-reset | the token is single-use, has a TTL, is bound to the user, invalidated after use | reset token: one-time, expires, host-header-independent? | a server-issued random token, TTL, marked used | `[UNPINNED]` | predictable / host-header poisoning (`X-Forwarded-Host`) / no invalidation |
| CORS | `ACAO` from an allowlist, `ACAC:true` only with an exact origin | is ACAO reflected or from a list? | `ACAO ∈ allowlist`, credentials only with an exact origin | `[UNPINNED]` | `ACAO:*`+credentials / a reflected origin without a check / null-origin trust |
| SQL / parametrized | parametrized queries / ORM binding | is the query built by concatenation or binding? | a prepared statement / ORM parametrized | `[UNPINNED]` | string concatenation of user input into SQL |
| session | server-side invalidation on logout/reset, secure/httponly/samesite | is the session invalidated on the server? cookie flags? | a server-side session store + invalidate on logout, `HttpOnly;Secure;SameSite` | idOS/Kwil KGW — KGW SIWE auth → a per-account server-side session cookie (`kgw.authn_param`/`kgw.authn`) | a JWT without a blacklist / session fixation / no rotation after privilege change |
| BOPLA (write) | a write does NOT accept privileged fields outside the role (mass-assignment) | does an injected owner/role/isAdmin field on write show up on read-back? | a server field-allowlist on write (not a blind bind), out-of-schema fields ignored | Plan 9 T1 `scripts/web2/business_logic.py` mass-assignment prover (write→read-back `semantic_diff`) | a blind object-bind (Rails/Mongoose/Sequelize) without a field-allowlist → the privileged field persists |
| object-provenance | BOLA is proven by a create→access chain, not by a marker diff of a single response | who created/owns/has access — is it recorded and reconciled? | a provenance registry `{object_id,created_by,owner}` + an ownership-diff against it | Plan 9 T4/T10 `scripts/web2/object_registry.py` + `authz_diff._apply_provenance` / provenance-from-traffic | an ID-swap "the response differs" without owner-identity grounding → an unproven/FP BOLA |
| revocation-staleness | access is actually revoked on the SERVER after revoke/expire/downgrade/unshare | does a re-probe of the same (op,role) AFTER the transition still return 200? | a server-side re-check of rights on every request (not a stale-token/stale-share/cache) | Plan 9 T3 `scripts/web2/authz_diff.py` transition→reprobe branch | point-in-time authz only; stale-but-still-works after revoke |
| api-request-signature (secret) | the request signature/HMAC (`X-*-Sign`) rests on a SERVER secret unavailable to the client | is the signing key a server secret or derived from values the client itself sends in the request (nonce/ts)? | HMAC/signature with a key from a server-side env secret (not from the bundle, not from the nonce) | `[UNPINNED]` — example: `X-Api-Sign` key = `keccak256(client-nonce)`, with the nonce in the `X-Api-Nonce` header → zero secret → forgeable, the gate = anti-bot, NOT authz | key = f(nonce/ts/uri) from the request itself / the key is hardcoded in the JS bundle → any client reproduces it |
| api-user-identity-binding | a private per-user endpoint takes identity from a VERIFIED token, not from a client parameter | does an endpoint `?userAddress=`/`?userId=` bind data to the token's subject or trust the parameter? | user ← the verified session/JWT subject; the client `userAddress` param is ignored or reconciled `== subject` | `[UNPINNED]` — example: an account endpoint whose identity = a `userAddress` query param with zero session → unauthenticated BOLA across all users; a sibling referral endpoint is authed by `jwtToken` (evidence of an oversight) | identity from a query/body parameter `userAddress`/`userId` without reconciliation against the token (classic BOLA/IDOR on an API) |

---

## § AI (LLM / agent-integration primitives — both web profiles)

> The mechanics are the same (see "How to use `fingerprint:`"): functionality present + canon fingerprint
> absent = a `SUBSTITUTED` candidate. `ref:` is mandatory (otherwise `[UNPINNED]`, like the flagship rows).
> Apply when the target carries an LLM/agent feature (class Cat 28, axis `ai-trust`, partition `P-AI`,
> harness `scripts/web2/ai_injection_diff.py` dclass `ai-trust`). The starter set is 7 primitives.

| Primitive | Invariant | check: | canon fingerprint: | ref: | anti-fingerprint (SUBSTITUTED) |
|---|---|---|---|---|---|
| tool-call re-authz | authz is re-checked AFTER the LLM's decision, per tool-call, against the rights of the CALLING user | is every tool-call gated server-side by the object/role of the caller, not of the agent? | server-side authz on EVERY tool-call with the identity of the session user (not the agent's privileges) | `[UNPINNED]` | the agent calls a tool under its own rights without re-checking the user's rights → BFLA/BOLA via LLM (Cat 28.1) |
| context≠instruction boundary | input into the context (chat/RAG/tool-return/metadata) does NOT override system instructions | are data and instructions separated structurally, not by concatenation into one prompt? | typed roles / spotlighting / a data-vs-instruction delimiter | `[UNPINNED]` | user/RAG/tool text is concatenated into the system prompt without a boundary → injection (Cat 28.1 / 23.11 / 23.12) |
| tenant-scoped RAG | retrieval is filtered by tenant/user AT THE STORE LEVEL before being fed into the context | does the vector query carry a tenant/ACL filter in the store, or is it a shared index + "ask it not to show"? | a retrieval query with a tenant/ACL filter at the store layer (not a post-filter in the prompt) | `[UNPINNED]` | a shared index for all tenants, the filter in the prompt → RAG tenant-bleed (Cat 23.12b) |
| tool-allowlist + per-call cap | the agent calls only allowlisted tools, with a per-call/spend/recursion limit | is there an explicit tool allowlist + a rate/spend/depth cap? | a static tool allowlist + a per-session spend/recursion cap | `[UNPINNED]` | an arbitrary internal request by the agent (SSRF confused deputy, Cat 28.3) / unbounded recursive calls (cost/DoS, Cat 28.5) |
| LLM-output sanitize before sink | LLM output is escaped/validated before DOM/eval/tool-dispatch, like user input | does an LLM response go through the same escape path as user input before the sink? | LLM output → the same sanitize path as user input, before innerHTML/eval/dispatch | `[UNPINNED]` — same class as an innerHTML sink fed by attacker-controlled token symbol/metadata; here the source = LLM output | escaping on user input but NOT on LLM output (asymmetric) → XSS/command (Cat 28.4, Cat 16) |
| system-prompt hygiene | no secrets/internal endpoints in the prompt; prompt extraction yields no privileges | does the prompt contain keys/internal URLs/tool schemas? is extraction = a leak? | secrets/endpoints in a protected layer, NOT in the model context | `[UNPINNED]` | keys/internal API/hidden caps are baked into the system prompt → extraction = an info leak + an entry into a chain (Cat 28.2) |
| ml-artifact loading | a user-uploaded ML artifact (dataset/checkpoint/model/config) is parsed in a sandbox / safe-loader, NOT as a trusted code-carrying format | does the backend load an upload via a safe path or via a code-executing deserializer? | `weights_only=True` / `yaml.SafeLoader` / `np.load(allow_pickle=False)` / HDF5 external-links off / `trust_remote_code=False` / a format allowlist + sandbox | public incident (external ref: a malicious HDF5 dataset → external-file-read in prod → RCE) | a code-carrying deserializer on an untrusted upload → AFR/RCE (Cat 28.6): raw `pickle.load`/`torch.load`(default)/`h5py.File`(external-links on)/`yaml.load`/`allow_pickle=True`/`trust_remote_code=True` |

---

## Replenishment

On `HUNT-EXIT` (and when closing a hunt with no finding too): walk through `system_model.md` and bring here
the **primitive** `I-NN` entries with their `fingerprint:` and `ref:`. The `active_divergence_unresolved` gate checks
that, with a non-empty model, the library was replenished with at least one entry.

Related: `sessions/_methodology/independent_model_first.md` (T10-B)

---
## Primitive: Socket "Controller-Vault" SuperToken bridge (app-chain token bridging)
Recognition (`fingerprint:`): files `Vault.sol`+`Controller.sol`+`Gauge.sol`+`ExchangeRate.sol`+`ConnectorPlug.sol`, interfaces `ISocket`/`IPlug`/`IHub`; `depositToAppChain`/`withdrawFromAppChain`/`receiveInbound`/`unlockPendingFor`/`mintPendingFor`. Vault = lock/unlock escrow (source chain), Controller = mint/burn (app chain). First ref: Aevo (Arbitrum Vault `0x80d4…137c`), 2026-07-29.
Primitive invariants + the canonical enforcement mechanism (ref: Aevo deploy, read):
- **INBOUND-AUTH** (`I-02/I-03`): `ConnectorPlug.inbound` gated by `msg.sender==socket__`; the hub (`Vault`/`Controller`) `receiveInbound` gated by `_unlock/_mintLimitParams[msg.sender].maxLimit!=0` — the registry is populated ONLY by `updateLimitParams` (onlyOwner). fingerprint: NO hardcoded connector address, auth = "does msg.sender have a limit-param". ⚠ siblingChainSlug in `inbound` is IGNORED (immutable per-plug) — cross-slug isolation is delegated to the Socket core.
- **GAUGE-CONSERVATION** (`I-04`): `_consumePartLimit` → `consumed+pending==amount` in both branches; `_getCurrentLimit` capped at maxLimit; refill = `timeElapsed*ratePerSecond`. The rate-limiter throttles VELOCITY, not identity. ⚠ footgun: the owner sets a huge `ratePerSecond` → `timeElapsed*rate` overflows (0.8.x checked) → `_getCurrentLimit` reverts → the connector is bricked (including the recovery `updateLimitParams`, since it also calls `_consumePartLimit(0)` first). Owner-triggered.
- **PENDING-LOCKSTEP** (`I-05`): `pendingUnlocks[c][r]` += pending in receiveInbound; `unlockPendingFor` (a permissionless keeper) deducts up to the remaining + `connectorPendingUnlocks[c]-=consumed`. The payout is hardwired to the `receiver_` param (not msg.sender) → the keeper cannot redirect it. No double-claim.
- **CEI** (`I-08`): state (Gauge+pending) is updated BEFORE `safeTransfer`. Safe for no-hook tokens (USDC/USDC.e).
- **REPLAY**: NO nonce/msgId dedup in the in-scope layer — fully delegated to the Socket core (`ISocket.execute` msgId/packetId). Vault/ConnectorPlug = passthrough.
- **EXCHANGE-RATE** (`I-06`): `getMintAmount`/`getUnlockAmount` in the ref = identity (return input); applied ONLY on the Controller (L2), the Vault moves the raw amount. ⚠ a non-identity rate + the owner's `updateExchangeRate` = a potential Vault↔Controller asymmetry (owner-triggered).
**Lesson for future Socket targets:** a permissionless drain in the in-scope layer is by design absent (auth/accounting are in the OOS Socket core + the counterparty Controller). Cross-TARGET transfer: a fee-on-transfer/rebasing token deposit (`I-09` ENFORCED-PARTIAL) — dead on USDC, but live on a Socket deployment with a fee token.

---
## Primitive: Liquid-staking vault (multi-validator, auto-compound; cross-chain PORT family)
Recognition (`fingerprint:`): the vault mints a receipt token (TruX/stX) per `sharePrice` over staked+idle+rewards; delegates to N validators; auto-compounds rewards taking `fee` bps to the treasury as minted shares; withdraw = burn→unbond→claim-after-period. Files `*Staker*`/`*Stake*Vault*` + an interface to chain-native staking (Polygon `IValidatorShare`, Cosmos `StakingMsg`, Aptos `delegation_pool`, SPL Stake Pool). Reference: **TruFin `TruStakePOL.sol`** (13 audits, read 2026-07-30). Key: the same logic is PORTED to Move/CosmWasm/Rust → the **T10-B cross-port diff = a machine** (the invariant is ENFORCED in Solidity, ABSENT/SUBSTITUTED in the port).

Primitive invariants + the canonical mechanism:
- **SHARE-PRICE fee-weight** (`I-05`): `price = [(totalStaked+totalAssets)·FEE_PREC + (FEE_PREC−fee)·totalRewards]·WAD / (totalSupply·FEE_PREC)`; supply==0→(WAD,1). fingerprint: **rewards weighted `(FEE_PREC−fee)`, idle+staked full-weight** — if a port puts realized rewards into the full-weight bucket WITHOUT minting the treasury fee → the share price inflates. ref: `TruStakePOL.sol:198-207`. (A port that reproduces `internal_share_price` identically = ENFORCED; verify a port line by line.)
- **FAIR-CLAIM** (`I-01`): only the initiator of an unbond claims; the record is consumed BEFORE the external transfer. fingerprint: a `stored.user == caller` revert + `delete/remove` before the CPI/send. ref: `TruStakePOL.sol:676-696` (`withdrawal.user!=msg.sender` revert; `delete` before `_claimStake`).
- **SLASH-CLAIM-RECONCILE** (`I-11`): a claim pays the **actually received amount per nonce**, not face value from a shared pool. fingerprint: the canonical `_claimStake` measures `totalAssets()` before/after the real unstakeClaim → pays the delta (`TruStakePOL.sol:690-693`) → the slash loss is borne by the SPECIFIC claimer. `SUBSTITUTED` = a port stores face value in claims + pays FCFS from a shared bank balance → after a slash, later claimers are frozen (socialized loss). ⚠ In the reference this is **acknowledged** (README: "off-chain top-up") — on a fork WITHOUT such a disclaimer it is a live High/Crit.
- **POOLED-UNBOND × POOL-FLOOR** (`I-07`, 🔴 cross-port-specific): the round-up-to-full-exit branch (when remaining < dust) MUST gate on "the target pool holds the whole inflated amount", NOT only on the dust condition. fingerprint: canon `TruStakePOL.sol:634` = `if (maxWithdrawal-_amount < ONE && maxWithdrawal <= validatorStake)` — the **second condition `≤ validatorStake`** prevents inflating a withdrawal beyond the target validator's stake. `ABSENT` in a port that has only the dust condition → it inflates up to the global max from a SINGLE pool → drains the pool's aggregate active stake. **The amplifier = a chain-native active-floor** (e.g. Aptos delegation_pool requires ≥10 APT active, `assert active ≥ amount+MIN`): a drain down to the floor → a third party cannot withdraw principal = a temporary freeze. The canon (Polygon, NO floor) — Bob withdraws normally. **Lesson: on any staking chain with a pool-min-active-floor (Aptos/Cosmos variants) a round-up defect = a live freeze; on Polygon it is dead.**
- **STAKED-ACCOUNTING units** (`I-06`): internal `stakedAmount += actual-bought`, `−= unbonded`. fingerprint: a known audit finding = div-vs-mul in `totalStaked` (`shares/exchangeRate` instead of `·`), latent when rate==1. ⚠ ports often **bypass** this by storing NOT internal accounting but a live query (e.g. `query_delegation`, `delegation_pool::get_stake`) → the drift class changes (a live query automatically reflects a slash, but the claim-pool desync remains).
- **RECEIPT-MINT-AUTH** (`I-09`): mint only by the vault/program. fingerprint: a PDA (Solana `mint_authority`), MintCapability in a resource account (Aptos), cw20 minter==contract (CosmWasm), OZ `_mint` internal (Solidity). ⚠ ports keep a test-mint behind `#[cfg(feature=test)]` — check the DEPLOYED bytecode (grep the variant in wasm/ELF), not just the source; confirm deployed=repo-HEAD by hash (deterministic `workspace-optimizer`).
**Cross-TARGET transfer:** this reference = a family of forks (Lido-like LSTs, Stader, any multi-validator staker). POOLED-UNBOND×POOL-FLOOR — look for it on EVERY staker over a chain with a min-active-floor. SLASH-CLAIM-RECONCILE — on EVERY one where slashing is enabled and the claim comes from a shared pool.

## Balancer V3 (transient-accounting Vault / Gyro / LBP / surge-hooks) — banked 2026-08-09

Primitive invariants + the canonical mechanism (from a 17-axis hunt):

- **LBP-VIRTUAL-BALANCE × ACCOUNTING-VIEW-SPLIT** (`I-83`, 🔴 fragile-primitive): an LBP adds
  `_reserveTokenVirtualBalanceScaled18` to the reserve BEFORE swap/computeInvariant, but the Vault's proportional
  add/remove computes from the REAL balances (`BasePoolMath.computeProportional*` without a pool call). The asymmetry
  is REAL (a swap sees real+virtual, proportional sees real-only), but it is NOT exploitable ONLY as long as
  3 gates hold simultaneously. **canon fingerprint (all 3 are mandatory):** (1) add-liquidity is owner-only+pre-sale
  (`LBPCommon.onBeforeAddLiquidity`: `router==_trustedRouter && sender==owner()` + `onlyBeforeSale`); (2)
  unbalanced is disabled at registration (`BaseLBPFactory._registerLBP`: `disableUnbalancedLiquidity=true` +
  `computeBalance` reverts `UnsupportedOperation`); (3) temporally disjoint windows (add: `now<startTime`; remove:
  `now<startTime ∨ now>endTime`; swap: `startTime≤now≤endTime` — the boundary conditions coincide, no 1-block
  overlap). **`ABSENT`/live** = a future LBP fork drops the owner-only add (a permissionless multi-LP LBP)
  OR the temporal separation → the asymmetry comes alive instantly (the attacker mints BPT without virtual → swaps against the
  curve with virtual). ⚠ RE-CHECK on EVERY new LBP pool type/fork. ref: `LBPool.sol:200-267` +
  `LBPCommon.sol:67-72,188-227` + `BaseLBPFactory.sol:97-98`.
- **fingerprint:** `_reserveTokenVirtualBalance\w*` (LBP virtual reserve — on a match, check the 3 gates above)
- **anti-fingerprint:** an LBP variant WITHOUT `onlyBeforeSale` on add OR WITHOUT `disableUnbalancedLiquidity=true`
  → the virtual-balance asymmetry is live.

- **SURGE-IMBALANCE-CLAMP × STRICT-TRIGGER** (ECLP-specific): an imbalance metric clamped to
  `FixedPoint.ONE` and fed into a strict-`>` surge trigger → on saturation old=new=ONE, `ONE>ONE`=false →
  the surge stays silent on the most extractive swaps. **defect fingerprint:** `imbalance > FixedPoint.ONE ?
  FixedPoint.ONE : imbalance` (a clamp) TOGETHER with `newImbalance > oldImbalance && newImbalance > threshold`
  (strict `>`). reference code: `ECLPSurgeHook.sol:262` + `SurgeHookCommon.sol:272`. **anti-fingerprint (canon
  safe):** a metric WITHOUT an artificial clamp — `StableSurgeMedianMath.sol:17-37` `totalDiff.divDown(totalBalance)`
  is naturally <1, no plateau → the strict-`>` does not stick. The class is transferable to ANY threshold trigger with a
  clamped metric (look for clamp-before-strict-inequality).

- **POOL-DECLARED-MIN-FEE × DYNAMIC-FEE-BYPASS**: a pool declares `getMinimumSwapFeePercentage()`
  as a security floor (Gyro E-CLP/2-CLP = 1e12 against add/remove round-trip profitability), the Vault enforces
  it ONLY for the static fee and does NOT clamp the hook's dynamic fee. **fingerprint gap:** `_setStaticSwapFeePercentage`
  checks `< getMinimumSwapFeePercentage() → revert`, but `callComputeDynamicSwapFeeHook` checks only
  `> MAX_FEE_PERCENTAGE` (no lower clamp). ref: `VaultCommon.sol:356` vs `HooksConfigLib.sol:175-198`.
  ⚠ OOS on Balancer (`IHooks.sol:232-239` documents the hook's responsibility + the official hooks are not sub-static),
  BUT **on a fork WITHOUT such an IHooks disclaimer OR with an official sub-static discount hook = live**.

- **GYRO-INVARIANT-SQRT-MARGIN** (docs-runtime-gap): the Gyro 2-CLP docstring promises a "very small margin"
  which is NOT in the code (the E-CLP sibling has an err-bound ×20/×40). **canon-safe mechanism** = a sqrt tolerance-check
  bound (`GyroPoolMath.sqrt:47-50` require `guessSquared ∈ input±guess·tol/1e18`) → an error in L of a few wei for
  L~1e21+ → de-minimis (executable: do/undo worst gain −1 wei). **anti-fingerprint (live):** a Gyro variant
  where sqrt has NO tolerance-require OR the margin compensation is smaller than the sqrt error → do/undo extraction. Lesson:
  "a documented margin is not in the code" ≠ automatically a bug — measure the sqrt error-bound by execution.

## § ETH-staking / Beacon-proofs (compounding LST — Origin/EigenLayer/Lido/ether.fi family)

- **BEACON-SSZ-PROOF-COUPLING** (canonical mechanism, ref: Origin `BeaconProofsLib.sol`/`Merkle.sol` 2026-08,
  EigenLayer-proven): an on-chain SSZ merkle inclusion proof of beacon-state fields (validator balance / pending
  deposit / withdrawable_epoch) via the EIP-4788 root. **canon-safe mechanism = TWO coupled guards:** (1) per-caller
  `require(proof.length == CONST)` EXACT (never `>=`) where CONST = gindex-bit-length−1 witnesses; (2) index
  type-width EXACTLY = gindex field-width so the variable index can NEVER inflate the gindex leading bit
  (`validatorIndex` uint40 vs VALIDATORS_LIST_HEIGHT 41; `balanceIndex<2^38`; `require(pendingDepositIndex<2^27)`).
  Together → `processInclusionProofSha256` walks exactly `depth` halvings, lands on gindex==1 (root). **fingerprint:**
  `processInclusionProofSha256` + exact `== <len>` per entrypoint + an index-bound require BEFORE gindex use.
  **anti-fingerprint (live):** any entrypoint using `>=` on proof.length, OR an index type WIDER than its
  gindex field (the index bleeds into field-gindex bits → wrong-subtree landing → forge a fake leaf that verifies →
  over-report validator balance → OToken/LRT mispricing). A missing terminal `index==1` assert is SAFE **only** if
  both couplings hold — check them, not the absent assert.

- **OTOKEN-ASYNC-QUEUE-CONSERVATION** (canonical mechanism, ref: Origin `VaultCore.sol` withdrawal queue 2026-08):
  FIFO async redemption (burn-OToken-at-request, 1:1, claim when `request.queued <= claimable` + delay). **canon-safe
  mechanism:** `claimable` advances ONLY by free liquidity — `unallocated = assetBalance − (claimable − claimed)`,
  `addedClaimable = min(queued−claimable, unallocated)` → invariant `claimable ≤ claimed + assetBalance` (reserved
  liquidity always physically present, no double-claim). checkBalance = `balance + claimed − queued` (excludes
  reserved), →0 on insolvency. **fingerprint:** metadata {queued, claimable, claimed, nextIndex} + `claimable−claimed`
  = allocated + a min-with-unallocated advance. **anti-fingerprint (live):** a fork that advances `claimable` by
  `assetBalance` WITHOUT subtracting `(claimable−claimed)` already-reserved → the same WETH backs two claims → drain;
  OR queued/claimed use DIFFERENT scaleBy rounding (drift → claimed>queued). FIFO 1:1 + a maxSupplyDiff-freeze on
  insolvency = an intended bank-run mitigation, not a bug.

### Compound v2 fork — CToken/Comptroller/Timelock (JustLendDAO ref, TRON 2026-08-18)
Recognition (`fingerprint:`): `Unitroller`+`Comptroller`(mintAllowed/borrowAllowed/getHypotheticalAccountLiquidityInternal/liquidateCalculateSeizeTokens) + `CErc20Delegator`(proxy)+`CErc20Delegate`+`CEther` + `JumpRateModelV2`/`WhitePaperModel` + `Exponential`/`CarefulMath` (error-code returns) + `Timelock`(GRACE_PERIOD 14d/MINIMUM_DELAY 2d) + `GovernorBravo`. Solidity 0.5.x = early Compound (functions return error codes, they do not revert). Reference: `compound-finance/compound-protocol`.
Key invariants (all ENFORCED in the canon — check a fork's DEVIATIONS, not the canon itself):
- **doTransferIn = balance-delta** (`balanceAfter - balanceBefore`, CErc20.sol) — FoT-safe. A fork that trusts `amount` = SUBSTITUTED (a bug). JustLend: ENFORCED.
- **CEI-via-mutex:** redeemFresh/borrowFresh do `doTransferOut` BEFORE writing totalSupply/accountTokens/accountBorrows — protection ONLY by the per-market `_notEntered`. Cross-market reentrancy is alive IF the underlying is a hook/ERC777 token (CREAM $130M). The `.transfer()` 2300-gas/Energy stipend (EVM AND TRON) blocks native reentry. accrueInterest is public WITHOUT a mutex (canon) — dust, unreachable without a hook.
- **blocksPerYear** is calibrated to the chain's block time (ETH 15s→2102400; **TRON 3s→10_512_000**). A deviation = interest drift.
- **exchangeRate empty-market donation** (Hundred/Midas $M) — a fresh UNSEEDED market + CF>0 = first-depositor inflation. Check the on-chain `totalSupply`/CF of fresh markets.
- **JustLend fork additions (all privileged → on a bounty usually OOS-centralization):** `collateralFactorGuardian` (a non-admin role sets CF on opt-in markets, without a timelock/lower bound) · `reserveAdmin` (only it can `_reduceReserves`) · the pauseGuardian one-way guard is COMMENTED OUT (it can unpause). WJST governance `getPriorVotes` ignores blockNumber → flash-governance (governance OOS).
- **Oracle:** check `comptroller.oracle()` on-chain — it may NOT match the in-scope oracle asset (JustLend: the live oracle is out of scope). A poster/reader-medianizer (WinkLink on TRON) = admin-fed, bad data is OOS except for on-chain manipulation.
- **LIVENESS SPOF:** getHypotheticalAccountLiquidityInternal iterates the borrower's accountAssets; price==0 OR a snapshot error on ANY entered market → PRICE_ERROR/SNAPSHOT_ERROR for the WHOLE account → liquidation is blocked entirely; there is no force-exit (exitMarket is the borrower's alone). Live if a deprecation/oracle drop leaves a 0-price LISTED market (check `getAllMarkets()`×price==0). Rate-freeze: accrueInterest `require(rate<=borrowRateMaxMantissa=5e12/block)` — permanent if tripped (repay also calls accrueInterest); util=borrows/equity can exceed 100% when reserveFactor→100%.

---

## § Swap-Executor / DEX-Aggregator (0x-Settler-family — meta-aggregator, intent-router, swap-executor)

> Primitives of an executor contract that runs the user's funds through N external DEX/bridge integrations
> by an attacker-composed action list. Banked from an analysis of 0x Settler (2026-08-18, 6 audits, 0 payable —
> see PAT-08 in `undup_pattern_library.md`). The key to the family: security rests NOT on per-hop checks,
> but on a GLOBAL settlement invariant; look for a path where the global invariant is ABSENT.

| Primitive | Invariant | check: | canon fingerprint: | ref: | anti-fingerprint (SUBSTITUTED/ABSENT) |
|---|---|---|---|---|---|
| **final actual-balance settlement** (⭐ the key of the family) | the output to the user is measured by the executor's ACTUAL balance (`buyToken.balanceOf(this)`), NOT by the return value of a swap call | at the end of EVERY execution path: `balanceOf(address(this)) >= minAmountOut` before payout? Find paths WITHOUT it (bridge/exit paths!) | `_checkSlippageAndTransfer`: `amountOut = buyToken.balanceOf(address(this)); if (amountOut < minAmountOut) revert` at the end of `_execute` | 0x Settler `SettlerBase.sol:_checkSlippageAndTransfer` — the comment: "must ensure the user's want token increase is coming directly from us" | slippage/output is computed from an integration's return value (`buyAmt := mload(...)`) without reconciling against the balance; **or an execution path (a bridge flavor) does not call the final check at all** |
| pool-genuineness (callback model) | the swap callback accepts only a pool derived via CREATE2 from the canonical factory+initHash | `msg.sender == derived pool`? are the factory/initHash constants ACTUALLY used in the derivation? | a transient `operator` slot: `setOperatorAndCallback(derivedPool, selector)` → in the fallback `caller()==operator` + a selector match + `operator≠payer` | 0x Settler `core/Permit2Payment.sol:57-110` + `UniswapV3Fork.sol:_toPool` | the pool comes from `abi.decode(actionData)` without derivation; **the factory/initHash constants are declared but referenced nowhere** (the check was intended and dropped out — 0x MaverickV2/EulerSwap/Hanji) |
| ephemeral (transient) allowance | a one-time allowance is bound to the triple (operator, **sender**, token) — ONLY the caller's own tokens can be pulled | does the allowance-slot key include the initiator's `msg.sender`? is the debit via an underflow check? is the target checked not to be an ERC20? | `_ephemeralAllowance(operator, sender, token)`; `_set(allowance, _get(allowance) - amount)` (underflow = validation); `_rejectIfERC20(target)` before an arbitrary call | 0x `AllowanceHolderBase.sol:_exec/transferFrom/_rejectIfERC20` | an allowance by (operator, token) without sender → other people's tokens; a missing `_rejectIfERC20` → confused-deputy via arbitrary calldata on an ERC20 |
| restricted-target guard | an arbitrary call target from action data cannot be a privileged dependency (Permit2/AllowanceHolder/RFQ-settlement) | is `_isRestrictedTarget(target)` called on EVERY path with an attacker target? does each integration add its own dependency to the list? | `if (_isRestrictedTarget(pool)) revertConfusedDeputy();` + a per-integration override `target == address(_DEP) \|\| super._isRestrictedTarget(t)` | 0x `core/Basic.sol:20-23`, `Bebop.sol:101`, `Permit2Payment.sol:187,398` | a new trusted singleton is added to an integration but NOT added to `_isRestrictedTarget`; **or the check is deliberately omitted because "the selectors do not intersect"** (0x `Settler.sol:140-143` — latent when a permit type/target is added) |
| counterparty-bound RFQ witness | the maker's signature binds the counterparty, token and amount (not only the amount) | does the signed struct contain `counterparty`, and is it recomputed from the actual `_msgSender()`? | the witness `Consideration{token, amount, counterparty: _msgSender(), partialFillAllowed}` in Permit2 `permitWitnessTransferFrom` | 0x `core/RfqOrderSettlement.sol:93-101` | a witness without a counterparty → any filler at someone else's price; the recipient in the signature is NOT required (it only routes the filler's proceeds) |
| deterministic multi-chain deploy + sig-domain | the same executor address on N chains does NOT give cross-chain signature replay | does the signature domain bind `block.chainid` (its own or Permit2's), is the nonce per-chain? | signatures ride on Permit2 `permitWitnessTransferFrom` (its EIP-712 domain includes chainId) + an unordered nonce bitmap | 0x Settler (12 chains, one address) — I-04 ENFORCED | a home-grown EIP-712 domain without chainId under a deterministic multi-deploy = instant cross-chain replay |
| submarine (counterfactual) receiver | the address where bridged funds arrive is cryptographically bound to the beneficiary AND the payload | does the `salt` include the owner/beneficiary? does signature verification re-derive the address from (root, owner) and require `== address(this)`? | `salt = keccak256(root‖initialOwner)`; `_verifyDeploymentRootHash`: `keccak(0xff‖factory‖salt‖initHash) == address(this)`; the leaf binds `chainid` | 0x `CrossChainReceiverFactory.sol:411-413, 1102-1124, 359-374` | the salt only from root/payload without an owner → front-run deploy with a foreign owner; a signature check against a passed root without re-deriving the address → forgery |
| bridge-sender amount provenance | the amount sent into the bridge is bound to the funds of THIS action, not to the contract's full balance | does the module take the whole `balanceOf(address(this))` or the action's delta? is the bridge recipient validated? | canon: bridged amount = the amount pulled in this action; the recipient is tied to the signed order | 0x bridge modules (Across/CCIP/DeBridge/LZ-OFT/Stargate/Mayan) — **all take the full balance**, safe ONLY because the flavor = taker-submitted+atomic (D-02) | a full-balance sweep + an unvalidatable recipient **in a NON-atomic/non-self-funded flavor** (gasless/solver/multi-user batch) = theft of other people's funds. ⚠ Check FIRST whether there is a non-taker-submitted path to a bridge module |

## § BoringVault / Arctic (Veda) — vault-primitive
- **I: every vault.manage call is proven against a strategist merkle leaf** = keccak(decoder,target,valueNonZero,selector,packedArgs).
  ref: ManagerWithMerkleVerification.manageVaultWithMerkleVerification + `totalSupply` MUST remain constant after manage
  (ManagerWithMerkleVerification.sol:158). fingerprint: `manageRoot|_verifyManageProof|MerkleProofLib.verify`.
  ⚠ SUBSTITUTED-risk: TellerWithBuffer._afterDeposit/_beforeWithdraw + the receiveFlashLoan repay call vault.manage
  DIRECTLY (no merkle) — constrained by an immutable-helper-allowlist / flashLoan-leaf, not merkle. Verify helper immutability.
- **I: share mint/burn only via Teller roles; manage only by the Manager.** ref: BoringVault.enter/exit/manage `requiresAuth`
  (RolesAuthority). ⚠ enter/exit do NOT call beforeTransferHook (only transfer/transferFrom) → the ShareWarden blacklist
  is bypassed on mint (a compliance edge, not theft).
- **I: yield-streaming per-event cap (maxDeviationYield via TWAS) protected by an accumulator reset.** ref:
  AccountantWithYieldStreaming._updateCumulative sets lastUpdateTimestamp before every mint/burn → retroactive credit is closed.
- **I: cross-chain share bridge burn-source==mint-dest 1:1, peer+endpoint auth.** ref: OAppAuthReceiver.lzReceive
  (OnlyEndpoint+OnlyPeer, the fork KEEPS the canonical check) / ChainlinkCCIPTeller (onlyRouter+selector+targetTeller==sender).
  fingerprint: `_getPeerOrRevert|OnlyPeer|allowMessagesFrom`. ⚠ the per-chain accountant is independent → cross-chain rate desync
  is possible; check bridge peer-connectivity (allowMessagesFrom) before treating a desync as arbitrable.

## § Enzyme V4 Sulu (vault-management / fund-of-funds primitive) — 2026-08-19
Open when an Enzyme fork / vault-management / fund-of-vaults / EP-wrapper architecture is recognized.

### Cross-fund share-price valuation (EnzymeVaultPriceFeed)
- **Invariant:** a parent fund holding child-vault shares values them via `FundValueCalculator.calcNetShareValue`,
  which, BEFORE reading GAV, calls `comptrollerProxy.callOnExtension(feeManager, 0, "")` (fee-settle).
- **`ref:` reference enforcement:** `callOnExtension` carries a `locksReentrance` mutex (`reentranceLocked` bool, per-comptroller) →
  when the child is mid-redeem (child locked) the parent read REVERTS "Re-entrance". `fingerprint: valuation-path-grabs-reentrancy-lock`
  → read-only reentrancy on the share price is STRUCTURALLY impossible (no ERC777 gate needed). A missing guard on `calcGav` itself
  (public, no mutex) is HARMLESS — all value-realizing consumers are guarded.

### Derivative price-feed set (fixed, non-flash-manip)
- **Invariant:** GAV manipulation requires a flash-manipulable registered rate.
- **`ref:` deployment fact (ETH):** EXACTLY 6 derivative feeds — `ERC4626PriceFeed` (raw `convertToAssets`, storage-tracked, 0-naive
  verified by enumeration), `EnzymeVaultPriceFeed` (child GAV, reentrancy-defended), `EtherFiEthPriceFeed`/`StaderSDPriceFeed` (accrual/TWAP oracle),
  `PeggedDerivativesPriceFeed` (constant+deviation-guard), `RevertingPriceFeed` (no-read). **NO Compound/cToken, NO Curve/Balancer-LP,
  NO Aave-aToken feed** (positive-proof find-empty) → read-only reentrancy/spot-manip are inapplicable. `fingerprint: no-LP-feed-no-spot-manip`.
- **`fingerprint: deviation-guard-asymmetry` (latent):** `AggregatorRateDeviationBase` (clamp) is applied ONLY to
  `PeggedRateDeviationAggregator`, ABSENT in ERC4626/Stader/wstETH/SmarDex → a single point of failure. The NoDepeg/
  CumulativeSlippage policies read the same unclamped VI → blind. Armed by a future naive registration. Enumeration recipe: `enum_derivatives.py`
  (DerivativeAdded topic `0xaa4ae250...`, ERC4626PriceFeed `0x66aA5b...86BB`; the naive test = `totalAssets ≈ asset.balanceOf(vault)`).

### External Position getManagedAssets (EP-value-accounting)
- **Invariant:** getManagedAssets reflects ALL EP-held/escrow-held value.
- **`ref:` bug locus (manager-trust OOS/known issue):** MysoV3 `getManagedAssets` returns EMPTY for a closed-but-skip-withdrawn
  escrow with a balance (§8.1 of a third-party audit = intended manager flexibility) · Solv `require settlePrice>0` reverts · Maple
  `lockedShares` no-try-catch reverts on pause · GMXV2 claimable-underflow. **calcGav iterates ALL active EPs WITHOUT a per-EP
  try/catch (`__calcExternalPositionValue:527-529`) → any reverting EP bricks the fund's GAV. BUT an in-kind redeem is EP-independent
  (`getTrackedAssets()` + `balanceOf`, not getManagedAssets) → the freeze is recoverable, in-kind survives.** `fingerprint:
  one-bad-EP-bricks-calcGav-but-in-kind-survives`.

### Integration reconcile (measured-delta)
- **`ref:` reference:** `IntegrationManager.__postProcessCoI` — incoming = post−pre balanceOf (≥minIncoming), spend = pre−post
  (Approve/Transfer implicit-max). The adapter target is immutable; approve-reset post-call. FoT only shortchanges the actor. → adapter
  theft/mis-declaration is closed by measured-delta. `_exchange` is allowlisted; `_exchangeApproveTarget` is attacker-controlled BUT the wrapper is
  stateless-refund → a dangling approve is inert (Low).

### Meta-tx sender (GSN)
- **`ref:`:** `GasRelayRecipientMixin.__msgSender` — the appended sender (last 20 bytes of calldata) is trusted ONLY when
  `msg.sender==trustedForwarder` (a GSN-verified signature); a direct call → `msg.sender`. Sender spoofing is impossible without being the forwarder.


## § CometBFT / proto-decode (sei-tendermint-style forks)

- **`FromProto-decode-must-bound-scalars-before-arithmetic`** — invariant: any `XxxFromProto` that decodes
  untrusted proto and calls arithmetic with a panic-guard (sum-overflow, div-by-zero, index) MUST validate
  scalar fields BEFORE the arithmetic, not AFTER. `ref:` upstream CometBFT `ValidatorSet.ValidateBasic` must run BEFORE
  `TotalVotingPower()`. **canon fingerprint:** decode→ValidateBasic→arithmetic. **SUBSTITUTED/defect:**
  a `ValidatorSetFromProto` that calls `TotalVotingPower()` BEFORE `ValidateBasic()` → panic
  on an over-cap voting_power before validation.
- **`decode-guard-guards-shape-not-value`** — invariant: a decode guard (wireguard `protoutils.Scan`) must
  cover both the COUNT and the VALUE ranges of liveness-critical scalar fields. `ref:` a `validator.wireguard.go` that caps
  only MaxCount leaves a value gap open. **recover boundary:** the consensus `receiveRoutine` re-panics
  (halt); gossip reactors (blocksync/statesync/evidence) `defer recover()` (safe).

---

## § UniswapV3 Automated-LP Vault (Charm Alpha Vaults / Gamma / Arrakis family)

**Primitive:** an ERC20-share vault over a UniV3 pool; deposit mints shares ∝ `getTotalAmounts` (read at slot0 SPOT); withdraw burns proportional liquidity (price-independent).

**Invariant — deposit spot-manipulation cannot over-mint (round-trip theft impossible):**
- `ref:` charmfinance/alpha-vaults-v2 AlphaProVault.sol `_calcSharesAndAmounts` + proportional `withdraw`.
- `fingerprint:` (a) deposit pulls tokens in a FORCED ratio `(amount0,amount1) ∝ (total0',total1')` (`cross=min(...)`, `amount_i = cross/total_j`) — an attacker cannot tilt toward the cheap token; (b) the withdraw split is `shares/totalSupply` of liquidity units + idle, NO price input.
- **Why safe (convexity/tangent bound):** amounts read at the manipulated price P' but VALUED at the true price P satisfy `T0'·P + T1' ≥ T0_P·P + T1_P` (surplus `ΣL(√P−√P')²/√P' ≥ 0`, a Bregman divergence — the LP-value curve is concave in P, any tangent lies above). ⇒ manipulation only INFLATES the reported total ⇒ the depositor gets FEWER shares ⇒ over-mint profit `= k·(W−(P·T0'+T1'))/W ≤ 0` in every branch. Holds for full-range too.
- **Contrast (why Arrakis/Gamma-style designs can FALL):** their share formulas / non-proportional mint-burn allow over-minting; the FORCED-ratio + proportional-withdraw + convexity combination is what defends. If a family member computes shares by VALUING the position (not forced-ratio) or lets withdraw depend on price → the invariant BREAKS → check that member.
- **First-deposit:** 1e3 MINIMUM_LIQUIDITY minted to a DEAD address (factory) + `require(shares>0)` revert-on-zero → inflation/donation grief returns 1/(1+locked) to the attacker, unprofitable.
- **Rebalance MEV:** if rebalance sizes liquidity at SPOT but gates the tick within `maxTwapDeviation` of TWAP (no TOCTOU between the guard read and the sizing read) → sandwich extraction is bounded by `maxTwapDeviation` (manager config); permissionless-when-delegate==0 is a documented tradeoff. Funds are un-freezable if withdraw is independent of rebalance.
- **Attack surface that WOULD break it:** a fee-on-transfer/rebasing pool token (deposit credits the requested amount, not the received one); a configurable "wide" order overlapping base (Charm v2.1 had `wideThreshold`, drainable — the full-range fixed-tick version does NOT).


## § Move / Sui CLMM (Orca-Whirlpools / UniV3 ports) — banked 2026-09-05

### Growth accumulator MUST wrap (fee_growth_global / reward growth_global)
- Canonical (UniV3 uint256 / Orca Rust): feeGrowthGlobal & reward growth_global OVERFLOW-AND-WRAP by design; downstream fee/reward-inside uses modular (wrapping) subtraction assuming self-consistency mod 2^N.
- **fingerprint (canonical wrap):** `MAX_U128\s*-\s*n2\s*\+\s*n1\s*\+\s*1` (true wrapping_sub) OR a real two's-complement XOR/carry add.
- **anti-fingerprint (SUBSTITUTED — the bug):** `fun wrapping_add[\s\S]{0,120}assert!\(\s*!` — a helper NAMED wrapping_add that ABORTS on overflow (Move has no native wrapping → ports mis-implement). Paired with a truly-wrapping wrapping_sub = asymmetry. Consumers `fee_growth_global`/`growth_global`/`tokens_owed`/`amount_owed` → DoS-at-overflow (swap-DoS if on the fee side; reward side gated on active emissions). Reachable via NO-min-liquidity (L=1) dust inflation. Severity is gated by the program's impact list (DoS is often OOS) + the attacker's fee cost (~2^64 units).

### CLMM primitives VERIFIED faithful in turbos (reuse as an ENFORCED baseline for sibling forks)
- tick-cross liquidity_net sign (a_to_b→neg), fee_growth_inside below/above (gte cur/lower, lt cur/upper) all wrapping_sub, cross_tick outside-flip (global-outside), rounding A-side ceil via math_u256::div_round (correct) / B-side mul_div_round (de-minimis), flash hot-potato (no-ability Receipt), position auth via NFT object-capability, OTW-gated fee-type creation, tick/sqrt_price = Orca constants (38 multipliers, MAX_TICK 443636, MIN/MAX_SQRT_PRICE_X64).
- **fingerprint (Orca-port identify):** `get_sqrt_price_positive_tick|get_sqrt_price_negative_tick|443636|BIT_PRECISION` → apply this baseline, diff only the deltas.

### Reward-campaign RESET must settle-all + clear per-tick outside
- **Invariant:** any fn that zeroes a monotonic reward `growth_global` (reset/restart campaign) MUST (a) call the settle-accumulator fn FIRST (next_pool_reward_infos analog) AND (b) clear every per-tick `reward_growths_outside[k]` snapshot — otherwise post-reset `inside = wrapping_sub(0, staleG0) ≈ 2^128` and downstream `mul_div_floor(inside, liquidity, Q64) as u64` behaves at the **u64-cast boundary**: L≥2 → overflow-abort on the SHARED update_position path → burn/decrease_liquidity abort → LP PRINCIPAL frozen cross-user; L==1 → fits+inflates amount_owed≈2^64 → `collect(requested=vault)` DRAINS the whole reward vault (permissionless theft).
- **⚠ SEVERITY CALIBRATION (PoC-corrected):** the FREEZE is **RECOVERABLE, not permanent** — if the operator later re-funds (add_reward + emissions) and time passes, `growth_global` climbs back above the stale `outside` and `inside` un-wraps → frozen withdrawals succeed again (a runnable recovery PoC passes). So freeze = a temporary DoS (High/Medium), while the **DRAIN (L==1 vault theft) is the irreversible High** and should lead the report. Do NOT claim a "permanent Critical freeze" on this class without a recoverability differential (reset→re-fund→still frozen?).
- **Canonical ref:** UniV3-staker / Orca use EPOCH-KEYED reward growth — a "reset" opens a NEW epoch, global is never zeroed under live positions. A port that drops epoch-keying and does a raw global-zero = **SUBSTITUTED**.
- **fingerprint (the bug):** a `reset*`/`clear*` reward fn that sets `growth_global = 0` / `emissions_per_second = 0` and does NOT call the settle fn its SIBLINGS (add_reward/update_reward_emissions) DO call, AND does NOT loop over live ticks zeroing outside.
- **Trigger:** an operator role but a BENIGN routine op (distinct from centralization-OOS). **TRANSFER candidates:** other Sui/Move CLMM DEXs (grep their reward-reset paths). See undup_pattern_library `reward-reset-without-settle-freeze`.

### Reward accrual time-unit MUST match the last-updated advance (sub-second starve)
- **Invariant:** if reward growth accrues as `growth += (time_delta * emissions) / liquidity` with `time_delta = (now_ms - last_ms) / 1000` (integer seconds), then `last_updated` MUST advance only by the CONSUMED whole-second portion — NOT to the full `now_ms`. Advancing `last_updated = now_ms` unconditionally while `time_delta` floors to 0 for sub-second gaps means a permissionless poke every <1s keeps `time_delta == 0` forever → `growth_global` never advances → emissions are never distributed (griefing/starvation of the incentive campaign).
- **Canonical ref:** accrue in the SAME unit you advance (ms↔ms), or carry the sub-second remainder.
- **fingerprint (the bug):** `last_updated\w*\s*=\s*.*timestamp_ms` (a full-ms store) co-located with a `/\s*1000` (or `/ 1000`) integer-second delta in the accrual fn; a permissionless entry (any mint/poke) is reachable → sub-second starve. Reachable via `pool_fetcher::compute_swap_result`-style `public entry &mut Pool` view-mutators (zero-capital poke).

## § Rootstock Flyover LBC (fast peg-in/peg-out bridge, EVM Solidity) — banked 2026-09-05

Reusable primitives for the Flyover / BTC-SPV-peg-bridge family (rsksmart/liquidity-bridge-contract v2 + any fork).

- **fast-bridge-SPV-binding** — the pegout refund binds btcTx→quote: `hashBtcTx(btcTx)` (double-SHA256, txid) fed to `bridge.getBtcTransactionConfirmations` (merkle proof) AND the local `BtcUtils.getOutputs` reads FIXED indices (output[0]=pay-to-quote.depositAddress, output[1]=OP_RETURN quoteHash). `ref:` PegOutContract.sol:404-497 / BtcUtils.hashBtcTx:272. `fingerprint:` `hashBtcTx=double-sha256(whole btcTx)` + fixed `_PAY_TO_ADDRESS_OUTPUT=0`/`_QUOTE_HASH_OUTPUT=1` + an amount floor sat*1e10. **A txid commitment closes output malleability** (any output change changes the txid; the getOutputs vs hashBtcTx segwit-marker asymmetry is latent-only — non-exploitable because a valid-hashing tx must be legacy bytes with ≥1 input).
- **refund-mutual-exclusion (XOR)** — a pegout quote refunds to the LP (refundPegOut) XOR the user (refundUserPegOut), never both. `ref:` PegOutContract.sol:224-225,254-255,408. `fingerprint:` paired `delete _pegOutQuotes[h]` + `_pegOutRegistry[h].completed=true` in the same call; guard `_isQuoteCompleted`. ⚠ **SUBSTITUTED variant:** refundUserPegOut relies on `lbcAddress==0`-after-delete (implicit) instead of reading the canonical `.completed` — safe only via EVM atomicity + lockstep delete/mark.
- **collateral-reservation (ANTI-pattern → a vulnerability class)** — LP collateral is a SINGLE shared unreserved pool checked point-in-time; NOT reserved per accepted quote. `ref:` CollateralManagement.sol:272-285 (isCollateralSufficient flat `>minCollateral-1`) + :187 (`Math.min(penaltyFee,pool)` slash). `fingerprint:` a per-LP scalar `_pegOutCollateral[addr]` + a point-in-time sufficiency gate + a `Math.min` non-reverting slash + NO reservation/lock mapping. **Vulnerability class:** N concurrent quotes share one snapshot → penalty under-collection; + a refundPegOut hard-revert-on-insufficient composed with a permissionless refundUserPegOut = late-LP escrow theft. Check any peg/LP-bridge fork for this exact shape.
- **EIP-712-quote-binding** — a quote is signed via OZ EIP712Upgradeable; ALL struct fields are covered by the hash; chainId+lbcAddress are bound explicitly. `ref:` Quotes.sol:92-199 (full-field encode split part1/part2) + PegOut/PegIn `_validate*Quote` chainId==block.chainid + lbcAddress==address(this). `fingerprint:` `_hashTypedDataV4` + `keccak(encode(part1,part2))` covering every field + `InvalidChainId` + a distinct PegIn/PegOut typehash. **No malleability** (all fields in the hash).
- **HSM-host-untrusted-signing (segwit re-verify)** — the powHSM firmware independently re-derives the BIP143 segwit sighash from the raw tx it authorizes (does NOT trust the node-provided sighash/amount). `ref:` rsk-powhsm firmware/src/powhsm/src/auth_tx.c:50-260. `fingerprint:` the HSM re-computes prevouts_hash + sequences + input outpoint + SIGHASH_ALL + double-sha256 from the parsed raw tx; the node's PowHSMSignerMessage.sigHash is advisory. **An amount lie → an invalid sig (BIP143 commit) = DoS, not theft.** (The host-untrusted model is preserved on the segwit path, = legacy.)
