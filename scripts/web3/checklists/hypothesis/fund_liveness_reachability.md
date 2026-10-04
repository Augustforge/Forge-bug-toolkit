# Fund Liveness / Permanent Freeze — Exit-Reachability Checklist

Pattern (MIRROR of custody extraction): funds sit in a phased-lifecycle contract under a
promise that participants can ALWAYS exit (refund on failure, claim/redeem on success), but
the state TRANSITION that enables the exit can never fire — or one party can withhold/block
it — so capital is frozen forever. **No theft required; "permanent freezing of funds" is its
own Critical/High class on Immunefi/Cantina.**

Reference: **HONG ICO 2026 ($2M / 1003 ETH trapped 9 YEARS → white-hatted)** —
`refundMyIcoInvestment()` is gated by `notLocked`; the lock/release state advances only inside
`internal tryToLockFund()`, called solely from `createTokenProxy()` (token purchases). ICO
missed its minimum, buying stopped in 2016, the state machine never reached its terminal
"released" branch, and every original investor's refund sat dormant until a white-hat
re-activated the path. → **The exit existed in code but its enabling transition was orphaned.**

Tool: `scripts/web3/advanced/state_machine_analyzer.py` (emits `[FREEZE?]` flags)
Threat model: `scripts/web3/threat_models/fund_liveness_terminal_state.yaml`

## When to apply
Any contract that holds funds AND has phases / a lifecycle: ICO / crowdsale, vesting,
escrow, auction, DAO-fund, staking-lock, locker, or a vault with a finalize/settle step.
Tags: `ico`, `crowdsale`, `dao`, `vesting`, `escrow`, `auction`, `staking`, `lifecycle`,
`liveness`, `custody`.

## Checklist
1. [ ] **Enumerate every exit:** `withdraw / refund / claim / redeem / collect / unlock / exit / release / harvest`. List each one.
2. [ ] **Identify each exit's gate:** which modifier / `require` / state var must be true to pass? (`notLocked`, `onlyDistributionReady`, `isFinalized`, `now >= deadline`, `phase == X`.)
3. [ ] **Find ALL writers of each gate var.** Run the analyzer; it maps gate → writers + visibility.
4. [ ] **Activity-gated test:** is the only writer `internal`/`private` reachable from a SINGLE path (a deposit/buy/vote)? If that activity ceases, does the gate ever flip again? (HONG = no.)
5. [ ] **Uncalled-finalizer test:** does the exit require a `finalize()`/`settle()`/`advance()` first? WHO is incentivized/able to call it? If nobody → frozen.
6. [ ] **Time-trap test:** terminal branch needs `now >= deadline` AND a fresh call to the driver? After the deadline, who makes that call?
7. [ ] **Downstream-revert test:** does the exit make an external call BEFORE paying out (sub-wallet pull, sweep, ERC-20 transfer to a possibly-blacklisting/insolvent target)? One permanent revert bricks the exit for all.
8. [ ] **Adversary-blockable test:** unbounded loop over a user-growable array in finalize/distribute? `address(this).balance` equality breakable by force-send? recipient that reverts on receive?
9. [ ] **Scope filter:** is the gate a DOCUMENTED pause/guardian/emergency-freeze (designed-trust, likely OOS) or a STRUCTURAL reachability bug (findable)? (See `[[feedback_ton_self_destructive_severity]]`.)

## Confirmation
- Static: analyzer prints `[FREEZE?] exit() gated by [gate] <- [writer(internal)]`. Then read the writer's call-sites — show the only path to it has ceased / can be withheld.
- Foundry fork: drive the contract to the parked state (e.g. let the deadline pass without the driving activity), then prove the exit reverts for a legitimately-entitled user; show no non-privileged call sequence makes it succeed.

## Severity rubric
| Finding | Default |
|---|---|
| User funds permanently unrecoverable (no actor can ever exit) | Critical |
| Adversary can cheaply & permanently freeze others' exits (DoS-to-freeze) | High-Critical |
| Exit reachable only via an uncalled/unincentivized finalizer | High |
| Temporary freeze (recoverable by a privileged but live actor) | Medium-High *(program-dependent)* |
| Documented pause/guardian freeze | OOS unless program pays for it |

## Cross-refs
- `liquidity_locker_privileged_unlock.yaml` (mirror: privileged actor UNLOCKS others' funds — extraction, not freeze)
- `validator_set_quorum_integrity.yaml` (a withheld/forged quorum can also freeze a bridge — sibling)
- generation: `dapphunt/prompts/hypothesis_generation.md` Lens 10 (Liveness / activity-gated exit)
- taxonomy: `methodology/hypothesis_taxonomy.md` Category 13.6
