# Mass Assignment — payload reference

> API6:2019 / part of API3:2023 in OWASP. Unlike `bopla.md` (broad property-level authorization,
> including over-fetch on READ), this one has a narrow focus: privileged fields sneaked in through a
> create/update body that business logic should not accept DIRECTLY from the client. Cross-ref:
> `invariant_library.md` → `## § Web2` → `authz`.

## Payloads

- **`is_admin`/`role`/`is_staff` in a registration/create body**:
  `POST /api/users {"email":"x@x.com","password":"...","is_admin":true}` — at new-account
  registration.
- **`role` as a string instead of an enum guard**: `"role":"ADMIN"`, `"role":"admin"`,
  `"role":"superuser"`, `"role":["user","admin"]` (an array instead of a string — sometimes bypasses
  an `==` comparison).
- **`balance`/`credit`/`points` in a profile update**: `PATCH /api/users/me {"balance":999999}` — a
  direct change to a money/balance field through a generic update endpoint.
- **`price`/`discount`/`total` in order-create**: `POST /api/orders {"item_id":1,"price":0.01}` —
  the client sets the price instead of the server computing it from `item_id` on its side.
- **`verified`/`email_confirmed`/`kyc_status` bypass**: bypass email/KYC verification by setting the
  status field directly on update.
- **`organization_id`/`tenant_id` override**: swap the object's tenant binding at creation — the
  object is created in ANOTHER tenant/organization.
- **`user_id`/`owner_id` override to create someone else's object**: `POST /api/comments
  {"post_id":1,"user_id":<other_user>}` — a comment/object is created ON BEHALF of another user.
- **Array of nested objects with a privileged field**: `{"items":[{"id":1,"price":0}]}` — bulk
  create/update more often skips the per-item field-level validation that the single-item route has.
- **Snake_case/camelCase field duplication**: if the backend validates `isAdmin` but the
  ORM/serializer accepts `is_admin` (or vice versa) — a naming inconsistency between the validation
  and the persistence layer.
- **JSON key case/unicode variation**: `IS_ADMIN`, `Is_Admin`, `is_admin` — when validation is
  strict on the key name but deserialization is case-insensitive / unicode-normalizes the key.

## Detection Signal

- A follow-up GET after create/update shows the changed privileged field, different from the default
  / from what the server should compute.
- 201/200 with no error on a body with an added unexpected field — already a signal that the
  DTO/serializer is not strict about unknown keys (even before confirming a REAL effect — but impact
  is only proven by a re-read).
- Compare the behavior of an explicit-allowlist DTO (Pydantic/serializer with `fields = [...]`) vs a
  generic `model.objects.create(**request.data)` pattern in the discovered source (if available) —
  a direct indicator of the vulnerable pattern.

## Anti-FP

- A field is accepted in the body but the persistence layer explicitly ignores it (an
  ORM/serializer whitelist) — not a bug; confirm the effect with a re-read, not merely with the
  absence of an error in the request response.
- A `role`/`is_admin` field that is written but NOT used anywhere in authz checks (a dead/legacy
  field) — impact is reduced; not de minimis, but flag it honestly.
- An endpoint explicitly documented as admin-only with SERVER-side authorization BEFORE the body is
  processed (401/403 for a non-admin BEFORE the body is even parsed) — then it is not
  mass-assignment, it is a separate BFLA question (see `bfla.md`); do not conflate the classes in the
  report.
