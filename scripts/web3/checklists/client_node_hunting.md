# Node-Client Hunting Checklist (Cat 18.12)

For blockchain **node** targets (Go/Rust/C++ client repos: validators, full nodes, P2P/RPC daemons) — NOT smart contracts. Consensus *logic* bugs live in Cat 18.1-18.11; this file is the **implementation layer around** that logic. Source: DarkNavySecurity `client-auditor`. Apply when T1 says the target is a node.

Pair with: T8 differential fuzzing (two clients → divergence is the highest-EV path on a mature node), Cat 26 (memory/secret safety in the same code), `go_language_footguns.md` / `c_cpp_footguns.md` for language-level traps.

## Severity reality (node caps — also in submission_checklist.yaml)
- Single-node crash / RPC panic ≠ Critical → **cap Medium**.
- Self-recovering resource exhaustion → **cap Medium**.
- Quorum-required exploit (attacker already controls protocol) → **Informational**.
- Critical needs: network-wide halt, consensus split / chain reorg, finality break, mass-validator removal.

## The 4 lenses (use as T1/T2 questions)
1. **consensus-invariant** — 7 invariants to assert hold under adversarial input: canonical-state consistency · deterministic fork resolution · validation uniformity (all nodes accept/reject the same) · state-read ordering · message-rule consistency · protocol-activation synchrony (fork/upgrade epoch) · crash-recovery safety. Evidence format per finding: *external input + state transition involved + which property breaks*.
2. **network-surface** — resource-exhaustion (quantify injection-rate vs cleanup-rate) · peer-reputation gaming · RPC→network amplification path · dedup/bloom-cache poisoning · cleanup gaps.
3. **state-resource** — reserve resources BEFORE expensive work; release on EVERY failure path; cross-system DB atomicity (two stores must commit/rollback together).
4. **memory-concurrency** — use-after-free across an async boundary; split-lock state inconsistency (two aspects of one state under different locks); lock-order inversion; holding a lock across `await`.

## Two operational checks
- **Zero-Trust Message Check** (P2P handlers): Can an *unsolicited* message arrive with no prior request? Does it cause state change? Is there request-ID / sequence / pending-set correlation? Does the handler distinguish requested from spontaneous? What happens at 10k msg/s? Trace data lifetime: injection_rate vs cleanup_rate → exhaustion risk.
- **Cross-Subsystem Boundary scan** (depth-ceiling seam for nodes): find every place a *lower-trust* layer (P2P/RPC handler) calls a *higher-trust* layer (consensus/state) — verify trust assumptions are re-validated AT the boundary, not assumed from the caller. 5 steps: locate crossing → trace attacker-controlled data → compare caller-vs-callee trust expectations → verify defenses (validation/sync/ordering/resource/cleanup) → confirm reachability.

## Attack-pattern library (PAT — sweep each)
- **Batch break-vs-continue** — one malformed item `break`s instead of `continue` → partial processing / wrong winner selection.
- **Negative/illegal input panic** — deferred processing path re-uses input without re-validation → panic.
- **Validator-set hook observes intermediate state** — hook fires mid-transition when a max-count is temporarily exceeded.
- **Vote dedup composite-key gap** — dedup key missing one of {signer, domain, height, nonce} → double-influence.
- **Non-determinism → chain split** — map-iteration order in leader/selection; platform-dependent `usize`/`size_t`; two decoders disagree on the same bytes.
- **RPC panic** — `unwrap`/`expect`/nil-deref/index-OOB reachable from a public handler → crash-DoS.
- **Pay-once amplification** — one cheap action enqueues unbounded later work with no per-block quota.
- **Module wiring / mock-startup** — code compiles but isn't registered at runtime; tests exercise mocks not real wiring (node-scale mock-vs-prod, Superform sibling).
- **Fee/gas snapshot timing** — gas measured after post-exec work; refund credited to sponsor not originator.
- **Replay** — signature verified without independent sender/origin binding; chain-id checked AFTER a queue slot is consumed.
- **Serialization non-canonical** — `encode(decode(x)) ≠ x` on a signature/hash path → hash divergence (18.1 involution at impl level).
- **Resource charging order** — expensive op (JIT compile, contract load) before gas/validation.
- **Alt-EVM / EVM-compat engine (Cat 18.13 — scope: chain/appchain program ONLY, at parity with contracts)** — sweep 4 field-proven patterns: **(a)** precompile trusts `msg.value`/`msg.sender` without a CALL-vs-`DELEGATECALL` check → infinite-spend / sender-impersonation (Aurora `ExitToNear` $6M, Moonbeam $1.05M); **(b)** native-asset-as-ERC20 (`OVM_ETH`) not updated by `SELFDESTRUCT`/`CREATE`/balance opcodes in the forked interpreter → value duplicated from nothing (Optimism $2M); **(c)** u256→u128/native truncation applied at *execution* but not *validation* (`msg.value=1<<128` transfers 0 yet credits full) → mint without backing (Frontier $1M); **(d)** any re-implemented opcode / gas rule / state-commit / precompile diverges from canonical geth/revm → run T8 / T8-B differential vs the reference.
- **Cross-layer bridge** — events from reverted txs accepted; witness-format disagreement; queue poisoning.
- **Precision loss in finalization** — iterative multiply on attacker-influenced values → payout > pool.
- **ZK constraint** — remainder unconstrained below divisor; arithmetic-gadget residual witness freedom (cross-ref Cat 14 / Orchard).
- **Memory safety** — use-after-free via async boundary; iterator invalidation.
- **Concurrency** — split-lock inconsistency; lock-order inversion.
- **Platform-dependent** — signed-overflow UB eliminates checks; float non-determinism in consensus.

## Verifier add-ons (feed T4)
- Mark each factual claim `VERIFIED`/`REFUTED`/`UNVERIFIABLE`; recompute severity from VERIFIED only.
- `contested` outcome (guard exists but not provably sufficient) → park for second pass, don't kill.
