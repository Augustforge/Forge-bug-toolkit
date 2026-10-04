# Trident Fuzzing Infrastructure — Solana

Phase S2 (Invariant Break) — automated property-based fuzzing via [Trident v0.12+](https://github.com/Ackee-Blockchain/trident) by Ackee Blockchain.

## ⚠️ Important: Anchor-only

Trident integrates **directly into Anchor workspace** (`trident-tests/` subdirectory). It auto-generates fuzz templates from Anchor IDL.

**Limitation**: Trident works ONLY with Anchor-based Solana programs. For native Solana (Pinocchio, raw `solana_program`) — use `solana-program-test` manually.

| Target | Compatible? |
|---|---|
| Orca Whirlpools (Anchor wrapper) | ✓ Yes |
| Marinade, Jito (Anchor) | ✓ Yes |
| Kamino lending (Anchor) | ✓ Yes |
| Squads multisig (Anchor) | ✓ Yes |
| xORCA (pure Pinocchio native) | ✗ No — use solana-program-test |
| Whirlpools Pinocchio module | ✗ No — use solana-program-test |
| Wormhole (Solitaire framework) | ✗ No — manual |

## When to use

- Mature Anchor protocols (3+ audits, $100M+ TVL)
- Surface bugs exhausted by auditors
- Long-term watchlist (continuous fuzz on releases)

## When to skip

- Fresh deploys (<6mo) — manual + audit_diff faster
- Audit competitions (time pressure < 24h)
- Native Solana (use solana-program-test)
- EVM (use Foundry invariants / Echidna / Halmos)

## Real Workflow

### Step 1: Setup harness (1-3h per target)

```bash
# Wrapper around `trident init`. Requires anchor build to generate IDL first.
bash scripts/sol/fuzzing/setup_target.sh \
    sessions/$TARGET/source/$REPO \
    --program $PROGRAM_NAME \
    --test fuzz_0 \
    --class amm_clmm   # invariants_lib reference copied
```

This runs:
1. `anchor build` (if not skipped) — generates `target/idl/`
2. `trident init -p $PROGRAM -t fuzz_0` — creates `trident-tests/fuzz_0/` with:
   - `test_fuzz.rs` (main fuzz binary with `#[flow_executor]` impl)
   - `fuzz_accounts.rs` (account storage `AccountAddresses` struct)
   - `types.rs` (generated from Anchor IDL — instruction types ready to use)
3. Copies relevant `invariants_lib/<class>.md` to `trident-tests/fuzz_0/` as reference

### Step 2: Customize test_fuzz.rs (THIS is the work)

Read `INVARIANTS_<CLASS>.md` then translate to flow code. See [`invariants_to_flow_guide.md`](./invariants_to_flow_guide.md) for translation patterns.

Key edits in `test_fuzz.rs`:
- `#[init]` — setup initial pool state, accounts, deploy
- `#[flow]` per instruction (or category) — exercise that path
- `#[flow]` invariant-check methods — assertions

### Step 3: Run fuzz (4-24h background)

```bash
bash scripts/sol/fuzzing/run_fuzz.sh \
    sessions/$TARGET/source/$REPO/trident-tests/fuzz_0
```

OR with explicit workspace:

```bash
bash scripts/sol/fuzzing/run_fuzz.sh \
    --workspace sessions/$TARGET/source/$REPO \
    --test fuzz_0 \
    --with-exit-code
```

Trident's internal control (set in `test_fuzz.rs` line `FuzzTest::fuzz(N, M)`):
- N = iterations (default 1000)
- M = max flow calls per iteration (default 100)
- Total flow executions = N × M ≈ 100K

For long runs, increase iterations: `FuzzTest::fuzz(100_000, 200)`.

### Step 4: Analyze crashes

```bash
python3 scripts/sol/fuzzing/analyze_crashes.py \
    sessions/$TARGET/source/$REPO/trident-tests/fuzz_0
```

Crashes saved by Trident to:
- `trident-tests/fuzz_0/hfuzz_workspace/` (honggfuzz output)
- Look for `*.fuzz` files = seed inputs that triggered crash

### Step 5: Reproduce specific crash

```bash
cd sessions/$TARGET/source/$REPO
trident fuzz debug fuzz_0 <SEED>
```

This replays the exact tx sequence → confirm exploit → Phase S5 PoC.

## Directory structure

```
scripts/sol/fuzzing/
├── README.md                       ← this file
├── invariants_to_flow_guide.md     ← translation patterns
├── setup_target.sh                 ← wrapper around `trident init`
├── run_fuzz.sh                     ← wrapper around `trident fuzz run`
├── analyze_crashes.py              ← parse crash output, severity-categorize
├── smoke_test.sh                   ← infrastructure verification
│
└── invariants_lib/                 ← Standard invariants per protocol class (.md only)
    ├── amm_clmm.md      (20 invariants)
    ├── amm_v2.md         (8 invariants)
    ├── staking_lst.md   (16 invariants)
    ├── lending.md       (14 invariants)
    ├── governance.md    (10 invariants)
    └── cross_program.md (13 invariants)
```

**Note**: NO Rust template files. Trident auto-generates skeleton via `trident init`. Library content is in `.md` for translating into auto-generated `test_fuzz.rs`.

## Time / cost model

| Phase | Time | Reusable? |
|---|---|---|
| One-time install Trident in Docker | 5-6 min (cargo compile) | YES — already baked into `bbt:latest` |
| First target harness | 3-5h (customize test_fuzz.rs) | Partial |
| Subsequent targets (same class) | 1-3h | YES (invariants lib reuse) |
| Fuzz run | 4-24h (background) | Compute, not human time |
| Crash analysis | 1-2h per session | Yes (automated triage) |

## Trident reference

- Repo: https://github.com/Ackee-Blockchain/trident
- v0.12.0 (Nov 2025, Solana Foundation supported)
- Throughput: ~12K tx/s
- Docs: https://ackee.xyz/trident/docs

## Honest limitations

1. **Anchor-only** — significant subset of Solana protocols (~70-80%) use Anchor, but native programs untouched
2. **IDL-driven** — Trident uses Anchor IDL to generate instruction types. Programs with custom serialization may not auto-generate correctly
3. **Invariant quality bottleneck** — fuzzer finds violations of YOUR specified invariants. Missing invariant = missed bug
4. **CPU-intensive** — ~12K tx/s but real workspace needs many threads
5. **No state cloning from mainnet** — Trident runs fresh test_validator. For real-state bugs use `solana-test-validator --clone` + Phase S5 fork PoC

## See also

- [`invariants_to_flow_guide.md`](./invariants_to_flow_guide.md) — how to translate invariants → assertions
- [`../HIGH_VALUE_PATTERNS_SOL.md`](../HIGH_VALUE_PATTERNS_SOL.md) — patterns informing invariants
- [`../DEFI_PRIMITIVES_SOL.md`](../DEFI_PRIMITIVES_SOL.md) — math-specific bug classes
- [`../fork/`](../fork/) — Phase S5 mainnet-state fork PoC (different tool, complementary)
- `../../web3/continuous_fuzz.py` — EVM analog (Foundry + Echidna)
