# DA (Data Availability) Layers

**Status**: not-started
**Priority**: high
**Why hunter cares**: Celestia/EigenDA/Avail underpin many L2s. **Data unavailability attacks** could brick chains. Each DA layer = $1M+ Immunefi cap typically.

## Core concept

DA layer = "store this blob, prove anyone can retrieve it". Rollups post data to DA layer instead of L1. If data lost → state un-reconstructable → rollup bricked.

Three approaches:
1. **Erasure-coded + sampling** (Celestia, Avail) — math-based availability guarantee
2. **Restaking-based** (EigenDA) — economic security from Eigen operators
3. **Optimistic with fraud proofs** (Avail with fraud proofs) — challenge mechanism

## Top bug classes

### 1. Sampling soundness
Celestia/Avail use Data Availability Sampling (DAS): light clients randomly query chunks.
Bug if:
- Adversary can withhold data but pass sampling
- Sample size insufficient for actual security (parameter mismatch)
- Erasure code reconstruction breaks under adversarial chunks
- KZG commitment verification gaps

### 2. Restaking economics (EigenDA)
EigenDA uses EigenLayer operators. Bugs from `restaking_avs.md` apply +:
- Operator can withhold blob but not get slashed
- Slashing evidence formation
- Withdrawal queue manipulation

### 3. Blob commitment bugs
- Commitment doesn't bind blob uniquely (commitment collision)
- KZG / FRI verification gaps in verifier contract
- Blob version not validated (replay across versions)

### 4. Rollup ↔ DA integration
- Rollup posts blob, doesn't verify DA receipt
- DA layer reorgs but rollup doesn't notice
- DA layer down → rollup falls back to L1?

### 5. Fraud proofs (Avail)
- Fraud proof window too short (legitimate disputes missed)
- Fraud proof construction wrong
- Bridge updates state before fraud window closes

### 6. Light client soundness
- Light client trusts fork choice incorrectly
- Header chain verification gaps
- Validator set update missing

## Implementations to read

### Celestia
- Repo: https://github.com/celestiaorg/celestia-node
- Key modules: `share/`, `das/` (sampling), `header/`
- Architecture: Tendermint consensus + erasure coding (Reed-Solomon)

### EigenDA
- Repo: https://github.com/Layr-Labs/eigenda
- Architecture: KZG commitments + EigenLayer operators
- Heavy crypto: KZG batch verification

### Avail
- Repo: https://github.com/availproject/avail
- Architecture: Polkadot SDK + DAS + KZG

## Notable past bugs

- **Celestia early audits** — multiple sampling-soundness fixes
- **EigenDA disclosures** — operator coordination bugs
- **Polygon DA** — historical issues with blob commitments

## Hunting workflow once we reach `can-hunt`

1. Identify DA layer used (Celestia / EigenDA / Avail / proprietary)
2. Check sampling parameters:
   - Number of samples per blob (must match security target)
   - Sample selection unbiased?
3. Verify rollup integration:
   - Does rollup verify DA receipt before finalizing state?
   - DA reorg → rollup reaction?
4. Operator misbehavior:
   - EigenDA — slashing for blob unavailability working?
   - Celestia — validator slashing for sampling fraud?
5. KZG verifier contract:
   - Pairing equation correctly checked?
   - Batched verification optimization safe?

## Active programs

- **Celestia Immunefi** — $1M cap
- **EigenDA** — part of EigenLayer Immunefi
- **Avail** — Polkadot side, separate program

## To-author once can-hunt status is reached

- `scripts/web3/checklists/specialized/da_layer.md`
- `scripts/web3/threat_models/da_sampling_soundness.yaml`
- `scripts/web3/threat_models/da_kzg_verifier.yaml`
- `scripts/web3/threat_models/da_rollup_integration.yaml`

## Reading list

1. **Celestia whitepaper**
2. **"Fraud and Data Availability Proofs"** — Mustafa Al-Bassam paper
3. **EigenDA spec doc**
4. **KZG commitments tutorial** — Dankrad Feist series
5. **Avail architecture docs**
