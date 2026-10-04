# Hypothesis Scripts — Broader Classes, Not Pattern Templates

> ⚠️ **GLOBAL PRINCIPLE** (applies to EVM + Solana + future phases)

## Mindset

Every script in this folder is a **detector for a broader hypothesis class**, not a template for a specific known exploit. Known exploits (DeXe, Alchemix, Mezo, Curve) are **instances** of broader classes, not cookbooks to copy-paste.

**Why it matters**: if scripts look specifically for the "DeXe pattern" — we will only find the same bug in DeXe forks. Every other protocol **fixes exactly this pattern** after public disclosure. Worst of all: every other hunter has already run the same scan.

**The right approach** — generalize the exploit into a broader class and look for **new instances of the class** in other protocols.

## Script → Broader Class Mapping

| Script | Triggering exploit | Broader class | What to hunt |
|---|---|---|---|
| `asymmetry_scanner.py` | DeXe `delegateTokens` missing `ifNotStaken` | **Sibling control-flow drift** | Siblings that do similar things but have different modifiers/checks/state mutations |
| `comment_miner.py` | Alchemix `@dev oracle-independent guard` | **Author-declared invariants** | Comments declaring the author's assumptions, which may not hold in edge cases |
| `audit_trail_miner.py` | Mezo audit "fix" vs real code | **Stale documentation vs current code** | Commit messages, comments, audit reports describing code that has changed but wasn't updated |
| `variant_scanner.py` | Bug X in file A — is X in B,C,D? | **Class-of-bug propagation** | The same conceptual bug in other protocols/files after disclosure of one instance |
| `economic_analysis.py` | Generic | **Attack ROI feasibility** | Cost/profit/threat-tier for a confirmed hypothesis |
| `invariant_generator.py` | Generic | **Invariant break testing** | Auto-generate Foundry invariant tests from declared invariants |

## Output Tagging

Every script labels a finding as:
- `[known_class]` — matches a specific historical exploit pattern (low novelty, but valid)
- `[novel_instance]` — a new manifestation of a broader class (HIGH PRIORITY — where the payout lives)

When reporting, prioritize `[novel_instance]`. If all findings are labeled `[known_class]` — you are pattern-matching, not hypothesis-hunting. Think wider.

## Anti-Patterns to Avoid

❌ "Find functions named `delegate*` without `ifNotStaken`"  
✅ "Find siblings (functions with similar signatures, working on the same state) where modifiers/checks drift between them"

❌ "Search for `@dev oracle-independent` in comments"  
✅ "Search for comments that declare assumptions — invariants, expected behavior, edge case handling"

❌ "Find `_allocate` without an oracle check"  
✅ "Find paired code paths (with swap / without swap, fast / slow, public / internal) where a safety check is present in one but absent in the other"

## When Adding New Script

When adding a new hypothesis script:
1. Describe the broader class in the header comment — don't tie it to a specific exploit
2. List 2-3 instances of the class (known exploits)
3. The detection logic must find **any** instance, not only known ones
4. The output must support `classification: "known" | "novel"` tagging
5. Update this README with a new row in the table

## Related Docs

- `../HYPOTHESIS_GUIDE.md` — overall methodology
- `../HIGH_VALUE_PATTERNS.md` — 35+ patterns library (EVM)
- `../prompts/read_as_attacker.md` — adversarial mindset prompt
- `../../sol/hypothesis/README.md` — Solana counterpart (after Phase K)
