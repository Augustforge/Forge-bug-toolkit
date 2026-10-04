# First-Contact Email — Coordinated Disclosure (no bug bounty program)

Use this when a company has no official bounty program but you found a vulnerability and want to help responsibly.

---

**To:** security@{{company_domain}} *(or DMARC rua, or the security.txt contact)*
**Subject:** Security Vulnerability Report — {{company_name}}

---

Dear {{company_name}} Security Team,

I am a security researcher who recently identified a vulnerability affecting your **{{affected_component}}** ({{brief_description}}). I am reaching out via responsible disclosure to give your team time to address the issue before any public disclosure.

I would appreciate confirmation of the following before sharing technical details:

1. The most appropriate point of contact for security disclosures
2. Whether your team has a published vulnerability disclosure policy or PGP key
3. An acceptable timeline for our coordinated disclosure (I am happy to follow industry standards — typically 90 days)

I am willing to wait for confirmation of a secure communication channel before transmitting any technical details, proof-of-concept code, or exploitation steps.

I have:
- ✅ Limited my testing to non-destructive proof-of-concept actions
- ✅ Not accessed, modified, or exfiltrated any user or company data beyond what was required to demonstrate the issue
- ✅ Not shared this finding with any third party

Looking forward to working together to address this securely.

Best regards,
{{researcher_handle_or_name}}
{{contact_email_or_proton}}
{{pgp_fingerprint_optional}}

---

## Notes for the operator

- Send from a **dedicated email** (ProtonMail recommended), not your personal one
- If you have a researcher handle (`RESEARCHER_HANDLE` in `.env`) — use it instead of real name
- **Wait for response** before sharing details — typically 7-14 days
- If no response in 30 days → escalate to CEO/legal email or send via LinkedIn DM to CISO
- Document timeline in `sessions/{target}/status.md`
- Do NOT include the technical details in the first email — only after they confirm secure channel
