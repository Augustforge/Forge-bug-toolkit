# Checklist: Signer Identity Verification Gaps

**Broader class**: any account expected to sign not verified via `Signer<>` or `is_signer` check.

## Verification steps

- [ ] For each `pub fn` instruction: which accounts MUST sign?
- [ ] Each such account: is field typed `Signer<>` or has manual `is_signer` check?
- [ ] Sibling instructions: same field — Signer<> in one, AccountInfo<> in another? (asymmetry = bug)
- [ ] Admin/upgrade/governance handlers: explicit signer check?
- [ ] Multisig flows: each approver verified?

## Known historical instances

- Wormhole 2022 ($325M): SignatureSet account not verified
- Generic: admin transition without is_signer check

## PoC scaffold

See `program_test_corpus/MissingSignerCheck.rs.template`

## Mindset

**Not**: "Did I find Wormhole pattern?"  
**But**: "What other signer-required accounts are passed raw?"
