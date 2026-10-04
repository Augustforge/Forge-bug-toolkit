# Django — fingerprint→CVE reflex

> Identified Django (Python) → reflex: debug/SECRET_KEY + DRF-permission-gaps + ORM-injection CVE.
> White-hat: read-only; admin-brute is noisy and logged — do not run it on production. SECRET_KEY→signed-cookie
> forge is described as class + detection. ATO link: `../../sessions/_methodology/ato_chains.md`.

## Fingerprint

- **Cookies:** `csrftoken`, `sessionid`.
- **Body:** `csrfmiddlewaretoken` in forms; a DRF browsable-API HTML; `__debug__` (django-debug-toolbar).
- **Paths:** `/admin/login/`, `/django-admin/`, `/static/admin/`, `/api/` (DRF), `/__debug__/`.
- **Errors:** under `DEBUG=True` — the yellow Django traceback page with settings/frames.

## Known-CVE reflexes

- **`DEBUG=True` in production → SECRET_KEY / settings leak (the class — crown jewel, not a CVE).**
  - Class: the debug traceback reveals settings (partially SECRET_KEY, DB creds, installed apps, env). A
    leaked `SECRET_KEY` → forge any signed values (session with a signed-cookie backend, a password-reset
    token, `TimestampSigner`) → ATO.
  - Check: trigger a 500/404 on a non-existent path / a malformed parameter type → the yellow traceback page?
    grep for `SECRET_KEY`, `PASSWORD`, `settings`.
  - Detection Signal: a Django traceback with settings frames visible anonymously = High→Critical (if
    SECRET_KEY is recoverable → prove the forged cookie with another session).

- **QuerySet ORM SQLi — CVE-2021-35042** (`order_by` via user input, Django `<3.1.13`, `<3.2.5`).
  - Class: `QuerySet.order_by()` with unchecked user input → SQLi via a column alias.
  - Check: `?order=name'` / `?ordering=-id);--` on list endpoints → a SQL error/anomaly.
  - Detection Signal: a DB error or a boolean/time diff = injection. Verify the version.

- **`Trunc`/`Extract` timezone SQLi — CVE-2022-34265** (Django `<3.2.14`, `<4.0.6`).
  - Class: `Trunc(kind=…)` / `Extract(lookup_name=…)` with a user-controlled `kind`/`lookup` → SQLi.
  - Check: endpoints with date aggregation/grouping where the period/kind comes from the query.
  - Detection Signal: a DB error on injection into `kind`/`lookup_name`. `[verify CVE#]` for the exact range.

- **`QuerySet.values()`/JSONField key SQLi — CVE-2024-42005** (`<4.2.15`, `<5.0.8`, `<5.1`).
  - Class: `values()`/`values_list()` with an unchecked key on a JSONField → column-alias injection.
  - Check: endpoints where a field name / JSON key comes from user input.
  - Detection Signal: a DB error/anomaly on injection into the field name. `[verify CVE#]` for the range.

- **DRF permission-class gaps (the class — the most common, not a CVE).**
  - Class: list vs retrieve vs a custom `@action` — each has its own permission; `@action` often lacks
    `permission_classes`; `AllowAny` is inherited; `/api/users/me/` without auth.
  - Check: `GET /api/users/`, `/api/users/1/`, `/api/users/me/`; enumerate `@action` names
    (`export`,`import`,`bulk`,`reset-password`,`send-invite`) across all methods.
  - Detection Signal: restricted data without a token / a write action without auth. FP-guard: `AllowAny` may
    be by design — check whether the endpoint is intentionally public.

- **Raw-ORM injection (the class) — `raw()` / `extra()` / `cursor.execute`.**
  - Class: `.raw(sql)`, `.extra(where=…)`, `RawSQL`, `cursor.execute(f"… {var}")` with user input → SQLi.
  - Check: `?q=' UNION SELECT …--`, `?category=1' OR '1'='1` on search/filter endpoints.
  - Detection Signal: UNION data / a boolean-blind diff. Cross-ref `payloads/` sqli.

- **Template injection — `mark_safe`/`|safe` + pickle-session (the class).**
  - Class: Django auto-escapes by default → XSS only via an explicit `mark_safe`/`|safe` sink; a session with
    `PickleSerializer` + a known SECRET_KEY → deserialize-RCE.
  - Check: `?message=<script>…` where output is not escaped; check the session backend/serializer.
  - Detection Signal: JS executes (a mark_safe sink), or a pickle-session + a leaked SECRET_KEY =
    the RCE precondition (do not build a weaponized pickle).

- **Django admin exposure / weak creds (the class).**
  - Class: `/admin/` reachable + default/weak creds → full access. Brute is noisy.
  - Check: `curl "/admin/"`, `/django-admin/`, `/administrator/` — reachable?
  - Detection Signal: a reachable admin login = a surface; creds-brute ONLY with caution on production.
