# NestJS — fingerprint→CVE reflex

> Identified NestJS (TypeScript, on top of Express/Fastify) → reflex: guard-gaps + ValidationPipe +
> serializer-leak + microservice-drift. White-hat: read-only. Almost all findings are class-level
> (architectural gaps in application code), not CVEs. The Node layer (prototype-pollution/SSTI/trust-proxy)
> — see `nodejs.md`.

## Fingerprint

- **Headers:** `X-Powered-By: Express` (Nest on Express by default — Nest itself rarely emits a marker);
  TypeScript-decorator patterns in stack traces.
- **Paths:** `/api`, `/api-json` (Swagger, `@nestjs/swagger`), `/graphql` (`@nestjs/graphql`),
  CRUD conventions `/api/<resource>` + `/api/<resource>/:id`.
- **Errors:** Nest-style `{"statusCode":…,"message":…,"error":…}` JSON.

## Known-CVE reflexes

- **Swagger/OpenAPI exposure — `/api-json` (the class — recon crown, not a CVE).**
  - Class: `@nestjs/swagger` often mounts the docs without auth → the full endpoint map (including hidden ones).
  - Check: `curl "/api-json" | jq '.paths|keys[]'`; `/api`, `/api/docs`, `/swagger`.
  - Detection Signal: undocumented endpoints in the schema = a surface for a guard test.

- **Guard bypass via decorator-stack gaps (the class — the most valuable).**
  - Class: guard resolution is global→controller→method; `@Public()`/`@SkipAuth()` on one method does not
    affect others, but a method-level override / route-param confusion / a metadata-key mismatch
    (`Reflector.get`) → the global guard does not find the metadata → lets it through.
  - Check: all methods (GET/POST/PUT/PATCH/DELETE/OPTIONS) on `/api/admin/users` — do the codes diverge?
    `/api/admin/health`,`/api/admin/config` (may be `@Public`); the param decorator `?userId=VICTIM`.
  - Detection Signal: an endpoint/method that should be protected returns data/mutation without a valid token
    = broken authz. Cross-ref `payloads/bfla.md`, `bola.md`.

- **ValidationPipe exploitation (the class — mass-assignment).**
  - Class: without `whitelist:true` — extra fields (`isAdmin`) pass into the DTO→ORM; `transform:true` —
    coercion (`"true"`→`true`); `skipMissingProperties:true` on PATCH — you update only the one field,
    bypassing validation of the rest.
  - Check: `POST /api/users {"username":"x","isAdmin":true}`; `PATCH /api/users/me {"role":"admin"}`;
    coercion `{"isActive":"true"}`.
  - Detection Signal: an extra/coerced field persists (a role/flag is gained) = priv-esc. Cross-ref
    `payloads/mass_assignment.md`.

- **Serialization leak — ClassSerializerInterceptor absence (the class).**
  - Class: without a global `ClassSerializerInterceptor` the controller returns the WHOLE entity, including
    `@Exclude()` fields (`password`,`passwordHash`,`secretKey`,`internalNotes`).
  - Check: `curl "/api/users/1" | jq 'keys'` → look for password/hash/token/internal.
  - Detection Signal: sensitive fields in JSON = info disclosure (High with a password hash/tokens).

- **class-validator / DTO-coercion bypass (the class).**
  - Class: weak/absent validators on the DTO → type/structure injection (e.g. an object instead of a string
    → NoSQL-operator injection if it reaches a Mongo query).
  - Check: pass `{"$gt":""}`/an array/an object into a field expecting a string; check 422 vs pass-through.
  - Detection Signal: a non-string structure accepted and reaching the query = an injection surface. Cross-ref
    `payloads/` nosqli.

- **Microservice transport auth-drift (the class).**
  - Class: `@MessagePattern` handlers (TCP/Redis/NATS/MQTT/gRPC) without `@UseGuards()` — auth is enforced on
    HTTP but NOT on the transport layer. Usually internal ports.
  - Check (from the target network): TCP `{"pattern":"getUser","data":{"id":1}}` on port 3000;
    `redis-cli PUBLISH`; `grpcurl -plaintext …:5000 list` (reflection).
  - Detection Signal: a microservice handler processes the request without auth while the HTTP equivalent
    requires a JWT = auth-drift.

- **CRUD-generator auto-endpoints (`@nestjsx/crud`) without `@UseGuards()` (the class).**
  - Class: auto-CRUD creates list/get/create/update/delete without explicit authorization.
  - Check: `GET/POST/PATCH/DELETE /api/<resource>[/id]` without a token → 200/204?
  - Detection Signal: write operations (create/update/delete) without auth = Critical (unauth data mutation).
