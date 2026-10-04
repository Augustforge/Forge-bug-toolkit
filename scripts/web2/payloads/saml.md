# SAML / SSO — payload reference

> Class: SP-impersonation / ATO by breaking trust in the assertion signature. XML parsers are notoriously
> inconsistent → SSO bugs are often High–Critical. Trigger endpoints: `/saml/acs`,
> `/sso/saml`, `/auth/saml/callback`, `/Shibboleth.sso`, ADFS
> `/adfs/ls/`, `/FederationMetadata/2007-06/FederationMetadata.xml`, SimpleSAMLphp
> `/saml2/idp/metadata.php`, Keycloak `/auth/realms/*/protocol/saml`. Tool: SAML Raider (Burp).
> **Gate: an auth-decision-changing step is mandatory** — editing display-name/locale without changing the
> NameID/role = Informational.

## Recon (before the attack)

- Fetch the IdP metadata → entityID, signing cert(s), SSO endpoints, NameID format.
- Decode the SAMLResponse: `base64 -d` (POST binding = raw base64 without compression; Redirect binding = raw
  DEFLATE, `zlib.decompress(raw, -15)`).
- **Key question:** is the signature at the `<Response>` level (better) or only on the `<Assertion>` (→ XSW
  possible)? What is signed and what the Reference URI covers.

## Payloads

- **XSW1 — duplicate-assertion injection** (classic): keep the original signed assertion
  (`ID="legit"` + a valid `<ds:Signature>`), add an evil assertion BEFORE it (`ID="evil"`,
  `<NameID>admin@company.com</NameID>`). The signature is still valid (it covers `#legit`), but the SP
  processes the FIRST assertion found = the evil one.
  - Detection Signal: the SP creates a session as `admin@company.com` — the forged SAMLResponse was accepted.
- **XSW2 — the Signature is moved outside / into a sibling** of the signed element (bypasses libraries that
  check the signature position relative to the root).
  - Detection Signal: an assertion with NameID=admin accepted even though the signature is not in canonical position.
- **XSW3 — an evil assertion as a sibling of the signed one, but processed first** (URI-fragment mismatch:
  the signature references `legit`, the SP reads `evil`).
  - Detection Signal: a session under the evil NameID.
- **XSW4 — a nested duplicate: the signed assertion inside an evil assertion** (or vice versa) — hits
  libraries that process all statements, not just the first.
  - Detection Signal: the SP reads the injected AuthnStatement/AttributeStatement, overriding the original.
- **XSW5 — the `ID`/`xml:id` on the INJECTED assertion matches the signature Reference URI** (libraries that
  match by the ID string rather than by DOM position).
  - Detection Signal: the evil assertion with the same ID passes the signature check.
- **XSW6 — namespace-prefix injection**: declare an alias for the SAML namespace; the injected assertion uses
  a different prefix but the same namespace (hits libraries that key on the prefix string).
  - Detection Signal: the evil assertion with the alias prefix is accepted.
- **XSW7 — XXE inside the Reference URI / assertion** to poison the digest check (libraries that resolve
  entities during signature validation). Overlaps with `xxe.md`.
  - Detection Signal: the digest matches on substituted content.
- **XSW8 — XSLT-transform injection in `<ds:Transform>`**: the transform changes the post-signature DOM
  (libraries that apply the transform AFTER verification).
  - Detection Signal: verified-DOM != processed-DOM, the NameID is substituted.
- **Signature-strip**: decode → delete the whole `<Signature>` element → change the NameID to admin → re-encode
  base64 → POST to the ACS. Works on an SP with `WantAssertionsSigned="false"` or without a signature-presence check.
  - Detection Signal: an unsigned/modified assertion accepted, an admin session issued without a crypto check.
- **NameID comment-injection (C14N differential)**: `<NameID>admin@company.com<!---->.evil.com</NameID>`
  — the signer canonicalizes (C14N without-comments) to `admin@company.com.evil.com` (what is signed, and the
  attacker owns that domain), while the SP's text extraction reads up to the comment boundary =
  `admin@company.com`. The divergence is the bug (CVE-2017-11428 Ruby-SAML/OneLogin, CVE-2016-5697).
  - Detection Signal: the SP logs in as `admin@company.com` even though `...evil.com` was signed.
- **Multi-signature / signature-copy**: the SP accepts an assertion with MULTIPLE `<ds:Signature>`. Take a
  valid signature from any past/demo assertion, attach it to the evil assertion — the SP checks that a
  signature EXISTS, but not WHAT it covers.
  - Detection Signal: the evil assertion with someone else's valid signature is accepted.
- **Key-confusion (federated multi-IdP)**: an assertion signed by an ATTACKER IdP (IdP-A) sent to an SP that
  trusts IdP-B. If the SP does not validate `<Issuer>` — it accepts it.
  - Detection Signal: an assertion signed by a foreign key grants access (the SP does not check Issuer against
    the expected IdP).
- **Audience-restriction bypass**: an assertion issued for service A (`<AudienceRestriction>` = A/or absent)
  accepted by service B without validating Audience → cross-SP token reuse.
  - Detection Signal: an assertion for another SP creates a session on the target SP.
- **Replay**: the same SAMLResponse sent twice within the validity window (`NotOnOrAfter`) — if there is no
  `InResponseTo`/one-time-use enforcement, a second session is created.
  - Detection Signal: resubmitting the same Response yields a second valid session.
- **XXE-in-SAML**: `<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
  <saml:Assertion><NameID>&xxe;</NameID></saml:Assertion>` — if the SAML parser lacks `disallow-doctype-decl`.
  - Detection Signal: file content in the SP's error response / audit log (a file-read on the SP infra).

## Severity triage

- XSW success / signature-strip = **Critical** (ATO of any user).
- Comment-injection / key-confusion / audience-bypass → admin ATO = **High–Critical**.
- XXE-in-assertion = **High** (file-read/SSRF).
- NameID manipulation = **Medium/High** (depends where the NameID maps).
- Replacing non-security attributes (display-name/locale) without changing the auth decision = **Informational**.

## Modern CVE anchors (2024-2025 ruby-saml wave)

CVE-2025-25291/25292 (ruby-saml ≤1.17 — XSW/parser-differential), CVE-2024-45409 (ruby-saml ≤1.16 — XSW),
CVE-2024-45428 (GitLab/ruby-saml — full ATO). Cite the technique + observed behavior, NOT an unverified
CVE/H1-ID.

## Anti-FP / what NOT to submit on its own

- **Modification without crossing an auth boundary** — a theoretical XML manipulation that does not change the
  NameID/AuthnContext/role-bearing AttributeStatement = Informational.
- **SP metadata publicly accessible** (`/saml/metadata`) — informational by itself; the finding is what the
  metadata reveals (unsigned requests, weak algorithms).
- **Signature-strip on a modern SP** — most reject unsigned; verify actual acceptance.
- **Replay** — if the SP validates `InResponseTo` / one-time, replay fails; verify with a double submission.
- **SAML != JWT** — do not cross-apply techniques (XML signature vs JSON-JWS).
- **Golden SAML** (forging tokens from a stolen ADFS token-signing cert) — post-exploitation, outside the
  white-hat scope of a non-destructive PoC; mention as impact, do not execute.
