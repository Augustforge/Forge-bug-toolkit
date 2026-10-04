# Checklist: Account Owner Verification Gaps

**Broader class**: `account.owner` not verified against expected program — fake accounts with identical layout accepted.

## Verification steps

- [ ] For each `AccountInfo<>` field used for data loading: is `.owner` verified?
- [ ] For each `Account<'info, T>` field: is constraint/address/has_one provided?
- [ ] For accounts named `collateral`, `mint`, `token_account`, `stake`, `vault`: explicit owner check?
- [ ] SPL token operations: token_program account verified == TokenkegQfe...?
- [ ] Cross-program account passing: owner expectations documented?

## Known historical instances

- Cashio 2022 ($52M): collateral.owner not verified

## PoC scaffold

See `program_test_corpus/OwnerSubstitution.rs.template`
