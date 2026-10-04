# Harness-from-Invariant — T11 skeleton (invariant → property, per-target)

> **T11 (mythos Technique 11): the fuzzer = a GENERATOR of divergences, not a verifier.** It runs BEFORE
> the hypothesis, from an `I-NN` of the independent model (`system_model.md`), looking for a **call sequence**
> that can't be reached by reading. Invoked from `/deephunt` phase `J2`. The harness is built **per-target** —
> this is a skeleton, not a ready-made script. Trigger: EVM/Solana state machine **AND** an `I-NN` that can't be verified by reading.

## 0. Input and anti-tautology (do BEFORE coding)

1. Take an `I-NN` from `system_model.md` — priority `ABSENT` / `ENFORCED-PARTIAL` / `SUBSTITUTED`,
   multi-step / order-dependent / cross-contract (single-step ones are verified by reading, not fuzzing).
2. ⛔ **Anti-tautology (flounder):** encode the property from the **formula of the model's `I-NN`**, NOT from the observed
   behavior of the code. Test before running: "would this property fail if there were a bug, — or does it just repeat a line
   of the contract?". An invariant copied from the implementation → the fuzzer proves that the code does what it does.
3. The goal of the run — **not to confirm a hypothesis, but to FIND a sequence**. Found → a machine-origin `D-NN`
   → `system_model.md ## Divergences` + SELECT (then the usual DRIVE: T2→PoC→T4).

## 1. EVM — fizz / Echidna / Medusa (stateful)

Dispatcher and full engine: [`../fuzz_harness/fizz/SKILL.md`](../fuzz_harness/fizz/SKILL.md).
Property skeleton from `I-NN`:

```solidity
// I-NN: <formula from system_model.md, e.g. "Σ user shares == totalShares on all paths">
// class: state|economic   status: ABSENT|ENFORCED-PARTIAL   check: <what exactly it breaks>
contract Inv_<NN> is Test {
    // actors — permissionless calls that the fuzzer combines into a SEQUENCE
    function invariant_<NN>() public {
        // assert the I-NN formula — NOT a copy of a require from the contract, but a property of the model
        assertEq(vault.totalShares(), sumUserShares(), "I-<NN> broken: sequence found");
    }
}
```

### 🔴 Coverage-gate is MANDATORY (otherwise a "PASS" may be vacuous) — a lesson from a marketplace-contract campaign (I-05)

An invariant that passed on a campaign where **every** actor call reverted is falsely green: the property was
never checked on a non-trivial state. Two mandatory techniques:

1. **Mock the transfer primitive to a no-op** (`_transferAsset` empty) → the fuzzer reaches the accounting logic
   WITHOUT token fixtures; and a **black-box handler** counts successes FROM OUTSIDE (`try actor {...} catch {}`,
   incrementing only on success), without instrumenting the contract. Encode the sharpest vector as an explicit knob
   (e.g. `hAcceptDup` — the same signed object twice in one atomic call).
2. **Prove non-vacuity with a SEPARATE deterministic test, NOT `afterInvariant()`.**
   `afterInvariant()` reads the state AFTER the campaign is rolled back to the setUp snapshot → the coverage counters there
   are **zeroed** (giving a false `0`, as if fuzzing was empty). The right way: `test_HandlerPathSettles()` calls the
   handler path directly and `assertGt(totalSuccess, 0)`. Plus a deterministic guard test
   ("a second spend of the same object reverts"). Only then does "the invariant holds" = proof.

Working reference (Offchain-Marketplace uses/tradeId): `sessions/decentraland/repos/offchain-marketplace-contract/test/marketplace/T11UsesInvariant.t.sol`.
Run: Docker `bbt`, `forge` in `/root/.foundry/bin` (not in PATH) — `export PATH=$PATH:/root/.foundry/bin && forge test --match-contract <Inv>`.

Run (auto-generating tests from the model):
```bash
py -3 scripts/web3/hypothesis/invariant_generator.py \
  --invariants sessions/$TARGET/system_model.md \
  --output sessions/$TARGET/deep/invariant_tests/
# then fizz/Echidna/Medusa stateful on the generated output (see fizz/SKILL.md)
```

## 2. Solana — Trident (Anchor) / proptest (native)

Skeleton: property = the `I-NN` formula in Trident's `#[invariant]` hook; actors = permissionless instructions.
Native/Rust without Anchor → `proptest`/`quickcheck` over the state-transition function. Account for the CU cost of actors
(it affects the reachability of the sequence).

## 3. Multi-client / format — differential T8

Two implementations of the same format/consensus → `libafl`-differential (`scripts/` T8 harness): a divergence
in outputs = a consensus-fork candidate. The invariant here is **involution/equivalence of implementations**, not
a state formula.

## 4. Output

| Outcome | Action |
|---|---|
| sequence found | `D-NN` in `## Divergences` (call-seq + violated `I-NN` + fork log) → SELECT |
| holds for N hours | `I-NN` → `ENFORCED` (machine-checked, closed path) — not "empty"; widen the horizon (calls/actors) |
| harness can't be built cheaply | don't burn hours: mark `I-NN` for a full harness on the next visit, pivot to reading |

The harness is a cross-hunt asset: put a working skeleton for a primitive next to its entry in
[`../../../methodology/invariant_library.md`](../../../methodology/invariant_library.md) (`fingerprint:`).
