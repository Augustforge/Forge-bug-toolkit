# Consensus / L1 Fault-Injection Checklist (grey-box runtime lens)

Source: CertiK "Grey-Box Chain Audit" ([[reference_certik_blog]]). The article's thesis: static
code review tells you what a chain is *designed* to do; it does NOT tell you how it behaves **under
live load, real infra dependencies, and stress**. Whole bug classes (chain halts, finality stalls,
bridge failures, oracle outages, post-upgrade rollbacks) only surface at runtime. This is the
companion *runtime* lens to Cat 18 (Consensus & Cross-Client Divergence) and the T8 differential
harness — use it on any L1 / multi-node / validator-binary target in `live_targets_consensus.md`.

We don't sell a multi-node testbed like CertiK; our use is (a) a **coverage checklist** so a consensus
hunt doesn't stop at static review, and (b) a guide for **local repro** (devnet / multi-node docker /
fork) when a static lead points at a runtime failure mode.

## Measurement frame (apply per scenario — pre / fault / post)

For every injected fault, record a structured window:
- **Pre:** baseline safety, liveness, finality lag, resource use (CPU/mem/disk/peers).
- **Fault:** inject the specific fault under realistic tx load.
- **Post:** does the chain keep **safety** (no conflicting finalized blocks)? **liveness** (still produces
  blocks)? **finality** (still finalizes)? **failover** (peers/validators recover)? **recovery time**?
  **resource stability** (no unbounded growth)?

A finding = any fault where safety breaks, OR liveness/finality does not recover without manual
intervention, OR resources grow unbounded. Map severity: permanent halt / safety break = Critical;
recoverable stall / degraded liveness = High/Medium.

## Eight fault-injection categories (coverage checklist)

- [ ] **Consensus & finality integrity** — equivocating/Byzantine proposer, conflicting votes, vote
      flooding, fork-choice edge inputs. Probe: can a minority force a finality stall or two finalized
      tips? → Cat 18.4 (proposer equivocation), 18.5/18.6 (quorum/punishment).
- [ ] **Validator & P2P behavior** — slow/silent/partitioned validators, gossip flooding, malformed
      P2P frames, eclipse. Probe: does one validator's misbehavior degrade the set beyond its weight?
      → Cat 18.1/18.2 (decoder divergence), 18.6 (punishment without quorum-survival guard).
- [ ] **Infrastructure & topology resilience** — network partition, asymmetric latency, node restart
      mid-round, clock skew. Probe: split-brain on heal? does recovery re-org finalized state?
- [ ] **RPC & oracle dependencies** — oracle outage/stale feed, RPC overload, dependency timeout.
      Probe: does a missing external read halt block production or freeze a price-gated path? → Cat
      5.1/5.4 (staleness), 22.4 (updater EV).
- [ ] **Bridge safety & upgrade logic** — message-relay under load, validator-set rotation during
      flight, upgrade/migration mid-traffic. Probe: in-flight messages dropped/double-processed across
      an upgrade? → Cat 5 (bridge), 10 (init/migration), `cross_chain_source_destination_binding.yaml`.
- [ ] **Resource exhaustion & recovery** — mempool flood, large-payload tx (attacker-inflatable size
      vs transport limit), state-bloat, OOM/disk-full, then recovery. Probe: cheap DoS to halt? recover
      after pressure? → Cat 13 (DoS), 18.5 (cross-layer size-limit → liveness; CometBFT `max_body_bytes`).
- [ ] **Cross-node determinism** — same input, divergent state across client impls / configs / arch.
      Probe: any non-determinism (map ordering, float, locale, uninit mem) → consensus fork. → Cat 18.1/
      18.2; run the **T8 differential/involution harness** (`scripts/web3/fuzz_harness/`).
- [ ] **Cryptographic primitives** — malleable sigs, edge-case curve points, hash-collision-shaped
      inputs, nonce reuse under concurrency. Probe: does a crafted-but-valid-looking input pass verify
      and diverge nodes? → Cat 14, 18.2.

## Where this beats static review (the grey-box gap)

The bug is in the **interaction of the binary + config + load + topology**, not in any single function:
a handler that is correct in isolation halts the chain when fed an attacker-inflated payload at quorum
scale (Axelar 18.5×18.6), or two clients that each "look right" diverge on one non-canonical byte
(18.1/18.2). Static review per-file structurally cannot see these — they need the runtime window above.

> Permanent-harness note: CertiK's differentiator is a *retained* testbed rerun on every release/patch/
> config change. Our equivalent = the `live_targets_consensus.md` queue + T8 harness, re-run after every
> client release (mirror of [[feedback_model_release_reaudit_window]] for consensus binaries).
