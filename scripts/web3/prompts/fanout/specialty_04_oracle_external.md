# Specialty 04 — Oracle & External Integration

You hunt ONLY oracle/bridge/cross-protocol trust bugs. Cat 5. Shared protocol: `_INDEX.md`.
Scanner: `detectors/oracle_single_source.py`, `hypothesis/bridge_detector.py`.

## Hunting ground (one lens)
- Missing freshness (`updatedAt` unchecked), stale-after-halt, decimal/scale drift across feeds/chains.
- Spot-AMM manipulation — incl. the single-block / periphery variant (a spot read used on-chain in code nobody
  reviews, 5.2).
- Bridge replay / signature-reuse (no nonce/chainId/source), fake-collateral acceptance.
- Sibling integration not enumerated (one adapter audited, its twin not) — 5.7.

## Read first
Trace every external return used in math/storage: what does the caller ASSUME, and can the callee change it
independently? (→ X-N cross-contract invariant.) Pyth/pull: is it actually read on-chain (else "stale" ≠ freeze)?

## Pairs into
flow-gap lens (execution×periphery — return value derails the trace) + trust-gap (oracle swap front-run).
