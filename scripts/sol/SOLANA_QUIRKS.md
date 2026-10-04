# Solana-Specific Quirks (vs EVM)

Architectural differences which create unique attack surfaces.

## Sealevel Parallel Execution

Solana executes non-conflicting txs **in parallel** (Sealevel runtime). Conflict resolution = writable account overlap.

**Attack surface**:
- If protocol assumes sequential ordering between Tx_A and Tx_B BUT they don't share a writable account → they execute in parallel
- Read-only race conditions are possible without explicit locks
- "First-to-finalize wins" doesn't work as expected

**Detection**: `compute_dos_analyzer.py` + manual review for shared state assumptions.

## Compute Budget (CU)

Each tx has a 1.4M CU default cap. Each instruction has a separate budget.

**Attack vectors**:
- **CU exhaustion DoS**: attacker forces program into an expensive code path
- **Priority fee bypass**: pay high priority but actual work cheap (waste competition)
- **Cross-slot MEV**: attacker rebuilds tx across multiple slots for optimal placement

## Rent and Lamports

Account holds lamports for rent-exemption (~0.002 SOL per 100 bytes). Below threshold → account closed by runtime.

**Quirks**:
- Account closed if lamports drop below rent-exempt threshold
- Closed account can be reopened by **anyone** in next instruction
- Stale data remains in account memory unless explicitly zero-filled

## Account Model

- Every "storage" lives in separate accounts (vs EVM single contract storage)
- Account size fixed at init, must `realloc` to change
- Account size limit: 10MB
- Programs are **stateless** — all state lives in accounts

**Attack surface**:
- Account substitution (fake account with same layout)
- Account realloc growth attack
- 10MB limit DoS (force account to max size)

## Discriminators

- Anchor: first 8 bytes of `sha256("global:<fn_name>")` per instruction
- Anchor accounts: first 8 bytes of `sha256("account:<StructName>")`
- Custom discriminators (Anchor 0.30+) allowed

**Attack surface**:
- Discriminator collision between programs
- Custom discriminator overlap (ambiguous parsing)
- Account discriminator stale after close+reinit

## Durable Nonces

Replaces recent_blockhash in txs — allows pre-signing txs indefinitely.

**Attack surface (Drift 2026)**:
- Combined with a multisig without timelock → admin takeover via held signatures
- No revocation mechanism (signatures stay valid)
- Used in offline signing flows, governance ops

## Token-2022 Extensions

New token program with extensions: transfer hooks, confidential transfers, interest-bearing, transfer fees, freeze, etc.

**Attack surface**:
- **Transfer hooks**: re-imports reentrancy via mid-transfer CPI
- **Confidential transfers**: ZK proof completeness (Fiat-Shamir hash inputs)
- **Extension composability**: hooks + confidential are incompatible

## CPI (Cross-Program Invocation)

- Solana programs call other programs via `invoke` / `invoke_signed`
- PDA authority via signer seeds

**Attack surface**:
- Authority not verified (caller can pretend PDA)
- Target program ID not verified (Loopscale 2025) — substitute malicious program with same interface
- Re-entrancy via callbacks (Token-2022 hooks)

## Validator-Level MEV

- Validator controls slot ordering during its leader window
- **Cross-slot sandwich**: 93% of all Solana sandwiches happen across different leader slots
- Jito bundle protection does not help against malicious validators
- 529K+ SOL extracted per year

## SVM Derivatives

- **Eclipse**: SVM on Ethereum settlement layer
- **Sonic SVM**: HyperGrid framework
- **MagicBlock**: ephemeral rollups (temporary SVM environments)
- **SOON**: decoupled SVM rollup

Each adds bridge/sequencer trust assumptions on top of Solana's model.

## See Also

- `HIGH_VALUE_PATTERNS_SOL.md` — 35 specific bug patterns
- `DEFI_PRIMITIVES_SOL.md` — math models on Solana
- `threat_intel.md` — historical exploits
