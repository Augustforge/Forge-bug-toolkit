# dApp clones — detection + exploitation checklist

## What counts as a clone

A "clone" is any public host that ships substantially the same dApp as
production. Often:
- Dev / staging / preprod environments accidentally left public
- Audit / pen-test environments
- Fork or "preview" branches for feature work
- Marketing landing pages that embed the dApp UI

## Detection signals (strong → weak)

1. **Identical Privy / Magic / Web3Auth app ID** (strongest) — shared trust grant
2. **Identical WalletConnect projectId** — shared peer metadata
3. **Identical bundle filename pattern + SHA-256 head hash** — same build artifact
4. **Identical HTML `<title>`** + brand banner string
5. **Same React/Wagmi/Vite version + same auth provider** — likely same product family

Run `core/dapp_clone_detector.py` to surface candidates automatically.

## After detection — exploitation check

For each clone host:

- [ ] Is it accessible publicly (HTTP 200)?
- [ ] Does it ship the same dApp UI? (Open in browser, confirm Connect Wallet works)
- [ ] Is it missing X-Frame-Options / CSP frame-ancestors?
- [ ] Does it share auth trust with production via wildcard? (check `auth_provider_config.json`)
- [ ] Build minimal HTML PoC iframing it + production for comparison

## SynFutures-pattern verification

```bash
# 1. Crt.sh subdomain enum
python3 bug-bounty-toolkit/scripts/crtsh_enum.py --domain iftl.info --output sessions/$DOMAIN/crtsh.json
# 2. Detect clones
python3 bug-bounty-toolkit/scripts/dapphunt/core/dapp_clone_detector.py \
    --primary https://oyster.synfutures.com/ \
    --subdomains sessions/$DOMAIN/crtsh.json \
    --auth-id clz2gl5r702phkqjy3zhlalh9 \
    --output sessions/$DOMAIN/clones.json
# 3. Verify framing posture on each detected clone
python3 bug-bounty-toolkit/scripts/dapphunt/core/iframe_trust_check.py \
    --primary https://oyster.synfutures.com/ \
    --subdomains sessions/$DOMAIN/crtsh.json
```

## When a clone is NOT a finding

- Clone is behind authentication (Authelia / Cloudflare Access / Basic Auth)
- Clone has identical hardening (X-Frame-Options DENY + CSP)
- Clone uses a DIFFERENT auth provider config (no shared trust grant)
- Clone is on a fully-scoped, explicitly-allowlisted subdomain (no wildcard)

## Severity

- **High**: clone exists + missing framing + shared auth via wildcard → wallet phishing chain (SynFutures pattern)
- **Medium**: clone exists + missing framing (no auth chain composability)
- **Low**: clone exists + identical hardening (info disclosure only)
