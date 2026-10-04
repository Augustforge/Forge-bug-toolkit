# Checklist: CPI Authority + Program ID

**Two distinct checks**:
1. **Authority**: who signs the CPI? Are signer_seeds correct?
2. **Program ID**: is target program verified, not spoofable? (Loopscale 2025 gap)

## Verification

- [ ] For each `invoke_signed`: signer_seeds match expected PDA?
- [ ] For each `invoke`/`invoke_signed`: target program_id verified via `require_keys_eq!`?
- [ ] CPI target from user input or from Anchor-validated Account? (raw user input = risky)
- [ ] Target program could be attacker-deployed with same interface?

## Known historical instances

- Loopscale 2025 ($5.8M): RateX program_id not verified, attacker substituted malicious clone

## PoC scaffold

`program_test_corpus/CpiAuthorityBypass.rs.template`
