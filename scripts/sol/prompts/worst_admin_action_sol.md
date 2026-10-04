# Prompt: Worst Admin Action (Solana)

You are the program admin/upgrade authority. Without breaking obvious invariants, what's the worst thing you can do?

## Solana-specific admin surfaces:

1. **Upgrade authority** — can swap program bytecode entirely
2. **Mint/freeze authority** — token control
3. **Multisig signers** — what if 1 signer rogue?
4. **Durable nonce control** — pre-sign txs offline
5. **Config update authority** — change oracle, fee recipient, threshold
6. **IDL authority** — change frontend behavior (explicitly not an on-chain bug)
7. **Squads governance roles** — propose, approve, execute

Output each action and:
- What state changes?
- Who suffers?
- Is it reversible?
- What's the timelock (if any)?

If admin can drain pool via "legitimate" config change → it's a centralization concern that becomes Critical when admin key compromised (Drift 2026 lesson).

---

## Program source:
