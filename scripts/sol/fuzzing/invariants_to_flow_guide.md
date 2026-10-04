# How to Translate Invariants Library → Trident Flow Code

Real Trident workflow (v0.12+) uses `#[flow]` methods in `test_fuzz.rs` with **inline assertions**. Invariants from `invariants_lib/*.md` are written as `assert!(...)` checks inside flow methods OR in dedicated check methods called from flows.

## Trident v0.12 anatomy (real)

```rust
use trident_fuzz::fuzzing::*;
mod fuzz_accounts;  mod types;
use fuzz_accounts::*;  use types::*;

#[derive(FuzzTestMethods)]
struct FuzzTest {
    trident: Trident,
    fuzz_accounts: AccountAddresses,
}

#[flow_executor]
impl FuzzTest {
    fn new() -> Self {
        Self {
            trident: Trident::default(),
            fuzz_accounts: AccountAddresses::default(),
        }
    }

    #[init]
    fn start(&mut self) {
        // One-time setup: airdrop, init accounts, deploy state
        let user = self.fuzz_accounts.user.insert(&mut self.trident, None);
        self.trident.airdrop(&user, 10 * LAMPORTS_PER_SOL);
        // ... setup more accounts, run init instructions
    }

    #[flow]  fn flow_stake(&mut self) { ... }
    #[flow]  fn flow_unstake(&mut self) { ... }
    #[flow]  fn flow_check_invariants(&mut self) {
        // Inline invariant assertions
    }

    #[end]
    fn end(&mut self) {
        // Per-iteration cleanup
    }
}

fn main() {
    FuzzTest::fuzz(1000, 100);  // (iterations, max_flows_per_iteration)
}
```

## Translating invariants from library

### Pattern 1: State value comparison

**Library** (e.g., `staking_lst.md` I1):
```
I1: Vault solvency
vault.balance >= state.escrowed_orca_amount
```

**Trident flow**:
```rust
#[flow]
fn check_solvency(&mut self) {
    let vault_balance = self.trident.get_account_lamports(&self.fuzz_accounts.vault.get());
    let state_data = self.trident.get_account_with_type::<State>(
        &self.fuzz_accounts.state_pda.get(),
        8,  // discriminator offset
    );
    if let Some(state) = state_data {
        assert!(
            vault_balance >= state.escrowed_orca_amount,
            "SOLVENCY VIOLATED: vault={} < escrowed={}",
            vault_balance, state.escrowed_orca_amount,
        );
    }
}
```

### Pattern 2: Round-trip invariant

**Library** (e.g., `amm_clmm.md` I5):
```
I5: No profit roundtrip
swap(A→B) + swap(B→A) ≤ initial
```

**Trident flow**:
```rust
#[flow]
fn check_roundtrip(&mut self) {
    let user = self.fuzz_accounts.user.get();
    let balance_before = self.get_user_token_a_balance(&user);

    // Swap A→B random amount
    let swap_amount = self.trident.random_from_range(1..1_000_000);
    let _ = self.trident.process_transaction(&[
        SwapInstruction::data(SwapInstructionData::new(swap_amount, true))
            .accounts(...)
            .instruction()
    ], Some("Swap A→B"));

    // Get B balance, swap B→A
    let b_balance = self.get_user_token_b_balance(&user);
    let _ = self.trident.process_transaction(&[
        SwapInstruction::data(SwapInstructionData::new(b_balance, false))
            .accounts(...)
            .instruction()
    ], Some("Swap B→A"));

    let balance_after = self.get_user_token_a_balance(&user);
    assert!(
        balance_after <= balance_before,
        "ROUNDTRIP PROFIT: started={} ended={}",
        balance_before, balance_after,
    );
}
```

### Pattern 3: Negative invariant (should fail)

**Library** (e.g., `amm_clmm.md` I11):
```
I11: Locked position is unmodifiable
LockConfig exists → decrease_liquidity errors
```

**Trident flow**:
```rust
#[flow]
fn try_decrease_locked(&mut self) {
    let position = self.fuzz_accounts.locked_position.get();
    let res = self.trident.process_transaction(&[
        DecreaseLiquidityInstruction::data(...)
            .accounts(...)
            .instruction()
    ], Some("Try decrease locked"));

    assert!(
        !res.is_success(),
        "LOCK BYPASS: decrease_liquidity succeeded on locked position!"
    );
}
```

### Pattern 4: Monotonic invariant

**Library** (e.g., `amm_clmm.md` I8):
```
I8: Fee accumulation monotonic
pool.fee_growth_global_a never decreases
```

Trident: store previous value in struct field, compare each flow:

```rust
struct FuzzTest {
    trident: Trident,
    fuzz_accounts: AccountAddresses,
    prev_fee_growth_a: u128,  // tracker
}

#[flow]
fn check_fee_monotonic(&mut self) {
    let pool = self.trident.get_account_with_type::<Whirlpool>(
        &self.fuzz_accounts.whirlpool.get(), 8
    );
    if let Some(pool) = pool {
        assert!(
            pool.fee_growth_global_a >= self.prev_fee_growth_a,
            "FEE GROWTH DECREASED: prev={} now={}",
            self.prev_fee_growth_a, pool.fee_growth_global_a,
        );
        self.prev_fee_growth_a = pool.fee_growth_global_a;
    }
}
```

### Pattern 5: Multi-account invariant

**Library** (e.g., `amm_clmm.md` I1):
```
I1: sum(positions.liquidity_active) == pool.liquidity
```

Trident: iterate over tracked position accounts in `fuzz_accounts`:

```rust
#[flow]
fn check_liquidity_conservation(&mut self) {
    let pool = self.trident.get_account_with_type::<Whirlpool>(...).unwrap();
    let mut sum = 0u128;
    for pos_addr in &self.fuzz_accounts.positions.all() {
        let pos = self.trident.get_account_with_type::<Position>(pos_addr, 8);
        if let Some(p) = pos {
            if p.tick_lower_index <= pool.tick_current_index
                && pool.tick_current_index < p.tick_upper_index
            {
                sum += p.liquidity;
            }
        }
    }
    assert_eq!(
        sum, pool.liquidity,
        "LIQUIDITY CONSERVATION: sum_positions={} pool={}",
        sum, pool.liquidity,
    );
}
```

## Flow execution semantics

Trident randomly selects `#[flow]` methods each iteration:
- 1000 iterations × ~100 flow calls = ~100,000 flow executions per fuzz run
- If ANY assertion fails in ANY flow → that seed is saved as crash → fuzz continues
- After run: `trident fuzz debug <test> <SEED>` to reproduce

## Common mistakes

1. **Forgetting to save tracker state** in struct — every method runs fresh, struct fields persist between flows
2. **Assert vs Result handling** — `process_transaction` returns `TransactionResult`, check `.is_success()` not panic
3. **Account type mismatch** — `get_account_with_type::<T>(addr, OFFSET)` — offset is discriminator size (8 for Anchor)
4. **Forgetting `forward_in_time`** — some bugs only appear after time progression (cooldowns, fee accrual)
5. **Random ranges too small** — `random_from_range(1..100)` may not hit edge cases. Use ranges including u64::MAX, 0, MIN/MAX bounds

## Performance tips

- Heavy invariant checks (loops over many accounts) — put in separate `#[flow]` method called less often
- For Adaptive Fee tests: use `forward_in_time` to test decay/filter periods
- For first-depositor inflation: `#[init]` should set up pool, flow_attack should run first-deposit scenario

## Reference: Trident docs

- Macros: https://ackee.xyz/trident/docs/latest/trident-api-macro/
- Examples: https://github.com/Ackee-Blockchain/trident/tree/master/examples
- FuzzAccounts pattern: https://ackee.xyz/trident/docs/latest/trident-api-macro/trident-types/fuzz-accounts/
