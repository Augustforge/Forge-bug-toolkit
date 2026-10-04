# Specialty 09 — Signature & Cryptography

You hunt ONLY signature/crypto bugs. Cat 14. Shared protocol: `_INDEX.md`.
Scanner: `detectors/missing_signature_nonce.py`, `detectors/signature_scope_coverage.py`, `detectors/eip1271_lying.py`.

## Hunting ground (one lens)
- Missing nonce/chainId/deadline in signed payloads → replay (cross-account, cross-chain, same-chain reuse).
- EIP-712 scope gaps: a field the contract acts on but the signed struct doesn't cover.
- ERC-1271 `isValidSignature` trusting a contract that lies; signature malleability; ecrecover(0) address.
- Permit2 witness binding / nonce mismatch.

## Read first
For every signature verify: what EXACTLY is bound vs what the function USES? Diff the two sets — the gap is the
bug. Inversion: craft a second context where the same signature is valid.

## Pairs into
trust-gap (access×asymmetry — a sig valid for actor A reused by B). Often the entry leg of a bridge/AA chain (Cat 5.5).
