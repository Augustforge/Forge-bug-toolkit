# E-commerce / Payment Vulnerability Disclosure Report

**Title:** {{vulnerability_title}}
**Target:** {{target_domain}}
**Reporter:** {{reporter_name}}
**Date:** {{report_date}}
**Severity:** {{severity}} (CVSS {{cvss_score}})
**Compliance Impact:** {{pci_dss_relevant}}

---

## Summary

A {{vulnerability_type}} vulnerability was identified in the {{checkout_or_payment_flow}} flow on `{{target_domain}}` that allows {{impact_short}}.

Because this affects a payment / customer-data path, the issue has direct compliance implications under PCI DSS {{pci_dss_section}} and customer-facing data protection laws.

---

## Affected Component

- **Flow:** {{flow_name}} (e.g. checkout, account, order details)
- **URL / Endpoint:** `{{affected_url}}`
- **Parameter / Field:** `{{affected_parameter}}`
- **Page / Component:** {{component_name}}

---

## Steps to Reproduce

1. {{step_1}}
2. {{step_2}}
3. {{step_3}}
4. Observe: {{expected_result}}

### Proof of Concept

```http
{{request_dump}}
```

```http
{{response_dump}}
```

---

## Payment Data Impact

**Data exposed / manipulated:**
- {{data_item_1}}  *(e.g. partial card numbers, billing addresses, order history)*
- {{data_item_2}}
- {{data_item_3}}

**Customer data at risk:**
- Number of customers potentially affected: {{customer_count_estimate}}
- Categories of personal data: {{pii_categories}}
- Financial data exposure: {{financial_exposure}}

**Magecart / supply-chain context:**
{{magecart_relevance_note}}

**PCI DSS reference:**
- Requirement {{pci_requirement}}: {{pci_requirement_description}}

---

## Business Impact

- **Direct financial loss:** {{financial_impact}}
- **Regulatory exposure:** GDPR / CCPA / PCI DSS {{regulatory_note}}
- **Reputational damage:** {{reputational_note}}
- **Fraud potential:** {{fraud_potential}}

---

## Remediation

**Immediate:**
1. {{immediate_fix_1}}
2. {{immediate_fix_2}}

**Long-term:**
- {{long_term_1}}
- {{long_term_2}}

```{{language}}
{{example_fix_code}}
```

**Defense-in-depth:**
- Strict CSP (block inline scripts on payment pages)
- Subresource Integrity (SRI) for all third-party JS
- Tokenization of card data
- Logging anomaly detection on checkout

---

## References

- PCI DSS v4.0: {{pci_link}}
- OWASP ASVS Payment Controls: {{asvs_link}}
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

*Submitted in good faith under coordinated disclosure principles. Card-data evidence sanitized prior to submission.*
