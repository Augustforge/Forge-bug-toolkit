# Active Targets — Protocols Shipping Researched Primitives

Auto-updated weekly via `_check_active_targets.py` (queries DeFiLlama new + GitHub trending). Manually augmented with specific repos / Immunefi programs.

## Last refresh

(Run `python3 scripts/web3/research/_check_active_targets.py` to refresh — populates section below.)

## ZK VMs

- **Risc0** — https://github.com/risc0/risc0 — Rust zkVM, used by Boundless, Bonsai
- **SP1 (Succinct)** — https://github.com/succinctlabs/sp1 — competing zkVM, focus on adoption
- **Jolt (a16z)** — https://github.com/a16z/jolt — RISC-V based, newer
- **Scroll** — https://github.com/scroll-tech/scroll — zkEVM L2
- **Linea** — Consensys zkEVM
- **Polygon zkEVM** — production zkEVM
- **ZKsync Era** — Boojum prover, production
- **Taiko** — based zkEVM

Immunefi programs: Scroll, ZKsync, Polygon (various)

## Restaking AVS

- **EigenLayer** — https://github.com/Layr-Labs/eigenlayer-contracts
- **EigenDA** — DA layer built on EigenLayer
- **AltLayer** — Restaked rollup framework
- **Symbiotic** — https://github.com/symbioticfi/core — alternative restaking
- **Karak** — multi-asset restaking
- **AVS catalog** (top 10 by TVL): EigenDA, AltLayer MACH, Brevis, Lagrange, etc.

Immunefi programs: EigenLayer ($1M cap), Symbiotic

## MPC threshold

- **FROST implementations**: ZF Frost, drand
- **GG24 / Lindell24** — newer protocols (limited production)
- **threshold BLS**: Chainlink VRF, Drand
- **DKG variants**: snowfork, drand DKG

Immunefi programs: Chainlink (VRF), ZF Frost (research bounty)

## DA layers

- **Celestia** — https://github.com/celestiaorg/celestia-node
- **EigenDA** — Layr-Labs/eigenda
- **Avail** — Polygon's DA layer

Immunefi: Celestia ($1M cap)

## Intent solvers

- **UniswapX** — Uniswap protocol periphery
- **CoWSwap** — CoW Protocol
- **Across** — across-protocol/contracts-v2
- **1inch Fusion** — 1inch

Immunefi: Uniswap, 1inch, CoW Protocol

## Post-quantum

- **Solana PQ pilot** — experimental, pre-production
- **NIST PQC migrations** — emerging across wallets, hardware HSMs
- **Reference**: liboqs (Open Quantum Safe)

Active targets thin — primitive has not reached widespread production yet.

## DAG consensus

- **Sui** — Mysticeti / Bullshark
- **Aptos** — BlockSTM execution + custom consensus
- **Monad** (post-launch) — DAG-influenced design

Immunefi: Sui ($500k cap), Aptos
