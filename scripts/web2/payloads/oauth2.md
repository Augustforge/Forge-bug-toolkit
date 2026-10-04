# OAuth2 / OIDC — payload reference

> Classic flow abuse on the authorization-code/implicit grant. Cross-ref: `invariant_library.md`
> → `## § Web2` (Task 8 will add the `SSRF guard`/`session` rows applicable to redirect validation and
> session issuance after the code exchange — at the time of this file the link may be `[UNPINNED]`).

## Payloads

- **`redirect_uri` open redirect / host confusion**: an exact-string match is bypassed via —
  `https://legit.com.attacker.com`, `https://legit.com@attacker.com`,
  `https://legit.com%2f%2e%2e@attacker.com`, adding a port `https://legit.com:443@attacker.com`,
  path traversal `https://legit.com/../../attacker`, backslashes `https:/\/attacker.com`.
- **`redirect_uri` subdomain takeover / open-redirect chain on an allowlisted host**: if the whole host is
  allowlisted (`*.legit.com`), look for an open redirect OR a takeover of ANY subdomain — the code/token
  leaks there via the redirect.
- **Missing/predictable `state` (CSRF)**: if `state` is absent or predictable — CSRF login: the attacker
  initiates the OAuth flow with THEIR account, gets a code, feeds the victim a callback URL with THAT code →
  the victim's account is linked to the attacker's account (account takeover via link-confusion), or
  conversely the victim is linked to a foreign OAuth account.
- **`state` replay**: one `state` works more than once (not invalidated after first use) — a race/replay for
  account-linking CSRF.
- **Authorization code reuse**: a once-used code is still accepted on a repeat `/token` request (it should be
  single-use) → a race condition on the code exchange, a double exchange for two different client_ids.
- **Code interception via referer leak**: if the code is passed in a query parameter and the callback page
  loads third-party resources (analytics, images from an external host) — the code leaks via the `Referer`
  header of the third-party request.
- **Implicit-flow token in a URL fragment leak**: `#access_token=...` — the fragment is not sent to the
  server, but it leaks via: browser history, the referer of third-party scripts on the same page (JS
  libraries read `location.hash`), a postMessage handler without an origin check.
- **`scope` escalation**: request more scope on the authorize request than the client declared
  (`scope=openid+profile+admin`) — if the server does not validate scope against the registered client scope.
- **PKCE downgrade**: if the server supports PKCE but does not REQUIRE it — simply do not send the
  `code_challenge`, falling back to the classic code flow without PKCE protection (relevant for public/mobile
  clients where code interception is a real threat).
- **client_id confusion / mix-up attack**: the server does not check that the `client_id` in the token
  request matches the `client_id` the code was issued for (relevant with several OAuth providers on one login
  page — a code from provider A fed to provider B).
- **IDP response mix-up (multi-IDP)**: the app supports several IDPs — the attacker initiates the flow via
  THEIR malicious IDP, gets a redirect with a `code` valid for the client, but the client does not verify
  WHICH IDP the response actually came from.

## Detection Signal

- A `redirect_uri` bypass is accepted by the server (a 302 to the attacker host with the code/token in
  query/fragment) — the primary signal, BEFORE demonstrating an actual token capture.
- CSRF login: after the victim submits the `state`-less callback — the victim's account gains access / is
  linked to the attacker's account (verified with a second test account, not a production victim).
- Code reuse: a second `/token` request with an already-used code returns 200 with a valid access_token (not
  `invalid_grant`).

## Anti-FP

- Many `redirect_uri` mismatch variants are silently REDIRECTED by the server to the app's own error page
  (not to the attacker URL) — confirm the redirect actually went TO an attacker-controlled host, not merely
  that the request was not rejected with an error.
- `state` is absent, but the flow uses PKCE + another anti-CSRF mechanism (e.g. a nonce in a session cookie, a
  sec-fetch-site check) — assess the equivalent protection, do not stamp "no state = CSRF" automatically.
- Scope escalation is requested, but the server silently IGNORES the unregistered scope (returns a token
  without it) — not a bug; confirm the extended scope is actually PRESENT in the issued token.
