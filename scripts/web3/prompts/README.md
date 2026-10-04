# AI Prompts Library

Reusable prompts for /deephunt workflow. Use these to structure code reading.

Each prompt is a markdown file that you copy-paste into your AI assistant (or run via subagent) along with relevant contract source.

## Usage

```bash
# Append target source code to prompt and feed to AI
cat scripts/web3/prompts/read_as_attacker.md > /tmp/prompt.md
cat sessions/$TARGET/main_contracts.sol >> /tmp/prompt.md
# Then feed /tmp/prompt.md to claude/gpt/etc
```

## Prompts

| File | Purpose |
|------|---------|
| `read_as_attacker.md` | Read contract as a malicious user |
| `worst_admin_action.md` | What's the worst admin can do? |
| `invariant_extraction.md` | List every invariant assumed |
| `weird_token_what_if.md` | Fee-on-transfer, rebasing, ERC-777 scenarios |
| `state_after_revert.md` | Trace state after each revert point |
| `cross_function_interaction.md` | Pairwise function interactions |
| `upgrade_path_analysis.md` | Proxy upgrade safety |
| `mev_attacker_view.md` | Tx ordering attacks |
| `reading_lens_feynman.md` | Plain-English explain — fuzzy wording = hidden assumption (always first) |
| `reading_lens_socratic.md` | Drill an unclear line past "because that's how it's written" |
| `reading_lens_inversion.md` | Backward pass on a clean path — 3 concrete attacker moves |

The three `reading_lens_*` files are the mental-tool anti-skim protocol (Feynman/Socratic/Inversion)
with binding trigger→`[Tool:]` markers. Aggregator + rules:
`../checklists/hypothesis/mental_tool_reading_protocol.md`. Applied during T1 reading; markers required
on every score-3+ file. See `methodology/mythos_techniques.md` T1.
