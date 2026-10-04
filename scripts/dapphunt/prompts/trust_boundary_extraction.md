# Trust boundary extraction — dApp frontend edition

Map every trust boundary the dApp depends on. A trust boundary is any
interface where one component delegates judgment to another. Each boundary
has an implicit allowlist (often forgotten) and a default failure mode
(usually permissive).

## The boundaries to map

For the target dApp, fill in this table:

| Boundary | Source | Sink | Allowlist / Trust Grant | Default if Trust Fails |
|---|---|---|---|---|
| Origin (frame) | parent window | dApp window | CSP `frame-ancestors` + `X-Frame-Options` | render anyway (no header = trust) |
| Origin (postMessage) | iframe / popup | dApp event handler | `event.origin === EXPECTED` check | accept (if check missing) |
| Wallet provider | injected extension | dApp's `window.ethereum` user | "first injected wins" or explicit selection | use whatever |
| Wallet signature domain | wallet UI | user | EIP-712 `domain.{name, chainId, verifyingContract}` | sign anyway if user clicks |
| Auth provider session | Privy / Magic | user identity | OAuth provider + email + session token | reject |
| Auth provider iframe | embedded `auth.privy.io` | dApp | provider's `frame-ancestors` policy | reject |
| OAuth callback | external IDP | dApp | `redirect_uri` allowlist | redirect anywhere if wildcard |
| API endpoint | dApp client | backend | hardcoded URL + (sometimes) CORS | trust response shape |
| Indexer / subgraph | dApp client | indexer | hardcoded URL | accept response |
| RPC | dApp client | chain reader | hardcoded RPC URL or chain config | accept response |
| TokenList | dApp client | token registry CDN | hardcoded fetch URL | display whatever |
| Image / icon CDN | dApp client | CDN | hardcoded URL | render whatever |
| Wallet metadata | wallet extension | dApp display | wallet sets `.name`, `.icons` | render whatever |
| TMA initData | Telegram backend | dApp | HMAC over initData with bot token | accept if hash matches |
| Risk engine (TRM / Halliday) | dApp client | risk service | hardcoded URL + flag value | usually decorative — accept |

## How to use this map

For each boundary:

1. **Verify the allowlist exists** at all. Missing = full trust = finding
   candidate.
2. **Check the allowlist format**. Strict equality is safe; substring is
   bypassable; wildcards are trust-expansion.
3. **Check the failure mode**. If the dApp accepts despite missing trust
   grant, that's a finding regardless of the allowlist's correctness.
4. **Check compositions**. The SynFutures pattern is a composition of two
   trust boundaries failing simultaneously (auth wildcard + iframe header
   missing).

## Output

```markdown
## Trust map for <DOMAIN>

| Boundary | Allowlist status | Failure mode | Finding candidate? |
|---|---|---|---|
| ... | strict / wildcard / missing | reject / accept | yes / no / needs verify |

### Composition candidates
- <boundary A> failing + <boundary B> failing = <composed attack>
```

For every "needs verify" or "yes" row, draft a hypothesis with file:line
evidence. Run through pre-flight (concrete, falsifiable, severity ceiling,
cost, refuted-by-read).
