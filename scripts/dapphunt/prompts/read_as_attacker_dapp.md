# Read-as-attacker prompt — dApp frontend edition

Apply this prompt to the main JS bundle of the target dApp.

> You're sitting at `attacker.com`. You can ship any HTML/JS/CSS to a victim,
> and you can register subdomains, deploy contracts, host CDN assets, register
> wallets in extensions. You CANNOT compromise the victim's wallet or the
> dApp's backend directly — but you can frame the dApp, postMessage into it,
> serve fake API responses if you control a relevant DNS record, run a wallet
> extension, or get the victim to click a single link.
>
> **What assumptions does this dApp make that I can break?**

Walk through these question loops while reading the bundle:

## 1. Origin trust assumptions

- Where does the dApp call `window.parent` or accept `postMessage`?
- What does it do with `event.origin`? Substring vs strict equality?
- Which iframes does it embed? What origins does it call via fetch?
- Does it trust the `wallet.peer.metadata.url` field that the user's wallet
  reports? If so, can I as a malicious wallet extension set that URL to a
  payload?

## 2. Wallet integration assumptions

- Does the dApp assume `window.ethereum` is MetaMask? If multiple extensions
  injected, which one wins?
- Is the EIP-712 `domain.chainId` set to a constant or read dynamically from
  the connected wallet? If constant on a multi-chain dApp, a signature is
  replayable across chains.
- Does EIP-712 `domain.verifyingContract` match what the dApp actually calls?
  If hardcoded, switching chains may render the signature valid on a
  different contract.
- For `personal_sign`: what is the canonical message format? Is the dApp
  prefixing with the chain ID + nonce + domain? Or signing free-form text
  that could be replayed?
- Is there an `eth_sign` path anywhere? That's almost always a finding.

## 3. Frontend-server assumptions

- Where are API endpoints hardcoded? Could I DNS-takeover any of those
  hostnames?
- What does the dApp do if the API returns an unexpected shape? Is there
  schema validation, or does it trust whatever JSON comes back?
- Is indexer/subgraph data ever sanity-checked against direct RPC reads?
- Are RPC URLs hardcoded? If so, can attacker influence which RPC the user
  uses (custom RPC setting, fallback chain)?

## 4. UI assumptions

- What does the user see vs what gets signed? (gas, ENS name, decimals,
  slippage, expiry, blocklist, transaction display)
- Where does the UI assert something the contract doesn't enforce? Those
  are display-vs-reality candidates.
- Are there any "soft" gates that the UI applies — Cloudflare geo block,
  KYC popup, terms-of-service modal — that are purely client-side?

## 5. Auth provider assumptions

- What auth provider is in use (Privy / Magic / Web3Auth / Dynamic / AppKit)?
- What does the publicly readable config say? `allowed_domains`,
  `frame-ancestors`, `redirect_uri`, OAuth providers?
- Are wildcards present anywhere in those allowlists? What's the implicit
  trust footprint of each wildcard?
- If the auth provider is embedded-wallet (Privy), what does compromise of
  the provider's iframe mean for the user's wallet?

## 6. Clone assumptions

- Are there dev/staging clones of this dApp on public DNS?
- Do they ship the same bundle? Same auth provider app ID?
- Are they hardened (X-Frame-Options + frame-ancestors)?
- Could I iframe a clone and ride its trust to the production user via
  the shared auth provider?

## Output

For each question that surfaces a non-trivial answer, write:

```markdown
## <surface>: <one-line assumption>
- **Assumption broken**: <what dApp believes>
- **Reality**: <what I can do to violate it>
- **Composition**: <what other surfaces this combines with>
- **Verification**: <how to confirm in 5-15 minutes>
```

Stop at 3-5 promising assumptions. Then run those through the pre-flight
quality check (concrete prediction, falsifier, severity ceiling, cost,
refuted-by-read).
