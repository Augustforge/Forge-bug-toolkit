# Reading Lens: The Feynman Test (FIRST — before anything else)

Apply this the moment you open ANY new function or contract — before you reason about
anything else. Code you have not Feynman'd is code you have not actually understood.

## The move

STOP and ask: *"Can I explain what this function does to someone who doesn't know Solidity?"*

Explain it in plain words. No `transferFrom`, no `mload`/`assembly`, no `safeTransfer`,
no jargon. Use as many sentences as you need until the explanation is solid.

**The places where your explanation gets fuzzy — where you reach for a Solidity term
instead of plain meaning — are where you're papering over an assumption. That is where
bugs hide. Mark that spot.**

## Example

You read `_handleFeeTransfer(zrc20, fee)` and your explanation comes out as
*"it transfers the fee."* That is NOT Feynman.

Feynman is: *"it picks up the protocol's commission off the user's payment and moves it
to the treasury wallet."* Now keep going: what if the payment is in ETH and the function
uses an ERC20 method? Your plain-English explanation breaks. **Bug.**

## Required marker (anti-skim)

When you open a function/contract to read, emit in your working text — literal syntax,
BEFORE continuing:

```
[Feynman: <function-or-contract-name>]
<plain-English explanation; mark every spot where wording slips to jargon>
```

The marker lives in your reasoning stream — it does NOT go into the FINDING/LEAD block.

A senior auditor doesn't trust their understanding until they can explain it without the
safety net of technical vocabulary. Trust your discomfort.

See sibling lenses: `reading_lens_socratic.md`, `reading_lens_inversion.md`. Aggregator +
binding protocol: `../checklists/hypothesis/mental_tool_reading_protocol.md`.
