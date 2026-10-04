# Prompt: CPI Chain Analysis (Solana)

Trace cross-program invocations in this program.

For each `invoke` / `invoke_signed`:

1. **Target program**: what program is called?
2. **Program ID verification**: is target's pubkey verified before invoke? (Loopscale 2025 gap)
3. **Authority**: who signs the CPI? PDA seeds correct?
4. **Account list**: which accounts forwarded? Trust assumptions on those?
5. **Re-entrancy surface**: can target callback into us?
6. **State mutations**: do we mutate state before/after CPI? Reentrancy-safe?

## Token-2022 special considerations

If CPI is to Token-2022 program (`TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA` or `TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb`):
- Could target token have transfer hook? → re-entrancy via hook callback
- Could token have transfer fee? → received amount != sent amount
- Could token be frozen? → instruction reverts mid-flow leaves stale state?

## CPI graph

Build full CPI graph:
- Program → Program → Program (depth 3+)
- Find composability bottlenecks
- If program A heavily depends on B → compromise of B breaks A (Loopscale-class)

---

## Program source:
