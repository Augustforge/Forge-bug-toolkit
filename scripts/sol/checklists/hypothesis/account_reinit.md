# Checklist: Account Reinit + Close+Reinit

- [ ] `init_if_needed` used? Verify constraint guard against existing data
- [ ] `init` without `if-already-init` — race condition in creation flow?
- [ ] Close instruction zero-fills data? Or leaves residual for stale discriminator attack?
- [ ] Same tx: close → reinit possible? Subsequent instructions check fresh discriminator?
- [ ] Lamports drain → account closed by runtime → re-init by attacker possible?

## PoC scaffold

`program_test_corpus/AccountReinit.rs.template`
