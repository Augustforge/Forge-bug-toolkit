# Multi-clone asymmetry prompt

This is the SynFutures-pattern hunting prompt. Apply when crt.sh enumeration
reveals 5+ subdomains under the target's apex, especially mixed
production/development naming (e.g. `sfdev-v3`, `sfpre-v3`, `appchain-dev`).

> **Hypothesis seed**: "Production is hardened, but a sibling clone serves
> the same bundle without protection."

## Steps

### 1. Catalog all live subdomains

For each subdomain from crt.sh:
- `curl -I https://<sub>/` — record status, security headers
- `curl -s https://<sub>/ | head -2000` — bundle URL pattern, dApp banner

### 2. Group by bundle identity

Hosts ship the same dApp if:
- Same auth provider app ID (Privy `clz...`, WalletConnect projectId)
- Bundle filename pattern matches (`assets/index-*.js`, `static/js/main.*.js`)
- HTML head structure matches (`<title>` text, `<meta name="description">`)

Build a table:

| Host | Status | XFO | CSP frame-ancestors | Privy app | WC project | Bundle pattern | React banner |
|---|---|---|---|---|---|---|---|

### 3. Spot the asymmetry

For each group, compare hardening. Outliers within a group = candidates.

Example (SynFutures):

| Host | Status | XFO | frame-ancestors | Privy app | Bundle |
|---|---|---|---|---|---|
| oyster.synfutures.com | 200 | DENY | 'none' | clz2gl5r... | index-*.js |
| sfdev-v3.iftl.info | 200 | (absent) | (absent) | clz2gl5r... | index-*.js |
| sfpre-v3.iftl.info | 200 | (absent) | (absent) | clz2gl5r... | index-*.js |

→ Production hardened, two clones share auth and bundle but lack headers.
→ Clickjacking primitive on each clone, ridden via shared auth trust.

### 4. Hypothesis candidate

For each unhardened clone within a group:

```markdown
## H_<host>: Clone <host> serves same dApp as <primary> without framing protection
- **Bundle equivalence**: <evidence>
- **Auth shared**: <Privy app ID or WC project ID>
- **Headers missing on clone**: <list>
- **Composition**: attacker frames <host>, drives clicks through to Privy
  modal, which trusts <host> via wildcard / explicit allow → wallet
  authorization on production's behalf.
- **Severity estimate**: High (HackenProof rubric — user-click + significant
  fund loss).
- **Verification**: 5-minute PoC — HTML with `<iframe src="<host>">`,
  observe load + Connect Wallet flow.
```

### 5. Verify the trust composition

This is what makes it High instead of Low informational:
- Pull the auth provider's `allowed_domains` and `frame-ancestors`.
- Confirm the clone host (or its parent wildcard) is in the allowlist.
- If yes → composition confirmed.

### 6. Sibling search

Once you have one hardening asymmetry, check:
- Other clones in the same group — same finding likely.
- Other dev clones outside this group's auth chain (might be in a different
  group with different findings).
- Subdomains in the wildcard policy that don't currently exist — these are
  the "future expansion" surface for DNS-takeover.

## Phase gate

Don't proceed past this prompt without ≥1 group containing both a hardened
production host AND ≥1 unhardened clone sharing the same auth. If you don't
have that, the trust composition primitive doesn't exist on this target.
