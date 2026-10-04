# ZK Virtual Machines

**Status**: not-started
**Priority**: very-high
**Why hunter cares**: soundness errors can drain $100M+ from any rollup. Almost no static analysis tooling exists. The audit ecosystem is still immature — a large window of advantage.

## Two distinct flavors (must understand the difference)

### zkEVM
Goal: EVM-compatible L2 with ZK proofs. Prover proves correct EVM execution.

Examples: Polygon zkEVM, Linea (Consensys), Scroll, ZKsync Era (Boojum), Taiko.

Attack surface: circuit constraints encoding EVM semantics. Each opcode = circuit gadget. Bugs:
- Opcode underconstraint (e.g., SHA3 circuit doesn't fully constrain output)
- Stack/memory model bugs in circuit
- Precompile differences between circuit and EVM spec
- Gas accounting drift between circuit and EVM

### zkVM (general-purpose)
Goal: prove arbitrary computation. Not EVM-tied — typically RISC-V or custom ISA.

Examples: Risc0 (RISC-V), SP1 (Succinct, RISC-V), Jolt (a16z, RISC-V), Cairo (StarkNet's, custom).

Attack surface: ISA semantics encoded in circuits + std lib + I/O syscalls. Bugs:
- ISA opcode underconstraint
- Syscall handler bugs (precompile equivalents)
- Memory model issues (page table, MMU)
- Witness manipulation possibilities
- Recursion bugs if used

## Top bug classes (universal across both)

### 1. Underconstrained circuits
Circuit verifies "X relates to Y" but doesn't enforce uniqueness or full constraint. Witness can be valid for malicious-X.
- Tooling: Picus (formal verification), Halo2 lint
- Detection: read each gate definition, ask "is every variable fully constrained?"

### 2. Soundness gaps
Prover can construct valid proof for false statement. Often:
- Field element overflow/underflow
- Trusted setup violations
- Custom gates with edge cases
- Recursion soundness

### 3. Witness manipulation
Hint/non-deterministic values insufficiently constrained. Prover picks malicious values.
- Common in: SHA hint gadgets, range checks with holes, MSM optimizations

### 4. Precompile / syscall divergence
zkVM precompile or zkEVM precompile disagrees with reference implementation.
- Test: differential fuzzing zkVM vs reference

### 5. Verifier contract bugs (on-chain)
Solidity verifier contract:
- Public inputs encoding wrong
- Verifying key trust assumption violated
- Batch verifier optimization bug

### 6. Recursive proof composition
SNARK-of-SNARK / folding scheme bugs:
- Accumulator initialization
- Folding scheme soundness (e.g., Nova, ProtoStar)
- Cycle-of-curves implementation

## Notable past bugs (study)

- **zkSync 2022** — issue in proof verifier
- **Aztec circuit** — historical SHA bugs
- **StarkNet Cairo** — several soundness fixes
- **Polygon zkEVM** — multiple disclosed fixes during 2023 audit
- **Risc0** — ongoing public disclosures via Spearbit, ZellicAudits
- **Various RISC-V zkVM** — divergence-from-RISC-V-spec catches

## Attack vectors specific to zkVM

- **Syscall halt bypass**: zkVM may accept proof where syscall returns "halt" but program continues
- **PC manipulation**: program counter not fully constrained
- **Register state divergence**: register file state is not verified at every step
- **I/O commitment**: input/output reading from "untrusted host" — commitment must be verified
- **Cycle accounting**: max cycle counter not enforced → infinite proof generation DoS

## Current implementations to read

### Risc0
- Repo: https://github.com/risc0/risc0
- Architecture: https://dev.risczero.com/api/zkvm/
- Key files: `risc0/zkvm/src/host/server/prove/`, `circuit/rv32im/`
- Read: PoC generator, witness construction, syscall handlers

### SP1
- Repo: https://github.com/succinctlabs/sp1
- Architecture: https://docs.succinct.xyz/docs/sp1/introduction
- Recent audits: ZellicAudits, Spearbit
- Compare to Risc0 — different design choices, look for divergence patterns

### Scroll zkEVM
- Repo: https://github.com/scroll-tech/zkevm-circuits
- Each opcode = subdirectory with circuit gadget
- Read: SHA, MEMORY, CALLDATALOAD — historically buggy areas

### Polygon zkEVM
- Repo: https://github.com/0xPolygonHermez/zkevm-rom
- Architecture: micro-architecture in zkASM
- Read: main ROM, syscall dispatch

## Tooling

- **Picus** — formal verification for Halo2 circuits
- **circomspect** — Circom linter
- **HaloByte** — Halo2 circuit analyzer
- **Most hunters use manual reading** — tooling immature

## Reading list

1. **"A Tour of zk-SNARKs"** — Vitalik's intro (start here)
2. **PLONK paper** (Gabizon et al.) — fundamental
3. **Halo2 book** — https://zcash.github.io/halo2/
4. **Risc0 architecture doc**
5. **"Underconstrained Bugs in zkSnarks"** — Code4rena research
6. **Reckonless** newsletter — ongoing exploit posts

## Hunting workflow once we reach `can-hunt`

1. Identify zkVM/zkEVM in use (look for "circuit", "constraint_system", "proof_verifier")
2. Apply specific lens:
   - Opcode handlers — completeness audit (every opcode mapped 1:1 to spec?)
   - Public inputs — encoded same on-chain as off-chain?
   - Precompiles — diff against reference implementation
   - Recursion — folding scheme correctly initialized?
3. For each surface — write Foundry test where attacker submits malicious proof
4. Compare to past disclosed fixes (zkSync, StarkNet) — same pattern?

## To-author once can-hunt status is reached

- `scripts/web3/checklists/specialized/zk_vm.md`
- `scripts/web3/threat_models/zk_circuit_underconstraint.yaml`
- `scripts/web3/threat_models/zk_precompile_divergence.yaml`
- Possibly `scripts/web3/specialized/zk_vm_hunter.py` — automated underconstrained-witness scanner
