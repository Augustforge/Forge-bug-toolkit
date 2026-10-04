# Auth provider wildcards — checklist

For each detected auth provider (Privy / Magic / Web3Auth / Dynamic / ThirdWeb /
AppKit / Reown / WalletConnect), pull the publicly readable config and tick
off each item.

## 1. Allowed-domains review

- [ ] List **every** entry in `allowed_domains` / `allowedDomains` / `trustedDomains`
- [ ] For each: is it a wildcard (`*.domain.tld`)?
- [ ] If wildcard: enumerate every existing subdomain via crt.sh
- [ ] For each existing subdomain: does it lack X-Frame-Options + CSP frame-ancestors?
- [ ] If yes → clickjacking primitive with auth trust composition

## 2. Frame-ancestors review (auth iframe's own CSP)

- [ ] Fetch the auth provider's iframe URL directly (e.g. https://auth.privy.io/)
- [ ] Read its `Content-Security-Policy: frame-ancestors ...` header
- [ ] List every host pattern allowed
- [ ] Wildcards here = trust-expansion at the auth-provider level (not just dApp level)

## 3. OAuth redirect_uri review

- [ ] List every OAuth provider configured
- [ ] For each: what's the configured redirect_uri?
- [ ] Wildcard or open-redirect? Token-leak primitive if yes

## 4. Embedded vs External wallet distinction

- [ ] Privy / Magic / Web3Auth = embedded (server-side key custody)
- [ ] WalletConnect / AppKit / Reown / direct injection = external (user wallet)
- [ ] For embedded: server compromise = mass wallet compromise
- [ ] For external: phishing-via-trusted-domain compromise (SynFutures pattern)

## 5. Cross-chain support

- [ ] Privy / Magic / Web3Auth support EVM + Solana + Cosmos
- [ ] Does the same app ID grant identical trust across chains? Test by signing on different chain selections.

## 6. App ID exposure

- [ ] Is the app/project ID public (in bundle)? Yes, basically always.
- [ ] Can attacker query the provider's public config endpoint? See `auth_provider_probe.py` for canonical endpoints.

## Severity calibration

- **Critical**: wildcard + DNS-takeover-ready subdomain under wildcard
- **High**: wildcard + existing public clone without framing protection (SynFutures pattern)
- **Medium**: wildcard but no immediate composability with framing or DNS issue
- **Low**: pure config hygiene (wildcard without obvious composition surface)

Reference threat models:
- `threat_models/auth_provider_wildcard.yaml`
- `threat_models/iframe_trust_composition.yaml`
- `threat_models/dns_takeover_under_wildcard.yaml`
