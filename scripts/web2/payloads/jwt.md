# JWT — payload reference

> Classic breaks of the JWT verify path. Cross-ref: `invariant_library.md` → `## § Web2` → the row
> `JWT verify` (verify with the alg from config + the secret — the anti-fingerprint is precisely
> `alg:none` / verify off / alg taken from the header).

## Payloads

- **`alg: none`**: rewrite the header to `{"alg":"none","typ":"JWT"}`, drop the signature (leave a trailing
  `.`), check whether the verify path accepts a token with no signature. Capitalization variants: `none`,
  `None`, `NONE`, `nOnE` (some parsers are case-insensitive to alg).
  - Detection Signal: the server accepts a modified payload (e.g. `{"role":"admin"}`) without a 401.
- **alg-confusion RS256→HS256**: if the server verifies RS256 with a public key but the verify function takes
  the alg from the header — set `alg:HS256` and sign the token with HMAC using the RSA PUBLIC key (usually
  available: `/jwks.json`, `.well-known/jwks.json`, or a cert from TLS/another public endpoint) as the HMAC
  secret.
  - Detection Signal: a signed HS256 token with an arbitrary payload is accepted as valid.
- **`kid`-injection (path traversal)**: if verify fetches the key by the `kid` from the header, set
  `kid: "../../../../dev/null"` (an empty key → HMAC with an empty string) or a `kid` pointing at a
  predictable file/env variable.
- **`kid`-injection (SQL/command)**: `kid` as a SQLi injection, if the key is read by a direct query
  `SELECT key FROM keys WHERE id = '<kid>'`.
- **`jku`/`x5u` header injection**: set `jku` (the JWK Set URL) to YOUR server serving the attacker's public
  key — if verify blindly fetches the key by `jku` without a host allowlist, sign the token with your private key.
- **Weak/predictable secret (HS256 brute-force)**: build a wordlist (project name, `secret`, `changeme`,
  popular-framework defaults) → offline brute-force of the signature (`hashcat -m 16500` / `jwt_tool`).
- **Signature stripping + accept**: drop the signature entirely, leave header.payload — some custom
  (non-library) verify implementations split on `.` and do not check the array length.
- **Expired-token replay without an exp check**: remove the `exp` claim entirely or set it far in the past —
  if verify does not require `exp` as a mandatory field, the token can stay valid forever.
- **Claim tampering without re-sign (if verify is actually broken by one of the above)**: once one vector
  works — alter `sub`/`role`/`user_id`/`org_id`/`is_admin` in the payload.
- **A token from one context in another (audience confusion)**: a JWT issued for service A (`aud: "service-a"`)
  accepted by service B without checking `aud`.

## Detection Signal

- A modified token (not re-computed with the HMAC secret, but via one of the vectors above) passes verify and
  the endpoint returns data/an effect matching the forged claim.
- `jwks.json`/`.well-known/jwks.json` is publicly accessible — not a bug on its own, but a prerequisite for
  alg-confusion (needed as a source of the public RSA key).
- The response to `alg:none` — 401/403 = good (guard); 200 = a finding.

## Anti-FP

- Confirm the endpoint actually USES the claim from the token in business logic (not just logs it) — a verify
  bypass without a reachable privileged effect = lower severity, not de-minimis, but clearly separate "verify
  is broken" from "verify is broken AND it affects something".
- Library (not hand-rolled) JWT implementations require whitelisting `algorithms: [...]` in the verify call by
  default — if the server uses such a library correctly (passes an explicit allowlist), alg-confusion is
  impossible regardless of the `alg` in the header — check the verify call in the code/behavior, do not assume
  the vulnerability from the mere presence of RS256.
- `kid`-injection requires confirming a REAL effect (the empty key/traversal worked), not just the presence of
  a `kid` header.
