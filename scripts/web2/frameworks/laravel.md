# Laravel — fingerprint→CVE reflex

> Identified Laravel (PHP) → reflex: debug-mode/Ignition + Telescope/Horizon + `.env`/APP_KEY. White-hat:
> read-only. Deserialize-RCE (APP_KEY→forge cookie, Ignition) is described as class + detection, WITHOUT a
> ready phpggc chain. APP_KEY→ATO link: `../../sessions/_methodology/ato_chains.md`.

## Fingerprint

- **Cookies:** `laravel_session`, `XSRF-TOKEN`.
- **Headers:** `X-Powered-By: PHP/…`; `Set-Cookie` with `laravel_session`.
- **Body:** a `csrf-token` meta; on a 404/500 under debug — a Whoops/Ignition error page.
- **Paths:** `/telescope`, `/horizon`, `/_ignition/*`, `/.env`, `/storage/logs/laravel.log`, `/artisan`
  (404-diff via `/vendor/laravel`).

## Known-CVE reflexes

- **Ignition RCE — CVE-2021-3129** (`facade/ignition` `<2.5.2`, Laravel `<8.4.2`; requires `APP_DEBUG=true`).
  - Class: `POST /_ignition/execute-solution` with `MakeViewVariableOptionalSolution` + `php://filter`
    log-poisoning → unauth RCE. Precondition — debug mode + a writable `storage/logs`.
  - Check (non-destructive): 1) `curl "/nonexistent" | grep -i "Whoops\|Ignition\|APP_DEBUG"` — debug on?
    2) `curl "/_ignition/health-check"` — endpoint alive? Do NOT send the RCE solution — it is proven by
    debug-ON + a reachable Ignition on a vulnerable version.
  - Detection Signal: a Whoops/Ignition page visible anonymously + `/_ignition/health-check` responding =
    the CVE precondition. Verify the version (fixed in `2.5.2`).

- **`.env` / APP_KEY exposure → forge session cookie → ATO (the class).**
  - Class: an accessible `/.env` (or `.env.backup`/`.env.local`/`.env.production`) with `APP_KEY` → decrypt
    all Laravel encrypted cookies → forge session → ATO of any user. (2024-2025: mass exploitation of leaked
    APP_KEYs.)
  - Check: `curl "/.env" | grep -iE "APP_KEY|DB_PASSWORD|SECRET"`; also `/.env.backup`, `/.env.save`.
  - Detection Signal: `APP_KEY=base64:…` + `DB_PASSWORD`/API keys in cleartext. Prove the forged cookie by
    retrieving another user's profile (not merely by knowing the key).

- **Laravel cookie / `X-XSRF-TOKEN` deserialization (the class, gated on APP_KEY).**
  - Class: with a known APP_KEY — forge an encrypted cookie with a serialized payload → phpggc gadget chain
    (`Laravel/RCE*`) → RCE. The precondition is strictly a leaked/predictable APP_KEY.
  - Check: confirm an APP_KEY is present (above) — without it the class is dead. Do not build a weaponized chain.
  - Detection Signal: APP_KEY known AND a test-cookie decrypt succeeds = the RCE precondition.

- **Telescope dashboard — `/telescope` (the class, unauth access).**
  - Class: `TelescopeServiceProvider` gates on `local` env by default; in production it is often open →
    full request/response logs, DB queries, Redis commands, env.
  - Check: `curl "/telescope/api/requests"`, `/telescope/api/environment`, `/telescope/api/redis` → JSON?
  - Detection Signal: JSON with DB queries/tokens/env = High (credential/PII theft).

- **Horizon dashboard — `/horizon` (the class, unauth access).**
  - Class: a queue dashboard; `/horizon/api/jobs/failed` — failed-job payloads often carry auth tokens/PII.
  - Check: `curl "/horizon/api/stats"`, `/horizon/api/jobs/failed`.
  - Detection Signal: failed-job payloads with tokens/request data = High.

- **Mass-assignment via Eloquent (the class).**
  - Class: `$guarded=[]` / a sloppy `$fillable` → extra fields (`is_admin`, `role`, `verified`) pass into
    update/create.
  - Check: `POST /api/profile {"name":"x","is_admin":true,"role":"admin"}` from your own session.
  - Detection Signal: `is_admin:true` accepted and the account becomes admin = Critical priv-esc.

- **Signed-URL manipulation (the class).**
  - Class: `URL::signedRoute` does not validate every parameter → change a non-signed param without re-signing.
  - Check: on a `?…&signature=SIG`, change `user=123`→`999` / add `&extra=…` / drop the signature.
  - Detection Signal: a changed parameter accepted with a valid/absent signature = an unauthorized action.
