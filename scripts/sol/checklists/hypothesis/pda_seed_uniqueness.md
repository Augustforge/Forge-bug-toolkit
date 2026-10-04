# Checklist: PDA Seed Uniqueness

- [ ] Empty seeds `[]` — guaranteed collision
- [ ] Static seeds only (constants) — predictable, anyone can pre-compute
- [ ] No bump binding — non-canonical bump exploit
- [ ] User key included in seeds for per-user PDA?
- [ ] Mint/account ref included for per-token PDA?
- [ ] Cross-instruction same seeds — collision across functions?

## PoC scaffold

See `program_test_corpus/PdaSeedCollision.rs.template`
