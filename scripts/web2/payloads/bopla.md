# BOPLA (Broken Object Property Level Authorization) — payload reference

> API3:2023 (OWASP API Top 10, merges the old Excessive Data Exposure + Mass Assignment at the
> PROPERTY level of an object, not the whole object). Separate from `mass_assignment.md`: that one
> focuses on privileged fields at CREATE time, this one on arbitrary read/write fields of the object
> as a whole, including over-fetch on READ. Cross-ref: `invariant_library.md` → `## § Web2` →
> `authz`.

## Payloads

- **Response over-fetch (excessive data exposure)**: compare which fields are DOCUMENTED in the
  frontend types/OpenAPI vs what actually comes back in the raw JSON response (`internal_notes`,
  `cost_price` vs `display_price`, `password_hash`, `ssn`, `is_flagged_fraud`, `risk_score`) — the
  frontend simply does not RENDER the extra fields, but the server returns them.
- **Write-property walk**: on an update endpoint, walk through ALL of the object's fields (not just
  the ones visible in the form) — `is_verified`, `email_confirmed`, `subscription_tier`,
  `discount_percent`, `internal_status`.
- **Read-only field as writable**: `created_at`, `owner_id`, the object's own `id` — if the server
  accepts them in a PATCH request without error, check the effect (owner_id transfer = object
  takeover).
- **Nested object property injection**: `{"user": {"profile": {...}, "permissions": {"admin": true}}}`
  — a nested object inside a legitimate payload can sneak in a field that the top-level DTO
  validator does not see but the ORM does see at save time.
- **Field-level authz by role, missing where object-level exists**: the object is correctly checked
  for "is this your order", but a specific FIELD (`internal_discount_code`) is editable by any
  object owner when it should be staff-only.
- **GraphQL selection set walk**: `query { me { id email ...AllFieldsFragment } }` — add fields from
  another type/introspection into the query that are not shown in the default UI query.
- **Array/list response leak**: `/api/users?fields=*`, or the complete absence of a `fields`
  parameter — compare the narrow default response (for a list) with the detailed one (for a single
  item); sometimes the list endpoint mistakenly uses the same serializer as the single-item
  admin view.

## Detection Signal

- The raw JSON contains a field that is not in the UI and not in the public OpenAPI schema — already
  a signal of excessive exposure, even without a write.
- A PATCH/PUT with an added non-public field returns 200 AND a follow-up GET shows the changed field
  value (not just an echo of the request — a real write).
- A different serializer/response shape for the same object type on different routes (the admin
  route is richer, but the user route mistakenly reuses the same serializer).

## Anti-FP

- A field is present in the response but identical for everyone (a constant/static config) — not
  sensitive; do not submit it as a finding without impact.
- A read-only field is accepted by the server in the request body but actually IGNORED (no effect on
  a follow-up GET) — not a bug; the ORM is simply not strict about unknown keys.
- Cross-check the project tests/CHANGELOG — sometimes an extra field in the response is left in
  deliberately for backward compat with an internal client (documented as deprecated-but-intentional).
