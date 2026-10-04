# Mental-Tool Reading Protocol — anti-skim discipline for code reading

Three reading tools with **binding trigger→marker protocol**. They are NOT optional steps;
you reach for the one the moment its trigger fires, and you **emit the marker in your
working text BEFORE continuing**. This is the operational mechanism behind "don't skim,
don't trust your first read" — it forces reasoning depth instead of surface scanning, which
is the failure mode of every junior auditor. Adapted from pashov/skills senior-auditor SOP;
see [[reference_pashov_skills]] block B.

This complements two things we already have — keep them linked, don't restate:
- **T1 assumption-enumeration lens** (`methodology/mythos_techniques.md` T1): "every opt/guard/
  cache/early-return is an undocumented bet — who controls the variable that breaks it?"
  Feynman/Socratic are HOW you surface that bet line-by-line.
- **`prompts/read_as_attacker.md`**: the malicious-reader frame; Inversion is its per-path drill.

## The three tools (full prompts: `../../prompts/reading_lens_{feynman,socratic,inversion}.md`)

| Trigger (the condition) | Required marker (literal `[Tool: ...]` syntax) | Content |
|---|---|---|
| You open a new function or contract to read | `[Feynman: <name>]` | Explain in plain English — no Solidity jargon. Wherever wording slips to a technical term, you're papering over an assumption — mark it; bugs hide there. |
| You stop on a line whose purpose isn't immediately clear | `[Socratic: <file:line> — why?]` | One-line question drilling past "because that's how it's written." First answer restates code — ask again until the implicit belief surfaces. |
| A path reads clean / a check looks sufficient / a guard looks correct | `[Inversion: <function>]` | Three concrete attacker moves to defeat the path — specific addresses/values/states, not abstractions. |

**Feynman is ALWAYS first** — apply it the moment you open any function, before reasoning
about anything else. Code you have not Feynman'd is code you have not understood.

## Rules
1. **Triggers are not optional.** Condition fires → marker follows. Always. No skipping.
2. **Literal `[Tool: ...]` syntax** so markers are greppable (self-audit: count markers vs
   functions read; a score-3+ file read with zero markers = you skimmed, re-read).
3. **Extra markers are fine; skipping a triggered one is not.**
4. **Markers live in reasoning text — NOT in the FINDING/LEAD / hypotheses.md output block.**
5. **On a bug conclusion: amplify, don't refute** — chain it, find more victims, lower the
   precondition cost (= [[feedback_push_severity_ceiling]]). Refuting a true positive out of
   self-doubt is the inverse failure of the cold T4 verifier (Mandate 0.7).

## Where this plugs in
- **T1 reading** (every score-3+ file): markers fire continuously throughout the read, not
  just at the top.
- **T2 STATE A**: each hypothesis carries the `[Tool: ...]` marker(s) that surfaced it — a
  hypothesis with no marker trail is a coverage gap masquerading as a check.
- **A fan-out specialties** (Stage 4): every specialty lens applies this protocol while reading.

## Cross-contract weaponization (carry-over from the same SOP)
When you find a bug in one contract, **search the same pattern across every sibling** — by
function name AND by code shape. Missing a repeat instance (e.g. native/ERC20 confusion in one
`onRevert` but not checking the others) is an audit failure. (= our T3 chaining +
sibling-class enumeration, taxonomy Cat 17.1.)
