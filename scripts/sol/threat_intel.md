# Solana Threat Intelligence — Exploits & Patterns

> Living document. After each new exploit disclosure → add entry + extract broader class.

## Critical Exploits 2022-2026

### Mango Markets ($114M, Oct 2022)
- **Root cause**: Oracle price manipulation via thin liquidity on MNGO perp futures. Attacker inflated MNGO collateral value 5x, borrowed against it, drained pool.
- **Broader class**: Oracle dependency without manipulation resistance (no TWAP / no liquidity check)
- **Tool hits**: `time_horizon_audit.py`, `economic_analysis.py`, `lending_hunter_sol.py`
- **Post-mortem**: [Helius blog](https://www.helius.dev/blog/solana-hacks)

### Wormhole ($325M attempted, Feb 2022)
- **Root cause**: `verify_signatures` accepted forged guardian signatures because the SignatureSet account passed by attacker was not validated as signer/owner. Fake account claimed verified.
- **Broader class**: "Any-account spoofing" — accounts trusted without identity verification (signer/owner/program)
- **Tool hits**: `signer_check_scanner.py`, `account_trust_audit.py`, `bridge_hunter_sol.py`
- **Post-mortem**: [Wormhole official](https://medium.com/@wormholecrypto/)

### Cashio ($52M, Mar 2022)
- **Root cause**: Fake collateral account passed — protocol didn't verify `account.owner == expected_program`. Attacker minted unlimited CASH stablecoins from fake collateral.
- **Broader class**: Missing owner check (same "any-account spoofing" class as Wormhole, different instance)
- **Tool hits**: `owner_check_scanner.py`, `account_trust_audit.py`
- **Post-mortem**: [Helius blog](https://www.helius.dev/blog/solana-hacks)

### Crema Finance ($8.7M, Jul 2022)
- **Root cause**: Tick array manipulation in CLMM. Attacker created fake tick accounts, manipulated price ticks to drain pool.
- **Broader class**: Auxiliary account trust (remaining_accounts validation gap)
- **Tool hits**: `amm_hunter_sol.py`, `account_trust_audit.py`
- **Post-mortem**: [Crema post-mortem](https://twitter.com/Crema_Finance)

### Raydium CLMM ($505K bounty, 2024)
- **Root cause**: `increase_liquidity` didn't verify `remaining_accounts[0]` was actually `TickArrayBitmapExtension` for the pool. Fake account → phantom liquidity → drain.
- **Broader class**: Account key validation in remaining_accounts (subclass of any-account spoofing)
- **Tool hits**: `amm_hunter_sol.py`, `account_trust_audit.py`
- **Fix**: `require_keys_eq!(remaining_accounts[0].key(), TickArrayBitmapExtension::key(pool_state_loader.key()))`
- **Post-mortem**: [Immunefi bugfix review](https://immunefi.com/blog/bug-fix-reviews/raydium-tick-manipulation-bugfix-review/)

### Loopscale ($5.8M, Apr 2025)
- **Root cause**: `get_pt_price` called without verifying RateX market's program ID. Attacker deployed malicious program with RateX interface, returned inflated PT price → undercollateralized loans.
- **Broader class**: CPI program ID not validated (NOT authority — different gap). Broader: ANY external program reference trust.
- **Tool hits**: `account_trust_audit.py`, `cpi_program_id_validator.py`, `lending_hunter_sol.py`
- **Post-mortem**: [Loopscale](https://blog.loopscale.com/posts/postmortem), [Halborn](https://www.halborn.com/blog/post/explained-the-loopscale-hack-april-2025)

### Marginfi flash loan ($160M prevented, Sep 2025)
- **Root cause**: `transfer_to_new_account` moved `lending_account` (with liabilities) to new account while `ACCOUNT_IN_FLASHLOAN` flag was active. Flag caused `check_account_init_health` early return — entire debt "evaporated".
- **Broader class**: State machine alternative routes — state flag bypass via account migration
- **Tool hits**: `state_route_analyzer.py`, `lending_hunter_sol.py`
- **Disclosed by**: Asymmetric Research
- **Post-mortem**: [Asymmetric Research](https://blog.asymmetric.re/threat-contained-marginfi-flash-loan-vulnerability/)

### Drift Protocol governance ($285M, Apr 2026)
- **Root cause**: NOT smart contract bug. Combination:
  1. Social engineering (DPRK actors, 6mo infiltration)
  2. Durable nonces — pre-signed txs stay valid indefinitely
  3. Squads 2-of-5 multisig with **zero timelock** → no delay between approval and execution
  4. After admin key compromise: malicious CVT market created, attacker oracle, 31 withdrawals in 12 min
- **Broader class**: Attacker-controlled time horizons + governance design gaps (zero-timelock, no revocation)
- **Tool hits**: `time_horizon_audit.py`, `governance_hunter_sol.py`, `multisig_hunter.py`
- **Post-mortem**: [BlockSec](https://blocksec.com/blog/drift-protocol-incident-multisig-governance-compromise-via-durable-nonce-exploitation), [QuillAudits](https://www.quillaudits.com/blog/hack-analysis/drift-protocol-multisig-exploit)

### Token-2022 ZK ElGamal Zero-Day (Apr 2025, patched before exploit)
- **Root cause**: Incomplete Fiat-Shamir Transformation in ZK ElGamal Proof Program — could forge valid ZK proofs for confidential transfers.
- **Broader class**: Cryptographic completeness gaps (missing hash components)
- **Tool hits**: `crypto_completeness.py`, `token_extensions_hunter.py`
- **Patched by**: Anza + Jito + Firedancer teams coordinatedly. ZK ElGamal Program temporarily disabled.
- **Post-mortem**: [The Block](https://www.theblock.co/post/353055)

## Emerging Attack Vectors 2025-2026

### Transfer Hook Reentrancy (Token-2022)
- Re-imports reentrancy into Solana (was "impossible" before).
- Token-2022 `transfer_checked` → hook program CPI → re-entry into caller.
- **Tool hit**: `callback_state_mutation.py`, `token_extensions_hunter.py`

### IDL Authority Takeover (Anchor)
- `IdlCreateAccount` is permissionless and one-time. Attacker can claim authority before legitimate IDL deployment.
- Disclosed in 2025 by Accretion: [Hidden IDL Instructions](https://accretionxyz.substack.com/p/hidden-idl-instructions-and-how-to)
- **Tool hit**: `permissionless_setup_race.py`, `idl_authority_scanner.py`

### Cross-Slot Validator Sandwich MEV
- 93% of Solana sandwiches happen across slots (different leader slots for front/back).
- 529K+ SOL extracted per year via this.
- Jito bundle protection doesn't help against malicious validators.
- Reference: [bloXroute analysis](https://bloxroute.com/pulse/a-new-era-of-mev-on-solana/)

### Bidirectional Rounding (Kamino-class potential)
- Same rounding direction in mint and redeem → profitable round-trip.
- Sec3 X-Ray detects this; manual audits often miss.
- Reference: [Sec3 blog](https://www.sec3.dev/blog/bidirectional-rounding)

### Custom Discriminator Collision (Anchor 0.30+)
- Custom discriminators allow overlapping prefixes across account types.
- Anchor 0.31 added ambiguity check, but legacy programs vulnerable.
- Reference: [Anchor PR #3157](https://github.com/solana-foundation/anchor/pull/3157)

## Stats from Sec3 2025 Ecosystem Review

- 163 audits, 1669 vulnerabilities
- Business Logic: 38.5% of all, 36.9% of High/Critical
- Input Validation: 25% of all, 27.9% of High/Critical
- Access Control: 19% of all, 20.7% of High/Critical
- On-chain Solana losses 2025: $8M (vs $550M peak 2022)
- 51% of audits contain High/Critical

Source: [Sec3 Solana Sec 2025](https://solanasec25.sec3.dev/)

## Update Protocol

When new exploit disclosed:
1. Add entry above with Root cause / Broader class / Tool hits
2. **DO NOT** just copy pattern — extract broader class first
3. Update relevant `hypothesis/*.py` script to catch broader class (not just this instance)
4. Add to `HIGH_VALUE_PATTERNS_SOL.md` if novel pattern
5. Check cross-chain amplifier (`sessions/_methodology/cross_chain_hypothesis_amplifier.md`): is there EVM analog?
