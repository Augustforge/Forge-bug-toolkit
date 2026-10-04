# Embedded vs External wallet — threat model split

## Embedded wallets

Provider holds the key. User authorizes via email / OAuth / passkey, provider
signs on user's behalf.

Examples: Privy, Magic, Web3Auth, Dynamic (in embedded mode), Reown WUI

## External wallets

User holds the key (extension, hardware, mobile). dApp asks user to sign;
user's wallet decides whether to comply.

Examples: MetaMask, Phantom, Keplr, Ledger via WalletConnect, Trust Wallet

## Threat model comparison

| Attack vector | Embedded | External |
|---|---|---|
| Provider server compromise | **Catastrophic** (mass key access) | None (keys local) |
| Phishing-via-trusted-domain | High (provider modal looks legit) | Medium (wallet still shows hostname) |
| Frontend XSS | High (provider session token reachable) | Lower (wallet popup separate origin) |
| Wallet metadata XSS | High (modal renders metadata) | Medium |
| Cross-chain replay | Same | Same |
| Permit/Permit2 abuse | Same | Same |
| Clickjacking of confirm | High (modal is iframe — frameable if provider allows it) | Lower (extension popup not frameable) |
| Session-replay leak (Sentry) | High (user UX captured) | Medium (wallet popup outside replay) |
| Approve-all primitive | Same | Same |

## Embedded-specific concerns

- [ ] If user reauthorizes (e.g. after refresh), does the dApp prompt for explicit approval each session?
- [ ] Privy: are `embeddedWallet.create` calls visible? Each is silent key generation
- [ ] Magic: passkey export — is it user-controllable?
- [ ] Web3Auth: shares of MPC stored where? Cloud provider compromise?

## External-specific concerns

- [ ] EIP-6963 multi-provider — first-wins vs explicit choice
- [ ] Ledger via WalletConnect: device must be unlocked; user fatigue → blind sign
- [ ] Hardware wallet display fidelity: small screen, hash-only display common

## Verification approach

For embedded:
1. Open dApp, sign in via email/OAuth
2. Inspect Network tab — what does dApp send to provider?
3. Look for session token in headers — where stored client-side?
4. Can session token be exfiltrated via XSS reach?

For external:
1. Connect a burner wallet (`0xA094...1332`)
2. Use mock provider (`eip1193_mock_provider.js`) to observe every request
3. Document EIP-712 domains and personal_sign payloads
4. Test cross-chain replay

## Severity rubric (when both classes are present)

- **Critical**: embedded provider compromise primitive that's available to outside attacker
- **High**: phishing chain that exploits embedded modal's iframe trust (SynFutures pattern)
- **Medium**: cross-chain or display-vs-reality issue affecting both wallet classes equally
- **Low**: hygiene issues specific to one class
