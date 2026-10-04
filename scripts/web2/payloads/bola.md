# BOLA (Broken Object Level Authorization) — payload reference

> API1:2023 (OWASP API Top 10). An object (record/resource) is reachable by ID without checking
> that the ID belongs to the currently authenticated user. Cross-ref: `invariant_library.md` →
> `## § Web2` → the `authz` row (framework-guard vs inline-check).

## Payloads

- **Sequential ID walk**: `/api/orders/1001` → `1000`, `1002`, `999`, `1` (swap your own ID for an
  adjacent one). Works on auto-increment PKs (SQL serial, Mongo ObjectId with a time component).
- **UUID/ObjectId guess**: if the ID looks random, check whether it leaks in another response
  (object list, referer, email notification, public share link, error message).
- **Parameter pollution on the ID**: `GET /api/order?id=1001&id=1002` — some frameworks take the
  last/first value, bypassing a middleware check that reads a different array index.
- **ID in different request locations**: path vs query vs body vs header (`X-Resource-Id`) —
  authorization may be checked against ONE location while business logic reads the ID from ANOTHER
  (mismatch = BOLA).
- **Nested/related object walk**: `/api/users/{me}/orders/{other_order_id}` — the top-level `{me}`
  is checked, the nested `{other_order_id}` is not.
- **Method+ID combo**: `GET` on someone else's ID may return 403, but `PUT`/`DELETE`/`PATCH` on the
  same ID may not (the check is not applied on every method of a route).
- **Batch/bulk endpoints**: `POST /api/orders/batch {"ids":[1001,1002,9999]}` — bulk routes often
  forget the per-item authz that the single-item route has.
- **Export/PDF/report endpoints**: `/api/invoice/{id}/pdf` — secondary routes (export, print,
  webhook-replay) regularly fail to inherit the authz guard of the primary route.
- **GraphQL node ID**: `query { node(id: "T3JkZXI6MTAwMQ==") { ... } }` — a base64 global ID often
  just decodes to `type:pk`, so guessing = brute-forcing the PK within a known type.
- **IDOR via file/attachment path**: `/uploads/{user_id}/{filename}` — if `user_id` is not checked
  against the session, iterating `user_id` exposes other users' files.

## Detection Signal

- A 200 response with someone else's data instead of 403/404 — the primary signal.
- A difference in response shape between "object exists but isn't yours" (should be a uniform
  404/403) and "object doesn't exist" — if the app returns DIFFERENT codes/texts for those two
  cases, that is already an enumeration oracle (you can find existing IDs by brute force even
  without reading the data). Cross-ref: `invariant_library.md` → `## § Web2` → `authz`.
- A timing difference between "exists, not yours" and "doesn't exist" — a secondary oracle when the
  codes are identical.

## Anti-FP

- Check whether the object is intentionally public (public listing, shared-by-design resource) —
  read the feature docs/UI before calling a finding an IDOR.
- Multi-tenant with an intentionally shared read-only reference set (catalog/reference data) — not
  a bug.
- If the ID is adjacent but belongs to YOUR OWN second test account in the same organization
  (intended team sharing) — not a bug; check the org/team boundary, not the user boundary.
