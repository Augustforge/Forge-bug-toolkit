<!--
Bugcrowd dApp report template

Structure: Title / Bug Type (VRT) / Severity (P1-P5) / Description / Steps to Reproduce / Affected URL / Suggested Fix

Notes:
- Bugcrowd uses VRT taxonomy — pick a leaf node carefully.
- P1 (Critical) — server-side RCE / full ATO; P5 — informational.
- For Web3 frontend findings most often: VRT > Broken Authentication & Session Management,
  VRT > Server Security Misconfiguration > Misconfigured DNS / HTTPS, VRT > CSRF / Clickjacking.
-->

# {{TITLE}}

**Bug Type (VRT):** {{CATEGORY}}
**Severity:** {{SEVERITY}}
**Affected URL:** {{TARGET}}

---

## Description

{{SUMMARY}}

{{VULN_DETAILS}}

## Steps to Reproduce

{{VALIDATION_STEPS}}

## Impact

{{IMPACT}}

### Composed attack chain

{{ATTACK_CHAINS}}

## Suggested Fix

{{RECOMMENDATION}}

## Supporting Files

{{SUPPORTING_FILES}}

## References

{{REFERENCES}}
