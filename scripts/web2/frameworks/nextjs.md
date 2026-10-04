# Next.js — fingerprint→CVE reflex

> Identified Next.js → reflexively run these CVE checks. White-hat: read-only fingerprint + a non-destructive
> probe. Confirm SSRF/bypass via OOB (a unique Collaborator subdomain), not by the status code.
> ATO links: `../../sessions/_methodology/ato_chains.md` (Path 4 JWT, `/_next/data` IDOR).

## Fingerprint

- **Headers:** `x-nextjs-*` (`x-nextjs-cache`, `x-nextjs-prerender`), `x-powered-by: Next.js`.
- **Body:** `<script id="__NEXT_DATA__">` in the HTML; `"buildId":"…"` (extract it for `/_next/data/` paths).
- **Paths:** `/_next/static/chunks/…` (JS bundles), `/_next/image?url=…`, `/_next/data/<buildId>/*.json`,
  `/__nextjs_original-stack-frame` (only under `next dev`).
- **Version:** `/_next/static/chunks/framework*.js` → grep `"next":"…"`; `.js.map` (source-map exposure).

## Known-CVE reflexes

- **CVE-2025-29927 — middleware auth-bypass via `x-middleware-subrequest`** (fixed 14.2.25 / 15.2.3;
  vulnerable `>=11.1.4 <12.3.5`, `<13.5.9`, `<14.2.25`, `<15.2.3`).
  - Class: middleware (auth/redirect in `middleware.ts`) is skipped entirely if the request carries the
    internal marker `x-middleware-subrequest`. Bypasses any auth gate implemented in middleware.
  - Check: `curl -s -o /dev/null -w "%{http_code}" -H "x-middleware-subrequest: middleware" <protected-route>`
    → compare with the status without the header. The multi-segment variant:
    `x-middleware-subrequest: middleware:middleware:middleware:middleware:middleware`.
  - Detection Signal: a protected route returns 200 with the header vs 307/401/403 without it = middleware bypassed.

- **CVE-2024-34351 — SSRF in Server Actions (a relative redirect trusts `Host`)** (13.4.0 – <14.1.1,
  fixed 14.1.1; NOT `/_next/image`, NOT Host-routed providers like Vercel).
  - Class: a Server Action that does a relative redirect builds the absolute URL from the request `Host` →
    a server-side fetch to the attacker Host.
  - Check: invoke the Server Action (header `Next-Action: <id>`) with a spoofed `Host: <collab>` →
    watch for the callback.
  - Detection Signal: an OOB DNS/HTTP hit on the Collaborator from a host-controlled request.

- **`/_next/image` SSRF (the class, allowlist-gated — NOT an auto-CVE).**
  - Class: the image optimizer fetches `?url=` only per `images.remotePatterns`/`domains`. Non-whitelisted →
    **400 by default** (a normal reject, not "a block you bypassed"). A 200 returns the OPTIMIZED image, not
    the upstream body — the status alone does NOT confirm SSRF.
  - Check: `?url=<collab>/nextjs-ssrf&w=64&q=75` → OOB; or a body-diff of an internal vs external target.
  - Detection Signal: an OOB callback on a unique subdomain. Without it — do not report.

- **Middleware bypass via path normalization / `/_next/data` IDOR (the class).**
  - Class: the middleware matcher excludes `/_next/static` → protected data is reachable via
    `/_next/data/<buildId>/<page>.json` or an encoded traversal (`..%2Fadmin%2Fusers.json`).
  - Check: `curl "/_next/data/$BUILD_ID/admin/dashboard.json"` without an auth cookie; enumerate
    `/_next/data/$BUILD_ID/users/<id>.json`.
  - Detection Signal: another user's server-side props/PII in the JSON without a session = auth-bypass / IDOR.

- **`__NEXT_DATA__` / `NEXT_PUBLIC_*` env-leak (info disclosure).**
  - Class: SSR props or baked env variables in the HTML/bundle contain non-public secrets.
  - Check: parse `<script id="__NEXT_DATA__">` → `props`; grep the bundle for `NEXT_PUBLIC_[A-Z_]+`.
  - Detection Signal: an API key / token / third-party PII in props → severity by sensitivity (usually
    Low-Medium, High with live creds).

- **`__nextjs_*` dev-endpoints (rare misconfig, `next dev` in production).**
  - Class: `__nextjs_original-stack-frame` / `__nextjs_launch-editor` — the react-dev-overlay, ONLY under
    `next dev`. A prod build → 404 (normal).
  - Check: `curl -o /dev/null -w "%{http_code}" "/__nextjs_original-stack-frame?isServer=true&errorMessage=test"`.
  - Detection Signal: any non-404 = a dev server in production (a file-read surface). 404 = NOT a finding.
