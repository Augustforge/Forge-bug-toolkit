# Blind SSRF — payload reference

> Server-Side Request Forgery with no direct reflection of the response in the HTTP response body —
> proven by an out-of-band (OOB) interaction. For in-band IP-obfuscation bypasses of
> allowlist/blocklist, see `ssrf_bypass.md` separately. Cross-ref: `invariant_library.md` →
> `## § Web2` (Task 8 will add an `SSRF guard` row — at the time of this file the reference may be
> `[UNPINNED]`).

## Payloads

- **Entry points (look for these FIRST)**: webhook URL config, avatar/image-from-URL upload,
  PDF/screenshot generator (URL → render), URL preview/unfurl (Slack-style link preview),
  import-from-URL (CSV/XML feed), SSO metadata URL config, XML `SYSTEM` entity (see the overlap with
  XXE), SSRF via PDF libs (`wkhtmltopdf`/`puppeteer` rendering attacker HTML with `<img src=...>`).
- **OOB callback (Burp Collaborator / interactsh / webhook.site)**: put your listener's URL into any
  of the entry points above → wait for an HTTP hit on the listener (this proves an outbound request,
  even if the app response shows nothing).
- **DNS-interaction detection**: if the HTTP callback does not fire (HTTP egress filtering) but the
  host itself is DNS-resolved, use a DNS-only listener (an `*.interactsh.com` A-record lookup already
  counts) — this proves the server at least RESOLVES an attacker-controlled domain (useful for a
  later DNS rebind, see `ssrf_bypass.md`).
- **Cloud metadata endpoint (169.254.169.254)**: put into the entry point `http://169.254.169.254/
  latest/meta-data/iam/security-credentials/` (AWS), `http://169.254.169.254/computeMetadata/v1/`
  (GCP, needs a `Metadata-Flavor: Google` header — if the app does a server-side GET without the
  header it may not work, but some SDKs add it themselves), `http://169.254.169.254/metadata/
  instance?api-version=2021-02-01` (Azure, needs `Metadata: true`).
- **Cloud metadata alt-representations (bypassing an allowlist on the `169.254.169.254` string)**:
  see `ssrf_bypass.md` — decimal/octal/hex/IPv6-mapped forms of the same address.
- **Internal network port scan via a time-based blind oracle**: if the app has a different response
  time for "port open, TCP connect succeeded, then a protocol timeout" vs "port closed, connection
  refused instantly", timing lets you enumerate the internal network even without a direct response.
- **Protocol smuggling via the URL scheme**: `gopher://`, `dict://`, `file://`, `ftp://` — if the
  server's URL parser accepts more than `http(s)://`, you can reach internal text-protocol services
  (Redis/Memcached/SMTP) via a gopher payload.
- **Second-order SSRF**: the URL is stored in the DB (e.g. a webhook config) and the request happens
  LATER, asynchronously (a cron/queue worker) — not at the moment of your request; wait for the
  deferred callback.

## Detection Signal

- An HTTP hit or DNS query on your OOB listener with a timestamp correlating to the moment the
  payload was sent — the only reliable proof for a blind SSRF (do not rely on error-message
  differences, they are easily false positives).
- A difference in HTTP response time between `http://169.254.169.254/...` (internal, a fast response
  OR a characteristic timeout) and a definitely non-existent internal IP — a secondary signal,
  weaker than OOB.
- A metadata-endpoint payload that returns, in an ASYNCHRONOUS channel (an email report, a webhook
  result, a generated PDF file), parsed contents of `iam/security-credentials/...` — the strongest
  proof (no longer blind, but originally found through a blind technique).

## Anti-FP

- The OOB hit must correlate by TIME and by a UNIQUE subdomain/token in the URL (generate a separate
  listener/subdomain FOR EACH test) — otherwise you cannot prove the hit came from THIS application
  rather than from your own browser/scanner/a third party.
- Some "SSRF" is actually a legitimate server-side fetch with an explicit, documented purpose (an
  image proxy BUILT for external URLs by design) — impact only if the internal network/metadata is
  REACHABLE through this same point, not the mere fact of an outbound request.
- An egress-filtered environment (the internal server has no outbound access at all) — OOB HTTP will
  not work structurally; switch to a DNS-only listener BEFORE concluding "no SSRF".
