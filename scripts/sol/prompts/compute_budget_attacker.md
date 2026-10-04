# Prompt: Compute Budget Attacker (Solana)

You're trying to exhaust victim's compute budget (CU) or cause DoS.

## Attack surfaces

1. **Force expensive code path**: which inputs trigger most-expensive branches?
2. **Unbounded loops**: any `for x in vec.iter()` without `.take(MAX)`?
3. **Heavy ops in loops**: invoke / find_program_address / hash inside loop?
4. **Large allocations**: vec![0; N] with attacker-controlled N?
5. **Realloc growth**: account grows on each call?
6. **CU exhaustion to skip work**: request max CU, do nothing real → block priority lane?

## Per-instruction analysis

For each `pub fn`:
- Worst-case CU consumption (you control inputs)
- Does worst-case fit in 1.4M CU default cap?
- Can you DoS specific operations by forcing victim to retry?

## Cross-tx state DoS

- Can you grow an account beyond 10MB?
- Can you fill a vault's order book / merkle tree?
- Can you create transactions that compete for the same writable account?

---

## Program source:
