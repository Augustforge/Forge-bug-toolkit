# Specialty 02 — Accounting Asymmetry

You hunt ONLY asymmetry between sibling functions/branches. Cat 3. Shared protocol: `_INDEX.md`.
Scanner: `hypothesis/asymmetry_scanner.py`, `detectors/asymmetric_modifier.py`.

## Hunting ground (one lens)
- Sibling guard asymmetry (`deposit` checks, `mint` doesn't; one wrapper guarded, the other not) — 3.1.
- Two-phase state-delta = 0 (phase-1 consumes the value phase-2 reads) — 3.2.
- Storage-write symmetry diff in paired ops (deposit↔withdraw write different sets).
- Branch asymmetry: native vs ERC20 path, only one validates; admin-variant lacking the user guard.
- One-sided slippage guard (3.7): input capped (`validateMaxIn`/`amountMax`) but NO output floor (`minOut`/`minLiquidity`/`minShares`) — guard bounds what you SPEND, not what you RECEIVE. Output derived from manipulable spot (`getSlot0`/`sqrtPriceX96`, no TWAP). Uniswap V4 `MINT_POSITION_FROM_DELTAS`.

## Read first
Grep paired names (`deposit/mint`, `withdraw/redeem`, `claimX/claimY`); diff the two bodies line-by-line.
Inversion on the LESS-guarded sibling: what slips through it that the guarded one blocks?
For every slippage/`validateMaxIn` check: does it floor the OUTPUT, or only cap the INPUT? Missing floor = 3.7.

## Pairs into
trust-gap lens (access×asymmetry / economics×asymmetry). Over-restrictive check that DoS's = bad-symmetry, log it.
