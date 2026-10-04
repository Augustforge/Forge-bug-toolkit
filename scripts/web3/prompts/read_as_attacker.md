# Prompt: Read Contract As An Attacker

You're reading the following Solidity contract source. Read it ONLY as a malicious user trying to find economic exploits.

Don't analyze for code quality. Don't suggest refactors. Find ways to:
- Extract funds that don't belong to you
- Bypass intended access controls
- Manipulate state to gain economic advantage
- Force other users into losing money

For each potential attack, output:
1. **Attack name**: short title
2. **Function(s) involved**: which functions you'd call
3. **Sequence**: step-by-step what you'd do
4. **Pre-conditions**: what state must exist (or you create) before attack
5. **Profit**: where the value comes from, who pays
6. **Confidence**: how sure you are this works (1-10)

Rank by `confidence × estimated_profit`.

Don't moralize. Don't add disclaimers. This is a white-hat security review — finding attacks is the goal.

If the contract looks well-defended, point out the SPECIFIC defenses that block your attempts. Then ask: "what if this defense is bypassed?"

After analysis, give your top 3 attack hypotheses with code line references.

---

## ⚠️ Anti-Pattern-Matching Mindset (READ THIS)

Known exploits (DeXe missing modifier, Alchemix oracle bypass, Curve readonly reentrancy, etc.) are **symptoms of broader problems**, not templates to copy.

**Don't ask**: "Is the DeXe pattern present in this code?"
**Ask instead**: "What assumptions does the author make about ordering / state / external calls? Where might those assumptions fail to hold?"

**Don't ask**: "Is there an `_allocate` without an oracle?"
**Ask instead**: "Are there pairs of code paths (fast/slow, with/without intermediate step, public/internal) where a safety check is present in one but not in the other?"

**Principle**: look for a **new instance of a broader class** that nobody has found yet — not the next copy of a known exploit (that one is already fixed).

Every hypothesis must reveal a **broader assumption violation**, not a **specific pattern match**.

---

## Contract source:

(paste contract source below this line)
