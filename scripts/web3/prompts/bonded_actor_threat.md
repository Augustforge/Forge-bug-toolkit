# Prompt: Bonded / Privileged Actor Threat Model

You're reading the following protocol source. The standard "outside attacker" lens already covered by `read_as_attacker.md`. This prompt is for a **different threat model**: actor who is **bonded / whitelisted / privileged**, behaves legitimately, but is adversarial.

Examples of bonded actors: TSS validator, oracle reporter, sequencer, relayer, keeper bot, restaking operator, governance signer, IBC relayer, LayerZero DVN, AVS operator.

> **Why this matters**: Thorchain ($10.8M, May 2026), Multichain ($120M, 2023), Ronin ($600M, 2022) — all exploited by malicious actor who was **inside the trust boundary**. Standard audits cover code-vs-outsider; bonded threat is a different scope often **out of audit**.

---

## Questions to answer

For each bonded actor role in the protocol:

1. **Who is this actor?** Name the role. What's the bond size / capital requirement to enter?
2. **What does protocol assume about them?** List explicit assumptions (e.g., "majority honest", "2/3 quorum", "single relayer is trusted", "operator won't censor").
3. **What can they legitimately do?** Sign messages, propose state, withdraw bonds, vote on upgrades, post oracle values, relay cross-chain messages, etc.
4. **What if one of them is malicious?** Walk through the legitimate flow, but at each step ask: "what if this actor returns malformed / stale / cherry-picked / adversarial input?"
5. **What is the minimum number of malicious actors needed to exploit?** 1 of N? Threshold? Full takeover?

---

## Specific lenses (apply ones that fit)

### TSS / MPC validators
- Can ONE malicious participant leak shards across multiple signing ceremonies?
- Are ZK proofs verified strictly (iterations ≥128, Paillier biprime checked)?
- Churn-in latency — can node sign immediately after joining?
- See `checklists/specialized/tss_mpc.md`.

### Oracle reporters / DVNs
- Does protocol verify oracle's last update was recent? (Stale data attack)
- Does protocol use single source vs N-of-M? Required DVN count?
- Can oracle return MAX_UINT or 0 without protocol breaking?

### Sequencers / Relayers
- Can sequencer censor specific user txs?
- Can sequencer reorder for MEV without slashing?
- L2 escape hatch — can user force-include if sequencer down?

### Keepers / Bots
- What if keeper never calls liquidation / harvest / update?
- Is there fallback for permissionless call?
- Loss windows if keeper opts out?

### Governance signers / multisig
- Quorum size vs total active signers? (1-of-2 = single point of failure)
- Timelock on critical actions?
- Can compromised signer block governance entirely (DoS on quorum)?

### Restaking operators / AVS
- Can operator slash trigger be gamed?
- Cross-AVS double-slashing without coordination?
- Withdrawal queue manipulation?

---

## Output format

For each adversarial-actor hypothesis:

1. **Actor + assumption**: "Protocol assumes [actor] is [property]. What if not?"
2. **Capability abuse path**: legitimate-call-but-malicious-input sequence
3. **Required bond/capital**: cost to mount attack
4. **Detection delay**: how long before honest parties notice?
5. **Severity**: IMPORTANT — bonded-actor attacks are often Critical (insider access)
6. **Mitigation gap**: what should the protocol do but does not?

---

## Anti-pattern-matching mindset (important)

**Don't ask**: "Is this similar to Ronin pattern?" — that fix already exists everywhere.
**Ask instead**: "What assumption does the protocol make about the bonded actor's input? Where can it be violated subtly, without protocol detection?"

The win — a broader class instance that nobody has found in this specific design.

---

## Protocol source:

(paste relevant protocol contracts / validator logic / off-chain code below this line)
