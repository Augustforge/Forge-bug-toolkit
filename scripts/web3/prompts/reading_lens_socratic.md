# Reading Lens: Socratic Questioning

Trigger: you stop on a line whose purpose isn't immediately clear.

## The move

For the line, ask: *why is this here? what does it assume? what happens if the
assumption breaks?*

Don't accept *"because that's how it's written."* Don't accept *"the function name says
so."* Drill until you reach the implicit belief the code rests on. **The first answer is
usually a restatement of the code. The actual assumption is two or three "whys" deeper.**

Stop when the answer exposes the implicit belief — don't pad with extra steps just to hit
a quota.

## Example

`if (zrc20 != _ETH_ADDRESS_) IERC20(zrc20).transferFrom(msg.sender, address(this), amount);`

- Why is `zrc20 != _ETH_ADDRESS_` checked? → because ETH isn't transferable via `transferFrom`.
- Why is there no else branch? → because the developer assumed ETH arrives via `msg.value`.
- Where is `msg.value` enforced to equal `amount` for the ETH path? → **nowhere.** Bug.

## Required marker (anti-skim)

On an unclear line, emit in your working text — literal syntax, BEFORE continuing:

```
[Socratic: <file:line> — why?]
<one-line question that drills past "because that's how it's written"; if your first
 answer restates the code, ask again — until the implicit belief surfaces>
```

The marker lives in your reasoning stream — it does NOT go into the FINDING/LEAD block.

A senior auditor accepts no "because" without examining it.

See sibling lenses: `reading_lens_feynman.md`, `reading_lens_inversion.md`. Aggregator +
binding protocol: `../checklists/hypothesis/mental_tool_reading_protocol.md`.
