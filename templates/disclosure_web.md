# Vulnerability Disclosure Report

**Title:** {{vulnerability_title}}
**Target:** {{target_domain}}
**Reporter:** {{reporter_name}}
**Date:** {{report_date}}
**Severity:** {{severity}} (CVSS {{cvss_score}})

---

## Summary

{{one_paragraph_summary}}

A {{vulnerability_type}} vulnerability was identified in `{{affected_endpoint}}` that allows {{impact_short}}. This issue can be exploited by {{attacker_profile}} to {{attacker_goal}}.

---

## Affected Component

- **URL / Endpoint:** `{{affected_url}}`
- **Parameter / Header:** `{{affected_parameter}}`
- **Component / Page:** {{component_name}}
- **HTTP Method:** {{http_method}}

---

## Steps to Reproduce

1. Navigate to `{{step_1_url}}`
2. {{step_2_action}}
3. {{step_3_action}}
4. Observe: {{expected_result}}

### Proof of Concept

```http
{{request_dump}}
```

```http
{{response_dump}}
```

### Screenshot / Recording

> ⚠ **Redact BEFORE attaching any PoC evidence** (`scripts/submission/evidence_redact.py`): run HAR/logs
> through `redact_har(har)` / `redact_text(log)`, and scrub screenshots of Cookie/Authorization/tokens/third-party PII.
> This protects your own test (burner) session from compromise and avoids leaking victim data to the triager.

{{poc_attachment_reference}}

---

## Impact

{{impact_paragraph}}

**Concrete consequences:**
- {{impact_item_1}}
- {{impact_item_2}}
- {{impact_item_3}}

**CVSS 3.1 Vector:** `{{cvss_vector}}`

---

## Remediation

**Recommended fix:**

{{remediation_paragraph}}

```{{language}}
{{example_fix_code}}
```

**Defense-in-depth:**
- {{additional_recommendation_1}}
- {{additional_recommendation_2}}

---

## References

- {{reference_1}}
- {{reference_2}}
- OWASP: {{owasp_link}}
- CWE-{{cwe_id}}: {{cwe_title}}

---

## Disclosure Timeline

| Date | Event |
|------|-------|
| {{date_discovered}} | Vulnerability identified |
| {{date_reported}} | Reported to {{vendor}} |
| {{date_acknowledged}} | Vendor acknowledged |
| {{date_fixed}} | Fix deployed |
| {{date_disclosed}} | Public disclosure |

---

*Report submitted in good faith under coordinated disclosure principles.*
