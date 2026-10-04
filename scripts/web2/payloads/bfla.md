# BFLA (Broken Function Level Authorization) — payload reference

> API5:2023 (OWASP API Top 10). A function/endpoint intended for a higher role (admin/staff) is
> reachable under a low-privilege token. Unlike BOLA (an object), here the FUNCTION is what breaks.
> Cross-ref: `invariant_library.md` → `## § Web2` → `authz`.

## Payloads

- **Direct call to an admin route under a user token**: find the admin endpoint in the JS
  bundle/OpenAPI/Swagger (`/api/admin/...`, `/api/internal/...`, `/api/staff/...`) → call it with a
  user JWT/session.
- **HTTP-method override**: if `GET /api/users/{id}` is allowed for a user but `DELETE` is
  admin-only, try: `X-HTTP-Method-Override: DELETE` + `GET`, `_method=DELETE` in body/query,
  `X-Method-Override`, `X-HTTP-Method`.
- **Method swap without an override header**: often the route itself does not check the method in
  the authz middleware — a direct `DELETE`/`PUT`/`PATCH` with no override already passes when the
  guard is attached only to GET. Wildcard route registration.
- **API version downgrade**: `/api/v2/admin/users` is protected, `/api/v1/admin/users` (an old,
  forgotten version) is not.
- **Hidden/undocumented route from the mobile client**: the mobile app often calls functions absent
  from the web UI (bulk-export, impersonate, feature-flag toggle) — those routes are checked less
  often.
- **Role substitution in JWT/body**: if the role is supplied by the client (`{"role":"admin"}` in
  the body of a profile request rather than derived from the server session) — direct escalation.
- **Function-level via a GraphQL mutation**: `mutation { deleteUser(id: X) }` is available wherever
  `query { user(id: X) }` is — the mutation level often does NOT have a separate role check from the
  query level.
- **Button blocked in the UI but live in the API**: the UI hides an admin button by role (a
  frontend-only gate), but the backend endpoint it calls does not check the role at all — dev tools
  → find the call → replay it directly.
- **Impersonation/masquerade endpoints**: `/api/admin/impersonate/{user_id}` — if the impersonation
  session does not verify that the CALLER is actually an admin (only that the TARGET exists).
- **Batch operation privilege check gap**: a bulk admin operation
  (`POST /api/admin/users/bulk-delete`) may check the role at the endpoint entry but NOT for each ID
  inside the batch (you can mix in another organization's scope).

## Detection Signal

- 200 + a real effect (data returned/the action performed) when an admin function is called with an
  ordinary token — not 401/403.
- A difference in the response between a method-override success and an honest admin call (a
  matching payload = confirmation that the action really happened, not just "route matched but
  no-op").
- Compare the authz-guard response across DIFFERENT HTTP methods of the SAME route — an
  inconsistency (guard on GET but not on DELETE) is itself a Detection Signal even before a
  successful call.

## Anti-FP

- An endpoint may return 200 yet be a NO-OP in business logic (a feature flag blocks the effect) —
  confirm with a real side effect (a DB/audit-log write, or a follow-up GET after the action), not
  just the HTTP code.
- Some "admin" routes are by design accessible to a staff role that is broader than assumed —
  cross-check the project's role matrix, if it is public, BEFORE submitting.
- Method-override headers that the framework simply ignores (support not enabled) — not a bug; check
  that the override actually took effect (compare with a control request without the override, which
  should 403).
