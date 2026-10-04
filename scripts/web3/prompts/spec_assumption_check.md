# Prompt: Spec-Assumption Check

`spec_miner.py` extracted MUST/SHALL/ALWAYS/NEVER claims from docs/README/whitepaper and tried to heuristically find a matching code guard. Some claims are marked `code_unenforced` (HIGH priority). Your task is to verify each one manually.

> **Why this matters**: Alchemix / Mezo / many DeFi exploits — the whitepaper says "system guarantees X", the code does not. The heuristic in spec_miner is coarse-grained. Each "code_unenforced" may be a real gap OR a false positive (keywords mismatched).

---

## Task

Read `spec_delta.md`. For **each HIGH** claim answer:

1. **Is the claim well-defined?** If the whitepaper says "users always benefit" — too vague. Drop.
2. **Where SHOULD it be enforced in code?** Identify the exact function/modifier.
3. **Is it actually enforced?** Read the exact code path:
   - Found a correct guard? → mark FALSE POSITIVE, claim enforced
   - Guard partial (covers some paths, not others)? → CONFIRMED GAP, strong signal
   - No guard at all? → CONFIRMED GAP, hypothesis for J1/J2
4. **Adversarial scenario**: if the claim is violated — what can an attacker do?

## Output

```markdown
### Claim: "<text from spec_delta>"
- **Source**: <doc file:line>
- **Expected enforcement**: <function/modifier where guard should live>
- **Actual code state**: ENFORCED | PARTIAL | UNENFORCED | FALSE_POSITIVE
- **Code location**: <file:line where you checked>
- **Hypothesis** (if gap):
  - "If user does X in function Y, claim violated because Z"
- **Severity if confirmed**: ...
```

## For MEDIUM (ambiguous) claims

Skip unless you have time. The heuristic couldn't resolve them — manual classification is expensive, payout uncertain.

## For LOW (code_enforced) claims

Skip entirely — the heuristic found a guard. Trust it, unless the target is a class (sophisticated protocol) that warrants a double-check.

---

## Anti-pattern

Don't read spec_delta.md and rubber-stamp findings. Each HIGH claim requires actual code reading. The heuristic in spec_miner is coarse-grained — it can err in either direction.

---

## Input (spec_delta.md):

(paste content of `sessions/$TARGET/[deep/]hypothesis/spec_delta.md` below)
