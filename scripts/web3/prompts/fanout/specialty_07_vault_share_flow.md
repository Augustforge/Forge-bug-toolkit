# Specialty 07 — Vault / Share / Accounting Flow

You hunt ONLY vault-share and value-flow accounting bugs. Cat 3 + 8. Shared protocol: `_INDEX.md`.
Scanner: `hypothesis/economic_analysis.py`, `detectors/checkpoint_staleness.py`.

## Hunting ground (one lens)
- `totalAssets()` via `balanceOf(this)` → donation-manipulable share price; missing virtual-offset.
- convertToShares/Assets round-trip creating value; cost-basis drift (3.3); reward double-claim (3.4).
- Strategy reports fake gain/loss; retains approval after migration; harvest sandwich.
- Per-block checkpoint staleness: a once-per-block opt leaving `(real−recorded)` delta exploitable (Cat 9.6 Tranchess).
- Mint/issue path floors only the INPUT, not the OUTPUT (3.7): `validateMaxIn` present but no `minLiquidity`/`minShares` floor, output sized from spot `getSlot0`/`getLiquidityForAmounts` → sandwich shrinks the position while max-in still passes (Uniswap V4 `_increaseFromDeltas`). Pair with Cat 5.2 spot-manip.

## Read first
Share-price calc path; `totalAssets` source (balanceOf vs internal); strategy interface powers; every once-per-block
guard → look downstream for a stale `(actual−recorded)` snapshot an attacker can order around.
Every share/liquidity MINT: is the amount RECEIVED floored (min-out), or only the amount SPENT capped? Spot-priced output + no floor = 3.7.

## Pairs into
numerical-gap (precision×invariant on share math) + trust-gap (keeper/strategy economics).
