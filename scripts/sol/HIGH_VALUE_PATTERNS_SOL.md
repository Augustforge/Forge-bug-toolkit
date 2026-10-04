# Solana High-Value Patterns Library (35 patterns)

> Each pattern is **instance** of broader class — see [Methodology](../web3/HYPOTHESIS_GUIDE.md). Don't copy. Generalize.

## Core (proven exploits)

1. **Missing signer check** — `is_signer == false` not verified → unauthorized actor. **Wormhole 2022 $325M**.
2. **Missing owner check** — `account.owner != expected_program` not verified → fake account. **Cashio 2022 $52M**.
3. **PDA seed collision** — weak/predictable seeds → hijack PDA.
4. **Account reinitialization** — `init` without `if-already-init` guard → reset state.
5. **CPI without authority** — `invoke_signed` without verifying caller PDA.
6. **CPI program ID not validated** — target program ID not verified → spoofing interface. **Loopscale 2025 $5.8M**.
7. **Type confusion** — `AccountInfo<T>` cast without discriminator check.
8. **Arithmetic overflow** (Anchor < 0.30) — without `checked_*` ops.
9. **Sysvar trust** — Clock/Rent/Sysvar fake injection.
10. **Discriminator collision** — 8-byte instruction prefix overlap.
11. **Custom discriminator collision** (Anchor 0.30+) — overlapping custom discriminators.
12. **Compute budget DoS** — unbounded loops, large memcpy.
13. **Account key validation in remaining_accounts** — auxiliary account is not validated. **Raydium CLMM 2024 $505K bounty**.

## State / governance

14. **Flash loan state flag bypass** — flag not checked in new instructions. **Marginfi sep 2025 $160M prevented**.
15. **Durable nonce + zero-timelock multisig** — pre-signed tx valid indefinitely → admin takeover. **Drift apr 2026 $285M**.
16. **IDL authority takeover** — permissionless `IdlCreateAccount` → fake IDL deploy.
17. **Squads/multisig threshold drift** — signature verify race.
18. **Mint/freeze authority drift** — authority transferred, not validated downstream.

## Token / SPL

19. **SPL token program substitution** — fake `token_program` address passed.
20. **Token-2022 transfer hook reentrancy** — hook program CPI → reentrancy imported into Solana.
21. **Token-2022 confidential transfer ZK proof forgery** — incomplete Fiat-Shamir. **Token-2022 zero-day apr 2025, patched coordinatedly**.
22. **Token-2022 extension composability** — hooks + confidential are incompatible.
23. **Bidirectional rounding** — same rounding direction for mint and redeem → profitable round-trip. **Sec3 + Kamino potential**.

## Cross-chain / bridge

24. **Bridge signature replay** (Wormhole-class) — nonce reusable.
25. **Cross-chain replay** — chainId not in message hash.
26. **VAA reuse / guardian set drift** — Wormhole-style.

## Account lifecycle / memory

27. **Rent-exempt mismatch / close+reinit** — closed account re-init'd in the same tx, stale discriminator not checked → bypass.
28. **Lamports drain** — `account.lamports -= X` without verifying receiver.
29. **Closed account residual data** — close without zero-fill.
30. **Realloc abuse** — account realloc without validation.

## Solana-unique (no EVM analog)

31. **Sealevel parallel execution race** — Solana parallelizes non-conflicting txs. If protocol assumes sequential ordering for two operations BUT they don't share a writable account → they execute in parallel.
32. **Compute Unit budget DoS / MEV** — attacker requests max compute, then drops actual work.
33. **Rent-exempt threshold drift** — balance below rent-exempt → silently closed by runtime.
34. **AccountInfo lifetime / borrow checker bypass** — Anchor's `AccountLoader` + manual `borrow_mut` patterns can create a double-borrow.
35. **Validator-level MEV (cross-slot sandwich)** — frontrun + backrun in different leader slots (93% of sandwiches).

## Mindset Reminder

Each pattern above is **ONE instance**. Toolkit looks for **new instances of the broader class** in new protocols. If you just copy the pattern — you'll find the same bug in a Loopscale fork. Generalize.

See `../web3/HYPOTHESIS_GUIDE.md` for global methodology.
