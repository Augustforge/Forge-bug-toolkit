<!--
Cantina dApp report template (per [[reference-cantina]])

Structure: Summary / Vulnerability Details / Impact / Code Snippet / PoC / Mitigation
References

Critical considerations:
- DEDUP FORMULA: Points = Full / (1 + 0.8 × (n−1))
  → If finding is Slither/Mythril-discoverable, expect N hunters submitted same =
    low EV per submission. Add unique angle if possible.
- Severity: Critical (no user action), High (minor friction), Medium (significant friction),
  Low (degraded UX), Info, Gas.
- Competition format: time-boxed contests vs ongoing bounties.
- No HTML reveals of automation. 1st person OR 3rd-passive.
-->

# {{TITLE}}

**Severity:** {{SEVERITY}}
**Target:** {{TARGET}}
**Category:** {{CATEGORY}}

---

## Summary

{{SUMMARY}}

## Vulnerability Details

{{VULN_DETAILS}}

## Impact

{{IMPACT}}

## Code Snippet

<!--
For dApp frontend findings, paste the relevant JS/TS chunk from the production
bundle, or quote the auth provider config response. Use fenced code blocks
sparingly — Cantina renders markdown directly.
-->

## Proof of Concept

{{VALIDATION_STEPS}}

### Composed attack chain

{{ATTACK_CHAINS}}

## Mitigation / Recommendation

{{RECOMMENDATION}}

## References

{{REFERENCES}}

## Attached Files

{{SUPPORTING_FILES}}

<!--
Dedup analysis:
- Could a Slither/Mythril/Aderyn scanner have found this? If yes → expect dups.
- What unique angle differentiates this from a surface scan? (Composed attack,
  cross-program variant, novel exploitation primitive.)
- Add `### Unique Angle` section if competition reports likely to converge.
-->
