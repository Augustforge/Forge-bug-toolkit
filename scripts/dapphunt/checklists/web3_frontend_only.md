# Web3 frontend-only surfaces — checklist

These surfaces don't exist in pure web2 hunts; they're dApp-specific.

## Service Worker hijack

- [ ] Is there a `sw.js` / `service-worker.js` at root?
- [ ] What's its scope? `/` = controls whole origin
- [ ] Does it cache wallet-connect flow or auth iframe content?
- [ ] If yes: poisoning the SW means the user sees stale/malicious connect UI on next visit
- [ ] Test: open SW DevTools panel, inspect caches

## SRI (Subresource Integrity)

- [ ] Run `core/sri_csp_audit.py --target $DOMAIN`
- [ ] Any cross-origin `<script>` without `integrity="..."` = supply chain risk
- [ ] Especially: TradingView, AntD CDN, Mapbox, custom CDN-hosted SDKs

## CSP completeness

- [ ] `script-src` has `'unsafe-inline'`? — XSS protection weakened
- [ ] `script-src` has `'unsafe-eval'`? — eval permitted
- [ ] `connect-src` has wildcards? — exfil paths via fetch
- [ ] `default-src` set? If absent, missing directives default to allow-all in some browsers

## WalletConnect URI handling

- [ ] dApp accepts `wc:?...` URIs from user input?
- [ ] If user pastes malicious wc: URI, can it cause anything beyond the standard session-handshake?
- [ ] WalletConnect peer metadata fields (`metadata.url`, `metadata.icons[]`) — rendered by dApp without sanitize?

## ENS / SNS spoofing in tx UI

- [ ] dApp resolves ENS name to address before tx?
- [ ] UI displays resolved name in confirmation? But wallet shows actual address?
- [ ] User clicks expecting name X, signs for address Y (look-alike attack)

## TokenList trust

- [ ] Run `core/tokenlist_audit.py --target $DOMAIN`
- [ ] Hardcoded tokenlist URL?
- [ ] Any SRI? (rarely — JSON SRI is uncommon)
- [ ] CDN takeover surface?

## Multi-RPC injection

- [ ] dApp lets user set custom RPC URL?
- [ ] Is there an allowlist of permitted RPC hosts?
- [ ] Fallback chain — if primary RPC down, where does dApp go? Attacker-controlled? 

## Indexer endpoint

- [ ] Run `core/indexer_endpoint_grep.py --target $DOMAIN`
- [ ] Hardcoded subgraph / Goldsky / Allium URL?
- [ ] DNS takeover surface?
- [ ] Sanity-check: does dApp ever verify balances via direct RPC, or 100% indexer trust?

## Analytics PII

- [ ] Sentry / PostHog / GTM payload — wallet address sent?
- [ ] Session replay enabled? — captures private wallet UX including unsigned tx previews

## Open redirect (OAuth / connect_callback)

- [ ] Any `redirect_uri` / `callback` / `return_to` query param?
- [ ] Whitelist enforced or open?
- [ ] Test: `?redirect_uri=https://attacker.com`

## Approval revoke UI

- [ ] Does dApp provide a "Revoke Approvals" view?
- [ ] If absent, this is at least an Insight/Low — user has no in-app way to clean up
- [ ] If present, does it ACTUALLY revoke, or just hide from UI?

## Tx display fidelity

- [ ] Wallet popup shows decoded transaction info, or only raw hex?
- [ ] If raw hex: confirm dApp ABI decoding is offered or user is blind-signing

## AI / LLM in dApp UX

- [ ] Does dApp use an AI to "explain transactions"?
- [ ] Where does the AI get input? Token name? Contract metadata? Order titles?
- [ ] Any of those = attacker-controlled = prompt injection vector
- [ ] Worst-case: AI explains a malicious tx as "safe"; user signs

## Mobile in-app browser

- [ ] Does dApp work in MetaMask Mobile in-app browser?
- [ ] Trust Wallet in-app?
- [ ] Universal links: app-claim conflicts?
- [ ] Test on real device or emulator

## PWA manifest

- [ ] `manifest.json` `start_url` — points where?
- [ ] `scope` — broader than necessary = drives user to attacker context on install

## Stablecoin blocklist UI

- [ ] dApp blocks tokens that are on USDC sanctions list?
- [ ] UI-only block (no on-chain enforcement) = bypass via direct contract call

## Risk engine UI

- [ ] TRM / Halliday / Witnesschain integration shows risk score?
- [ ] Decorative or actually blocks? Test by signing through low-risk vs high-risk

## Token approval simulator gap

- [ ] dApp shows "Estimated outcome: 100 USDC"?
- [ ] Is this from `eth_call` simulation (forward-looking) or hardcoded?
- [ ] Can attacker manipulate the simulation result so estimate ≠ actual?

## Gas estimation display vs reality

- [ ] "Estimated gas: 100k" shown in UI
- [ ] Actual gas burned? Often 100x for nested approve+swap
- [ ] Display vs reality gap

## Permit2 expiry display

- [ ] UI says "Approval expires in 30 days"?
- [ ] Signed payload deadline?
- [ ] Mismatch = user accepts longer permit than they think
