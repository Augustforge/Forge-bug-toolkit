# FastAPI — fingerprint→CVE reflex

> Identified FastAPI (Python/ASGI) → reflex: OpenAPI mining + Depends-authz-gaps + Pydantic-coercion.
> White-hat: read-only. Most findings are class-level (not CVEs): auth-gap/coercion/SSTI live in application
> code, not in the framework.

## Fingerprint

- **Headers:** `server: uvicorn` (or `hypercorn`/`gunicorn` + a uvicorn worker).
- **Paths:** `/openapi.json`, `/docs` (Swagger UI), `/redoc`. `/openapi.json` → `.info.title`.
- **Errors:** a Pydantic 422 with `{"detail":[{"loc":…,"type":…}]}` — the characteristic FastAPI validation.

## Known-CVE reflexes

- **OpenAPI / docs exposure (the class — recon crown, not a CVE).**
  - Class: `/openapi.json` reveals ALL endpoints (including ones hidden from the public docs) + security
    schemes + types. A map for the authz test.
  - Check: `curl "/openapi.json" | jq '.paths | keys[]'`; find the unprotected ones:
    `jq '.paths|to_entries[]|select(.value.get.security==[])|.key'`. If 403 — try `/docs`, `/redoc`
    (same content).
  - Detection Signal: undocumented/internal endpoints in the schema = a surface for Phase 2.

- **Dependency-injection authz-gap (the class — the most valuable).**
  - Class: `Depends(get_current_user)` is declared, but not on every operation; a router-level Depends is
    overridden with `None`; `Security` vs `Depends` confusion; a `BackgroundTasks` path bypasses auth.
  - Check: an endpoint that should require auth, without `Authorization` → 200? All methods
    (GET/POST/PUT/PATCH/DELETE) on `/api/users/1` — do the codes diverge?
  - Detection Signal: an endpoint that should be protected returns data/mutation without a valid token =
    broken authz (BOLA/BFLA). Cross-ref `payloads/bola.md`, `bfla.md`.

- **Pydantic coercion / extra-fields (the class — mass-assignment).**
  - Class: type coercion (`"true"`→`True`, `"1"`→`1`); Pydantic v1 ignores extra, v2 too by default
    (`extra='ignore'`) — but if the model lacks `whitelist`/`Extra.forbid` and the field reaches the ORM →
    mass-assignment.
  - Check: `POST /api/register {"username":"x","is_admin":"true"}`; the extra field `{"role":"admin"}`;
    a content-type switch to `x-www-form-urlencoded` with `is_superuser=true`.
  - Detection Signal: a coerced/extra field persists (the account gains a role/flag) = priv-esc. Cross-ref
    `payloads/mass_assignment.md`.

- **Jinja2 SSTI (the class, gated on template render).**
  - Class: if the response is rendered by Jinja2 with user input in the template (`Template(user_input)`),
    `{{7*7}}` → `49` → RCE via a `{{cycler.__init__.__globals__.os.popen('id')}}`-class gadget.
  - Check: `{{7*7}}`/`${7*7}` in reflected fields → `49`? Confirm RCE via OOB, do not run anything destructive.
  - Detection Signal: `49` in the response = SSTI. Cross-ref `payloads/` ssti.

- **ASGI proxy-trust / TrustedHost bypass (the class).**
  - Class: `--proxy-headers` trusts `X-Forwarded-For`/`X-Real-IP` → spoof the client IP (bypass an
    IP-allowlist/rate-limit); a `TrustedHostMiddleware` misconfig → host injection; a CORS middleware with
    `allow_origins=["*"]`+credentials.
  - Check: `-H "X-Forwarded-For: 127.0.0.1"` on an IP-gated endpoint; `-H "Host: evil.com"` on health;
    `OPTIONS` with `Origin: https://evil.com`.
  - Detection Signal: a spoofed IP accepted (gate bypass); a reflected ACAO with credentials. FP-guard: if the
    server sees your real IP, proxy-headers are off. Cross-ref `payloads/cors.md`.

- **WebSocket / GraphQL-mount authz-parity (the class).**
  - Class: a WS endpoint (`@app.websocket`) or a mounted GraphQL (strawberry/graphene) does not enforce the
    Depends that guards the REST equivalent; mutations work without auth where queries require it.
  - Check: `wscat -c wss://…/ws/notifications` without a token; `POST /graphql` introspection + a mutation
    without auth.
  - Detection Signal: a WS/GraphQL mutation passes without a session while the REST analog requires one =
    auth-drift.

- **python-multipart / Starlette DoS (dependency-CVE, [verify CVE#] range).**
  - Class: `CVE-2024-24762`/`CVE-2024-53981` (python-multipart ReDoS/DoS on malformed multipart),
    `CVE-2024-47874` (Starlette multipart without a size limit → memory DoS). DoS — **not exploited**
    (a forbidden class), only record the version.
  - Check: the `python-multipart`/`starlette` version from the `/openapi.json` stack / error fingerprint.
  - Detection Signal: a vulnerable version = an info report about the version, WITHOUT an active DoS PoC.
