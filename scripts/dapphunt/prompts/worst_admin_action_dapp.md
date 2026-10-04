# Worst-admin-action prompt — dApp frontend edition

The threat model: an authorized actor inside the dApp's trust chain does
something subtly malicious. Not the obvious "rug everything" — the kind of
action that an oncall engineer might do at 3am to "fix something fast" and
that opens a window for outside attackers.

> Assume the dApp's **auth provider admin** is fully compromised (Privy /
> Magic / Web3Auth dashboard takeover). What is the worst single config
> change they can push that you, as an outside attacker, can exploit
> immediately?

Walk through these scenarios for the target dApp:

## 1. Allowed-domains expansion

- Auth provider admin adds a wildcard `*.iftl.info` to `allowed_domains`.
- Any subdomain (existing or future) under iftl.info now inherits production
  trust.
- If outside attacker can register / takeover any subdomain under iftl.info,
  they get an instant phishing primitive that the dApp's own users see as
  legitimate (their Privy modal renders normally on attacker's clone).
- **Outside attack window**: minutes to hours after admin push, before
  noticed.

## 2. OAuth provider list expansion

- Admin adds a new OAuth provider (e.g. attacker-controlled OIDC IDP).
- Anyone who logs in via that provider gets a Privy-issued embedded wallet
  bound to the attacker's IDP user.
- Outside attacker creates accounts at the malicious IDP, then signs in via
  Privy, and ends up with embedded wallets the attacker controls — including
  ability to interact with the dApp under those user identities.

## 3. Redirect URI broadening

- Admin sets `redirect_uri` to `*` or a permissive wildcard.
- Any OAuth flow can now exfiltrate tokens to attacker URL.

## 4. Iframe permissions broadening

- Admin loosens auth iframe's `frame-ancestors` CSP from explicit list to
  wildcard.
- Attacker frames the auth modal from `attacker.com` and renders it normally.
- Combined with social engineering, full wallet authorization is possible.

## 5. Indexer / subgraph endpoint swap

- Admin (or anyone with deploy access to the dApp's frontend) changes the
  indexer URL in the bundle from `gold.synfutures.com` to
  `gold-attacker.com`.
- All user clients now read fake balances/positions from attacker indexer.
- Indirectly drives users into bad on-chain decisions.

## 6. RPC URL swap

- Same as indexer swap but for read-only RPC. dApp shows fake balances,
  prices, allowances. Cascade effect on user actions.

## 7. Production deployment to dev clone

- Admin "accidentally" deploys a dev branch with relaxed checks to a public
  staging URL that inherits production trust via auth provider wildcard.
- This is the **SynFutures pattern** — production hardened, dev clone not,
  trust shared via wildcard.

## Output

For each scenario, document:

```markdown
## <scenario>
- **Admin action that enables this**: <one sentence>
- **What outside attacker does next**: <one sentence>
- **Attack window**: <minutes / hours / days>
- **Detectable from outside**: yes / no
- **Defense**: <what should prevent the admin from being able to do this
  without review>
```

The point is to surface findings that exist **right now** as a result of
admin actions already taken (e.g. wildcards already configured). The
"compromised admin" framing is just a lens — the existing configuration
either provides this expansion surface or it doesn't.
