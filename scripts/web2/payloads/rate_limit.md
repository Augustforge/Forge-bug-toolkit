# Rate Limit Bypass — payload reference

> Partly API4:2023 (Unrestricted Resource Consumption), plus the classic brute-force enabler.
> A rate-limit bypass is rarely Critical on its own — the severity comes from WHAT it unlocks (OTP
> brute-force, password brute-force, credential stuffing, coupon/promo brute-force). Cross-ref:
> `invariant_library.md` → `## § Web2` (overlaps with the `session`/`authz` rows).

## Payloads

- **Header spoofing (IP-based rate limit)**: if the limit is counted by IP and the IP is taken from a header
  (not directly from the TCP connection, e.g. behind a reverse proxy/CDN) — change it on every request:
  `X-Forwarded-For`, `X-Real-IP`, `X-Originating-IP`, `X-Remote-IP`, `X-Remote-Addr`,
  `X-Client-IP`, `True-Client-IP`, `CF-Connecting-IP`, `Forwarded: for=...`.
- **Multiple values in one header**: `X-Forwarded-For: 1.1.1.1, 2.2.2.2, 3.3.3.3` — differing parsing
  (first/last/random value) may bypass a limit counted on a different list element than the proxy actually
  uses for forwarding.
- **Race condition (parallel request burst)**: send N simultaneous (not sequential!) requests BEFORE the
  counter can increment — a TOCTOU in the limiter implementation (read-counter → check → increment are not
  atomic). Tool: Burp Turbo Intruder's race-condition template / a `race the web`-style single-packet attack.
- **Endpoint/path variation hitting one resource**: `/api/login`, `/api/login/`, `/API/LOGIN`,
  `/api//login`, `/api/./login`, `/api/v1/login` vs `/api/v2/login` (aliases of one handler) — if the limit
  is counted by the exact path string rather than by the resolved route.
- **Case variation in the account identifier (username casing)**: `user@x.com` vs `User@X.com` vs
  `USER@X.COM` — if the per-account limit keys on the exact string while the email comparison is
  case-insensitive at authentication.
- **Trailing/leading whitespace or a unicode look-alike in the identifier**: `user@x.com` vs `user@x.com `
  (trailing space) vs `usеr@x.com` (a Cyrillic `е` instead of the Latin one) — if both variants lead to the
  same account at authentication but the limit counts them as DIFFERENT keys.
- **Session/cookie churn**: if the limit is tied to the session ID/cookie rather than the account/IP —
  resetting the cookie (logout+login, or just a new session-init request) between attempts resets the counter.
- **CAPTCHA/2FA only on the N+1 attempt without real enforcement**: check whether the CAPTCHA token is
  actually VALIDATED by the server, or the endpoint merely requires the PRESENCE of a `captcha_token` field
  without checking its correctness.
- **An alternative endpoint with the same effect but no limit**: if `/api/login` is limited but
  `/api/v1/mobile/login` or the GraphQL `mutation login(...)` (the same business effect) is not.

## Detection Signal

- N successful attempts (N > the stated/observed limit) without a 429/block when varying ONE of the vectors
  above, while the baseline (no variation, repeated identical requests) returns a 429 on the N-th attempt —
  the direct comparison proves the bypass, not just "I didn't see a limit".
- Race condition: the end effect (e.g. the number of successful redemptions of a one-time code) is GREATER
  than 1 under parallel submission — a measurable business impact, not just the absence of a 429.

## Anti-FP

- The absence of a visible rate-limit on a NON-sensitive endpoint (public read-only content) is not a finding
  on its own; a rate-limit matters as a security control precisely on authn/brute-forceable operations
  (login, OTP verify, password reset, coupon redeem) — tie the finding to a CONCRETE chainable impact.
- A WAF/CDN may limit at ITS level (invisible to a direct test, but actually working under a sustained attack)
  — a baseline test is mandatory BEFORE claiming a bypass (do not rely on "I didn't get a 429 in 20 requests",
  the threshold may just be higher).
- A race-condition bypass yielding literally 2 successful hits instead of 1 (off-by-one) against a
  high-latency target network is not always stably reproducible — note it honestly if the success rate is low.
