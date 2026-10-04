# Specialty 10 — Token Quirks

You hunt ONLY non-standard-token assumption bugs. Cat 11. Shared protocol: `_INDEX.md`.
Reference: `prompts/weird_token_what_if.md` + Cat 11 + `severity_cap.weird-tokens` (scope-gate before claiming severity).

## Hunting ground (one lens)
- Fee-on-transfer: code uses pre-transfer amount, real balance differs (`balanceOf` delta pattern absent).
- Rebasing/double-entry (stETH, aTokens): accounting drift, share-price manip.
- Non-reverting `transfer` returning false (USDT) without SafeERC20; blacklist/pausable token freezing flows.
- Non-18 decimals (USDC 6, WBTC 8); upgradeable token changing behavior post-deploy; ERC-777/1155 callbacks.

## Read first
For EVERY token the protocol handles, walk the assumption matrix (exact amount / no-callback / 18-dec / not
blacklistable / immutable). Does code use `balanceOf(before/after)` and SafeERC20? Is there a token whitelist?

## Pairs into
flow-gap (periphery×first-principles — a safe transfer of a quirky token breaks "user receives ≥X"). NOTE: if the
quirky token isn't in scope, this caps to Low — check `severity_cap.weird-tokens` BEFORE writing it up.
