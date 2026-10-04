# Post-Quantum Cryptography

**Status**: not-started
**Priority**: high (long-term)
**Why hunter cares**: protocols starting PQ migrations (Solana pilot, Algorand). **Migration bugs are juicy** — hybrid schemes have new failure modes, no industry-wide tooling yet.

## NIST-standardized algorithms (2024)

| Scheme | Type | Use case |
|---|---|---|
| **ML-KEM** (was Kyber) | Lattice-based KEM | Key encapsulation (replaces ECDH) |
| **ML-DSA** (was Dilithium) | Lattice-based signature | Digital signatures (replaces ECDSA/EdDSA) |
| **SLH-DSA** (was SPHINCS+) | Hash-based signature | Backup signature (large size, slow) |
| **FN-DSA** (was Falcon) | Lattice-based signature | Compact signatures (still standardizing) |

## Top bug classes

### 1. Hybrid scheme failures
Most production migrations use **hybrid** (classical + PQ in parallel). Bugs:
- Hybrid output combines two ciphers — improperly chained = either alone breaks all
- Failure handling: one cipher fails, fallback unclear
- Key derivation: weak combination function

### 2. Implementation side-channels
PQ primitives still vulnerable to:
- Timing attacks on lattice operations
- Cache attacks during decapsulation failure
- Power analysis on hardware implementations

### 3. Signature malleability in lattice
- Different valid signatures for same message
- Rejection sampling bugs
- Nonce reuse in Dilithium

### 4. Key generation entropy
- PQ keys much larger — bad RNG harder to catch
- Hardware RNG fallback path bugs

### 5. Migration / wrapping bugs
- Existing protocol expects 32-byte secret key → ML-KEM produces 1568+ bytes
- Wallet UI shows ECDSA address — but PQ wallet generates different address from same seed
- Backup format incompatibility

## Migration patterns (where bugs live)

**Hybrid signing**:
```
sig_hybrid = sig_classical || sig_pq
verify(sig_hybrid) = verify(sig_classical) && verify(sig_pq)
```
Bug if `||` truncates, or if `&&` short-circuits.

**Hybrid KEM**:
```
shared = KDF(shared_classical || shared_pq)
```
Bug if either component is predictable / null.

**Algorithm negotiation**:
- Protocols may negotiate ECDSA vs ML-DSA at handshake
- Downgrade attack: force ECDSA via MITM

## Notable past bugs / known issues

- **Kyber implementations** — various reference implementation fixes 2020-2023
- **Dilithium** — multiple side-channel disclosures
- **Open Quantum Safe (liboqs)** — public CVE history
- **CECPQ2 (Google Chrome)** — initial deployment bug fixes

## Active targets / migrations

- **Solana PQ pilot** — experimental, pre-production
- **Algorand FALCON** — production limited
- **Various wallets** evaluating ML-DSA integration
- **HSM vendors** — Thales, AWS CloudHSM rolling out PQ
- **TLS 1.3 hybrid** — Google Chrome, Cloudflare deployments

Bounty programs thin here — primitive has not reached widespread production yet.

## Implementations to read

- **liboqs** — https://github.com/open-quantum-safe/liboqs (most comprehensive)
- **pq-crystals/kyber** — reference ML-KEM
- **pq-crystals/dilithium** — reference ML-DSA
- **circle/circl** — Cloudflare's PQ library (Go)
- **aws-lc** — AWS PQ implementation

## Reading list

1. **NIST PQC project** — https://csrc.nist.gov/projects/post-quantum-cryptography
2. **"A Decade of Lattice Cryptography"** — Peikert
3. **Cloudflare PQ blog series**
4. **CRYSTALS-Kyber / Dilithium papers**
5. **"Module-Lattice-Based Key-Encapsulation Mechanism Standard"** (NIST FIPS 203)

## Hunting workflow once we reach `can-hunt`

1. Identify hybrid scheme (target uses both classical + PQ)
2. Check combining function:
   - KDF used for hybrid KEM?
   - Concat order for signatures?
3. Check failure paths:
   - One cipher fails — does verify still return ok?
4. Check negotiation:
   - Downgrade attack possible?
5. Check key format compatibility:
   - PQ key fits in existing serialization? Truncated?

## To-author once can-hunt status is reached

- `scripts/web3/checklists/specialized/post_quantum.md`
- `scripts/web3/threat_models/hybrid_scheme_chain.yaml`
- `scripts/web3/threat_models/pq_downgrade_attack.yaml`

## Realistic timeline

Bounties for PQ-class bugs are still rare. This primitive is an **18-24 month investment** before payouts materialize. Track now, exploit when production migrations hit.
