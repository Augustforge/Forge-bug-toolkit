# Checklist: Sysvar Trust

- [ ] Clock used as `Sysvar<'info, Clock>` (typed), not `AccountInfo`?
- [ ] Rent used as `Sysvar<'info, Rent>`?
- [ ] StakeHistory, SlotHashes, etc. — typed wrappers?
- [ ] If manual sysvar deserialization: key check vs `solana_program::sysvar::clock::id()`?
- [ ] Time-based logic doesn't fully trust Clock (validator can drift) — use slot for monotonic ops?
