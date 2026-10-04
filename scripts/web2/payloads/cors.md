# CORS Misconfiguration — payload reference

> Cross-Origin Resource Sharing is configured so that an arbitrary (or semi-arbitrary) origin can
> read a sensitive response via `fetch`/`XHR` with credentials. Cross-ref: `invariant_library.md` →
> `## § Web2` (Task 8 will add a `CORS` row — at the time of this file the reference may be
> `[UNPINNED]`).

## Payloads

- **`ACAO: *` + `ACAC: true` (the combo is technically forbidden by the spec but still appears)**:
  if the browser actually allows reading the response with this combination on a given stack (not
  all browsers are equally strict about the invalid combination) — a direct finding. Verify in a
  real browser too, not just the headers.
- **Reflected origin without an allowlist**: send `Origin: https://attacker.com` in the request → if
  the response contains `Access-Control-Allow-Origin: https://attacker.com` (your Origin reflected
  literally) + `Access-Control-Allow-Credentials: true` — an arbitrary site reads the response with
  the victim's credentials.
- **`null` origin trust**: `Origin: null` (reachable via a sandboxed iframe `<iframe
  sandbox="allow-scripts" src="data:text/html,<script>...</script>">`, or a local `file://`) — if
  the server reflects/allowlists `null` as a valid origin.
- **Subdomain wildcard/regex over-trust**: an allowlist by regex `*.legit.com` or a suffix
  comparison (`origin.endsWith("legit.com")`) is bypassed with `legit.com.attacker.com`,
  `attackerlegit.com`, or a subdomain takeover of any forgotten `*.legit.com` (dangling
  DNS/S3/Netlify).
- **Protocol/scheme confusion in the allowlist**: the allowlist checks only the hostname without the
  scheme — `http://legit.com` (not HTTPS) may be accepted where only `https://legit.com` was
  expected, if the attacker can MITM/downgrade in an HTTP context.
- **Pre-flight (`OPTIONS`) not checked as strictly as the main request**: send a valid Origin on
  `OPTIONS` and an invalid one on the real `GET`/`POST` — if the browser has already cached the
  permissive preflight (`Access-Control-Max-Age`), check for TTL mismatches.
- **Trailing dot / case / punycode in the Origin**: `https://legit.com.` (trailing dot),
  `https://LEGIT.COM`, a punycode homoglyph of the domain — if the allowlist comparison is a plain
  string match and does not normalize.
- **Port as part of the origin**: `https://legit.com:1337` — the origin INCLUDES the port; if the
  allowlist compares only the hostname without the port, any port on the same host passes (relevant
  if the host allows arbitrary ports, e.g. via a proxy/dev mode).
- **CORS on an internal/admin API next to a public one**: the public `/api/*` is correctly
  restricted, but `/internal-api/*`/`/admin-api/*` (the same origin-policy code, copied carelessly)
  is broader.

## Detection Signal

- A real cross-origin `fetch()` with `credentials: 'include'` from an ATTACKER-controlled origin
  returns a readable response body with the victim's sensitive data (not just an ACAO header in
  devtools — confirm with a PoC page that actually reads the JSON).
- The response to an `OPTIONS` preflight contains an `Access-Control-Allow-Origin` literally equal to
  the arbitrary `Origin` header sent in the request (not a static list) — detectable with a one-line
  probe script (change the Origin → compare the echo in the response).

## Anti-FP

- `ACAO: *` WITHOUT `Access-Control-Allow-Credentials: true` — by spec the browser then does NOT
  send cookies/credentials; a readable response with no auth context may be an intentionally public
  API (check whether the response actually contains user-specific data without a token).
- The origin is reflected, but the endpoint returns exclusively public/non-critical data (not
  requiring authorization at all) — no sensitive impact; flag it honestly per the severity rubric.
- A dev/staging environment with wide CORS "for development convenience" — if it is NOT an in-scope
  production equivalent, dedupe/clarify scope before submitting.
