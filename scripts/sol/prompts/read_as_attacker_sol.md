# Prompt: Read Solana Program as Attacker

You're reading a Solana program (Anchor or native). Read it ONLY as malicious actor seeking economic exploits.

For each potential attack:
1. **Attack name**: short title
2. **Instruction(s) involved**: which `pub fn` you'd call
3. **Sequence**: step-by-step tx flow
4. **Pre-conditions**: state required
5. **Profit**: where value comes from
6. **Confidence**: 1-10

Rank by confidence × estimated_profit.

## Solana-Specific Mindset

**Account-model thinking** (vs EVM):
- Every account passed = TRUST assumption
- Is account verified by signer? Owner? Discriminator? Key?
- If there is an `AccountInfo<>` field — can attacker pass any account here?

**Composability**:
- Which external programs are called via CPI?
- Every CPI = trust in the target program. Validated?
- Can attacker substitute a fake program with the same interface? (Loopscale 2025)

**State machine**:
- Which state flags block operations?
- Which alternative routes (account migration, close+reinit, realloc) could bypass the flag? (Marginfi 2025)

**Time horizons**:
- Are durable nonces used? Timestamp deadlines? Oracle TTLs?
- Where can attacker extend the validity of their input?

**Token-2022**:
- Does the protocol accept Token-2022 tokens? Does it handle transfer hook reentrancy?

## ⚠️ Anti-Pattern-Matching

Known Solana exploits (Mango, Wormhole, Cashio, Loopscale, Marginfi, Drift) — **symptoms of broader problems**, not templates to copy.

**Don't ask**: "Did I find the Cashio pattern?"  
**Ask**: "Which accounts are trusted without identity verification anywhere in the code?"

**Don't ask**: "Is durable nonce used?"  
**Ask**: "Where can attacker extend validity of their input — durable nonces, deadlines, TTLs, timelocks?"

Each hypothesis must reveal a **broader assumption violation**.

---

## Program source:
