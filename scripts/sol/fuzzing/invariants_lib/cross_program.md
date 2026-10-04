# Cross-Program / Composability Invariants

Bugs that emerge from interaction between programs. Critical zone — auditors rarely cover cross-protocol composition.

## CPI invariants

### I1: CPI program ID validated
```
For each invoke/invoke_signed:
    target_program_id matches expected (hardcoded constant or stored authority)
```
Loopscale 2025 ($5.8M) — missed this for RateX market spoofing.

### I2: CPI account ownership/state validated before passing
Before passing account to external program, validate:
- owner matches expected
- discriminator matches if reading state
- type matches expected struct

### I3: CPI return value handled
```
invoke_signed result checked; if Err, propagate or handle
```

## Composability via Token-2022 hooks

### I4: Transfer hook reentrancy
During CPI to transfer hook:
- Program state should NOT be re-mutated
- If protocol takes lock during hook, hook shouldn't release it
- Test: assert state.lock == true throughout hook execution

### I5: Hook program ID validation
```
transfer_hook.program_id matches expected (via TokenBadge or hardcoded)
```

## Cross-protocol value invariants

### I6: Asset substitution resistance
If pool/vault accepts ANY token of mint M:
```
all token accounts of mint M should be substitutable without breaking invariants
```
e.g., user provides own ATA of mint M = valid. Protocol shouldn't trust external state from such ATA.

### I7: Oracle dependency safety
If protocol uses external oracle (Pyth, Switchboard, Lazer):
- staleness check
- confidence interval check
- authority pin (oracle_account.update_authority)
- price sanity bounds

### I8: External pool/AMM dependency
If protocol consults external AMM for pricing:
- single-block manipulation resistance (TWAP or read-only reentrancy)
- not vulnerable to flash-loan price manipulation

## Multi-program coordination

### I9: Atomicity preserved across CPI chain
A→B→C call sequence: if C fails, A should rollback. Verify no partial state.

### I10: No reentrancy via CPI chain
A→B can't call back into A.

## SVM-derivatives specific (Eclipse, Sonic, MagicBlock, SOON)

### I11: Bridge trust assumption
If protocol uses bridge: assume bridge can be compromised → impact bounded?

### I12: Ephemeral state ↔ persistent state consistency
For ephemeral chains: state synced to base layer must match between snapshots.

### I13: Sequencer fault tolerance
For optimistic L2s: protocol should function even if sequencer pauses temporarily.

## Strategy hints

```rust
strategies! {
    DirectInvocation(instruction),
    InvocationViaCPI(target_program, instruction),
    InvocationViaCPIChain(programs[3..5]),  // multi-hop
    ConcurrentInvocations(instructions[2..]),  // same slot
    TokenTransferWithHook(hook_program, malicious_state_mutation),
}
```

## Critical real-world examples to fuzz

1. **CPI substitution**: Pass wrong program_id where target program is expected → does target verify?
2. **Hook reentrancy**: Call protocol op that triggers transfer_hook → hook re-enters protocol
3. **Stale state via CPI**: A calls B, B mutates account X, A reads X → A using stale data
