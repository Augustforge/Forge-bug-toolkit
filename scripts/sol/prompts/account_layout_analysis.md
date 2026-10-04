# Prompt: Solana Account Layout Analysis

For each account struct, analyze:

1. **Discriminator**: 8-byte prefix — collision with other types?
2. **Layout fields**: typed correctly? Pack/repr issues?
3. **Size**: fixed or realloc? Within 10MB limit?
4. **Authority fields**: which fields control state changes?
5. **Stale data**: if account closed/reopened, what's residual?

## Discriminator collision check
- Anchor accounts use sha256("account:<StructName>")[..8]
- Custom discriminators (0.30+) — can collide
- 8-byte data prefix should uniquely identify type

## Field-by-field

For each field:
- Is it user-controlled?
- Is it admin-controlled?
- What invariants does it maintain?
- What happens at extreme values (0, MAX)?

## Cross-references

- Which instructions read this field?
- Which instructions write this field?
- Are write-paths gated by authority?
- Are read-paths trust-relying on write-path correctness?

---

## Account struct(s):
