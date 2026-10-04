# Reading Lens: Inversion

Trigger: a code path reads as clean / a check looks sufficient / a guard looks correct.

## The move

Every clean path gets a backward pass. After you understand what the code IS supposed to
do, ask: *how would I make it NOT do that?*

Same code, attacker's eye instead of developer's eye. The developer asks *"does this
work?"* The attacker asks *"how do I break this?"*

- Read every check → ask *"what value slips past it?"*
- Read every state update → ask *"what state am I in just before this?"*

A senior auditor never reads code only forward.

## Discipline after a "bug" conclusion

When you reach a bug conclusion you do NOT refute it — you **amplify the attack**: chain
it, find more victims, lower the precondition cost. *"You are an attacker — when you find
a bug, deepen the attack; never argue yourself out of one."* (= our
[[feedback_push_severity_ceiling]] + [[feedback_no_cheating_on_verification]].)

## Required marker (anti-skim)

When a path looks clean / a guard looks sufficient, emit in your working text — literal
syntax, BEFORE moving on:

```
[Inversion: <function>]
<three concrete attacker moves that attempt to defeat the path — specific addresses /
 values / states, not abstractions>
```

The marker lives in your reasoning stream — it does NOT go into the FINDING/LEAD block.

See sibling lenses: `reading_lens_feynman.md`, `reading_lens_socratic.md`. Aggregator +
binding protocol: `../checklists/hypothesis/mental_tool_reading_protocol.md`.
