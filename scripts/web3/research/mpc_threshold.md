# MPC Threshold (beyond GG18/20)

**Status**: familiar (post-Thorchain study)
**Priority**: high
**Why hunter cares**: Thorchain TSSHOCK proved GG18/20 class is alive. **Newer protocols** (FROST, GG24, threshold BLS) hardly audited — same insider class, different math.

## Why "beyond" GG18/20

GG18/20 already studied via the Thorchain case (`threat_intel.md` §7, `threat_models/tss_validator_extraction.yaml`). This document covers **newer / less common** threshold schemes the hunter has not covered yet.

## Schemes catalog

### FROST (Schnorr-based threshold)
- Spec: RFC 9591
- Different math: Schnorr signatures instead of ECDSA
- Two flavors: FROST (interactive) and FROST-secp256k1 (for Bitcoin)
- Active users: drand, ZF Frost (Zcash Foundation), some Bitcoin BIP-340 protocols

**Attack surface**:
- Nonce generation: must be deterministic (RFC says so) — non-deterministic implementations vulnerable
- Coefficient commitments — verification gaps?
- Aggregator role — single point of failure?
- Round 1 vs Round 2 timing — race conditions

### GG24 / Lindell24
- Newer protocols from the Lindell research line
- Improvements over GG20 (fewer rounds, stronger security proofs)
- **Production status**: emerging — multiple papers, few deployments
- Hunter alpha: study spec, find production implementations early

### Threshold BLS
- Used in: Chainlink VRF, Drand randomness beacon, projects using BLS signature aggregation
- Different math: pairing-based crypto
- Bug classes:
  - Signature malleability
  - Subgroup confusion attacks
  - DKG round bugs (similar to GG20)
- Easier static analysis — fewer rounds, less state

### DKG (Distributed Key Generation) variants
- Stand-alone DKG protocols are used for setup phases
- Snowfork DKG, drand DKG
- Bug classes:
  - DKG abort enables key biasing
  - Complaint protocol gaps (malicious dealer accusation)
  - Reshare protocols

## Universal attack lens (transferable from GG20 study)

1. **Insider participation** — adversarial bonded actor leaking material
2. **ZK proof completeness** — every proof, every round, every iteration
3. **Modulus / parameter validation** — biprime, prime order subgroup, etc.
4. **Resharing soundness** — old shares must actually be invalidated
5. **Abort attacks** — malicious participant can force restart, replay round inputs

## Notable implementations to read

- **ZF Frost** — https://github.com/ZcashFoundation/frost (Rust, well-audited reference)
- **drand** — https://github.com/drand/drand (Go, threshold BLS production)
- **chia-network/bls-signatures** — production threshold BLS
- **frost-secp256k1** — Bitcoin-flavored FROST
- **schnorr-fun** — Rust FROST implementation

## Notable past bugs / disclosures

- **Verichains TSSHOCK** — covered (see threat_intel §7)
- **Fireblocks BitForge (CVE-2023-33241)** — Paillier modulus class
- **dfinity threshold ECDSA** — multiple disclosed fixes
- **chia BLS** — historical fixes during early 2022

## Hunting workflow once we reach `can-hunt`

1. Identify scheme in use:
   - GG18/20 → existing `tss_validator_extraction.yaml`
   - FROST → check nonce determinism, coefficient verification
   - threshold BLS → subgroup checks, pairing validation
   - Custom DKG → complaint protocol, abort handling
2. Apply universal lens (5 items above)
3. For each ZK proof / commitment — check ALL paths (keygen + signing + resharing + recovery)
4. Insider model: one malicious participant — can they extract / forge?

## Active programs

- **Chainlink** — Immunefi $2M+ cap (covers VRF, threshold BLS)
- **Drand** — research bounty
- **ZF Frost** — Zcash Foundation grants for security research
- **dfinity** — ICP bug bounty

## To-author once can-hunt status is reached

- `scripts/web3/checklists/specialized/frost.md`
- `scripts/web3/checklists/specialized/threshold_bls.md`
- `scripts/web3/threat_models/frost_nonce_compromise.yaml`
- `scripts/web3/threat_models/threshold_bls_subgroup.yaml`
- `scripts/web3/threat_models/dkg_abort_attack.yaml`

## Cross-link

- Existing `tss_validator_extraction.yaml` (covers GG18/20)
- `prompts/validator_extracts.md` — extends with FROST/BLS in future revision
- `checklists/specialized/tss_mpc.md` — currently GG-focused, expand
