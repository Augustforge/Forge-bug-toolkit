# Checklist: Type Confusion (AccountInfo Cast)

- [ ] Each `AccountInfo<>` deserialized via typed cast: discriminator verified first?
- [ ] `try_from_account_info`: caller verified owner + discriminator?
- [ ] Multiple types of accounts with similar layout — confused?
- [ ] Token account vs token mint account substitution possible?
