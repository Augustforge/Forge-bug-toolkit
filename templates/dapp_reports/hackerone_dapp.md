<!--
HackerOne dApp report template

Structure: Title / Severity (CVSS) / Description / Steps to Reproduce / Supporting Material / Impact

Notes:
- HackerOne is web2-classic-flavored; many programs accept Web3 but format expectations align with H1's CVSS-based severity.
- CVSS: Critical 9.0+, High 7.0-8.9, Medium 4.0-6.9, Low <4.0.
- "Supporting Material" is uploaded separately in the H1 UI — list referencing only.
- Voice rules still apply; H1 doesn't have heavy WAF but voice tone matters for triage.
-->

# {{TITLE}}

**Severity (CVSS):** {{SEVERITY}}
**Asset:** {{TARGET}}
**Weakness:** {{CATEGORY}}

---

## Description

{{SUMMARY}}

{{VULN_DETAILS}}

## Steps to Reproduce

{{VALIDATION_STEPS}}

## Supporting Material / References

{{SUPPORTING_FILES}}

{{REFERENCES}}

## Impact

{{IMPACT}}

### Composed attack chain

{{ATTACK_CHAINS}}

## Recommended Fix

{{RECOMMENDATION}}
