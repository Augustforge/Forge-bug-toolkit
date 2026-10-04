# Checklist: Solana Multisig (Squads v4)

- [ ] Threshold <= total signers, > 0
- [ ] Approval cannot be double-counted (same signer twice)
- [ ] Durable nonce NOT used in admin flows (Drift 2026 lesson)
- [ ] Timelock present and > 0 between approval and execution
- [ ] Execution can be cancelled before timelock expiry
- [ ] Replay protection: executed flag immutable
- [ ] Signer set changes: multi-step + timelock
- [ ] Upgrade authority: separate multisig from operational?
