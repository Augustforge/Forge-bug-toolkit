# Legal Posture — White-hat Hunting Framework

Reference document. Read before each hunt.

---

## SafeHarbor Check

Before testing ANY protocol, check if they have a SafeHarbor policy:
- [SEAL Whitehat SafeHarbor](https://github.com/security-alliance/safe-harbor)
- Specific protocol's `SECURITY.md` or `RESPONSIBLE_DISCLOSURE.md`
- Bug bounty program ToS

If SafeHarbor → you're protected for good-faith research.
If no SafeHarbor → restrict to passive recon. Don't execute exploit on production.

---

## Coordinated Disclosure Timeline (default)

For protocols without bug bounty:
1. **T+0**: Notification with technical details + PoC. Use security@protocol.com or established channel.
2. **T+24h**: Acknowledge receipt confirmation expected.
3. **T+7 days**: Follow-up if no response.
4. **T+30 days**: Second follow-up. Escalate to Chainlink security / Trail of Bits if relevant.
5. **T+90 days**: Public disclosure window opens (RFC standard).

Never publicly disclose before fix OR program-approved date.

---

## Authorization Documentation

For every hunt, log to `~/.bbt/audit.log`:
- Target
- Mode (passive/active)
- Tools used
- Authorization source (immunefi:program / hackerone:program / explicit-permission / coordinated-disclosure)
- Result summary

Use `scripts/_audit_log.py` (existing).

---

## What NEVER to Do

- DDoS, phishing, RAT, C2
- Execute exploit on mainnet production
- Touch user funds (even to "save" them — use proper notification)
- Hold zero-day longer than disclosure window allows
- Sell findings to anyone except the protocol team or via approved bounty platform
- Brag publicly before resolution

---

## Sanctions Compliance

- Don't test protocols based in OFAC-sanctioned jurisdictions
- Don't accept bounty payments to addresses involved with Tornado Cash (post-2022 sanctions)
- KYC requirements vary per bounty platform — comply

---

## Jurisdictional Notes

(Reporter is Russian-based — check region-specific risks)

- **EU**: NIS2 directive grants whitehats explicit safe harbor for good-faith research (2024+).
- **US**: CFAA fear largely mitigated by 2022 DOJ policy update — good-faith research not prosecuted.
- **Russia**: No specific safe harbor. Operate under coordinated disclosure principle. International bug bounty platforms cover us if we follow their rules.
- **CN, IR, KP**: Avoid testing protocols from these jurisdictions due to sanctions risk on payouts.

---

## Wallet Hygiene

For each hunt:
- Use isolated wallet (`opsec/wallet_manager.py --new --target X`)
- Never link to KYC'd exchange wallet
- Don't use Tornado Cash (sanctioned)
- Use clean cash-funded onramp if possible (e.g., Coinbase → fresh wallet → testnet faucet)

---

## Bounty Receipt

When payout offered:
1. Confirm sender is official protocol channel
2. Confirm amount matches agreed
3. Use KYC'd wallet ONLY when KYC compliance required by platform (Immunefi)
4. For pseudonymous bounties: use isolated wallet
5. Wait for L1 finality before claiming complete

---

## Report Quality Reduces Legal Risk

A high-quality report:
- States authorization (program X covers this)
- Documents PoC as on fork (not mainnet exploit)
- Names protocol's contact
- Doesn't include reproducer for mass exploitation
- Gives team time to fix

Reduces ambiguity = reduces legal risk.

---

## Quick Pre-Hunt Checklist

- [ ] Target has bug bounty OR SafeHarbor policy?
- [ ] Wallet isolated for this hunt?
- [ ] Pseudonym separated from main handle?
- [ ] Recon via VPN or Tor?
- [ ] Audit log entry created?
- [ ] No mainnet exploitation planned?
- [ ] Coordinated disclosure plan in place?

If any "no" — pause and resolve.
