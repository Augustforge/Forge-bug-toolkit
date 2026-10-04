# Composability Prover — Lightweight Composability-Aware Fuzzing

## Why it is needed

Protocol A integrates dep B (Aave, Uniswap, LayerZero, Pyth). The assumptions A makes about B are **out of scope for A's audit**. When B is in an edge state (paused, drained, returns an extreme oracle value, sequencer down) — A's invariants may break.

A top bug-bounty class of 2024-2026: composability failures.

## Approach

**NOT a full formal proof** — practical composability-aware fuzzing with symbolic edge-state generation. 80% of the usefulness of formal methods for 5% of the effort.

## Architecture

```
target (Solidity repo + invariants)
   │
   ▼
dep_extractor.py
   │  finds: imports, external calls, addr constants
   │  output: deps.json [{name, surface_in_target[]}]
   ▼
edge_state_generator.py
   │  for each dep — emit mock contracts with edge states
   │  output: foundry_compose/Mocks/MockX.sol for each dep
   ▼
prover.py
   │  generates .t.sol test files combining:
   │    - target's existing invariants
   │    - mock dep in edge state
   │    - normal protocol flow
   │  optionally runs forge test
   │  output: composability_breaks.json
   ▼
deephunt.md J3 → composability prover row
deephunt.md J8 → composability_breaks feeds Generalization
```

## Edge states inventory

For each dep type:

| Dep type | Edge states tested |
|---|---|
| Lending (Aave/Compound) | paused, liquidity 0, utilization 100%, oracle stale |
| AMM (UniV3/Curve) | paused, pool drained, fee MAX, sqrtPriceX96 extreme |
| Oracle (Chainlink/Pyth) | returns 0, returns MAX_INT, returns stale timestamp |
| Bridge (LayerZero/Wormhole) | DVN paused, message reverted, race-to-deliver |
| Restaking (EigenLayer) | operator slashed mid-call, withdrawal queue full |
| Yield (Pendle/Aura) | yield negative, rate extreme, principal decay |

## Practical limit (honestly)

- **Not Z3/SMT** — fuzzing with symbolic edge values, not a formal proof
- **Does not cover novel deps** without runtime info — an Etherscan ABI or local repo is needed
- **Foundry required** — without `forge test` this generates scaffolds only
- **Manual review of breaks** — the tool says "invariant broken under edge X", a human verifies it's a real exploitation path

## Reuse

- `scripts/web3/longtail/composability_matrix.py` — existing static analysis. `prover.py` calls it for the dep list, doesn't duplicate it.
- `scripts/web3/hypothesis/invariant_generator.py` — generates Foundry stubs. prover.py extends it with a composability flavor.
- `scripts/web3/foundry_corpus/` — templates for test scaffolding.
- `scripts/web3/advanced/exploit_chain_builder.py` — `composability_breaks.json` can feed the chain builder for multi-step Crit construction.

## Integration in /deephunt

- **J3 specialized table** — for **any** protocol with external deps add a required row "Composability prover"
- **J8 Generalization** — composability_breaks points to which protocols (other A's using the same B) the edge state hits
- **Phase gate**: J3 → J4 only if the prover ran on at least 1 dep edge state

## Usage

```bash
# Step 1: extract deps
python3 scripts/web3/composability/dep_extractor.py \
    --repo /path/to/target --output sessions/$TARGET/composability/

# Step 2: generate mocks
python3 scripts/web3/composability/edge_state_generator.py \
    --deps sessions/$TARGET/composability/deps.json \
    --output sessions/$TARGET/composability/Mocks/

# Step 3: prove (generates test files; runs forge if available)
python3 scripts/web3/composability/prover.py \
    --target /path/to/target \
    --deps sessions/$TARGET/composability/deps.json \
    --invariants sessions/$TARGET/deep/invariants.md \
    --output sessions/$TARGET/composability/
```

## Anti-pattern

**Don't** treat broken invariants as automatic findings. Many edge states are unreachable in practice (e.g., Aave permanently paused is an operational concern, not a bug). Always trace from "edge state achievable" → "invariant broken" → "value extractable".

**Don't** generate tests for 50 deps. Focus on the top-3 deps by usage frequency or by criticality. Coverage vs depth — prefer depth.
