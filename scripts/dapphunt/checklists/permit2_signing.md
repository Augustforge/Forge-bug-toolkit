# Permit2 / EIP-2612 signing — checklist

Use when dApp requests off-chain approval signatures (no on-chain `approve()` tx).
Permit2 (Uniswap, deployed 2022) and EIP-2612 (DAI-style permit) are now standard
across DeFi. Inferno/Angel drainers industrialized this vector — >$100M cumulative.

**Canonical addresses to memorize:**
- Permit2 (universal): `0x000000000022D473030F116dDEE9F6B43aC78BA3` (same on every chain via CREATE2)

## Capture the signing request

- [ ] Use mock provider (`wallet_test/eip1193_mock_provider.js`) to intercept `eth_signTypedData_v4`
- [ ] Save full payload (domain + types + message) for offline decode
- [ ] Also intercept any `personal_sign` with raw bytes — might be wrapped Permit data

## Identify signing standard

- [ ] `domain.name == "Permit2"` AND `domain.verifyingContract == 0x000000000022D473030F116dDEE9F6B43aC78BA3` → Permit2
- [ ] `domain.name == <token name>` (e.g., "Dai Stablecoin") AND `types.Permit` defined → EIP-2612
- [ ] `domain.name == "USD Coin"` AND USDC contract → EIP-3009 transferWithAuthorization (different beast)
- [ ] Custom domain with permit-like fields → audit individually

## Permit2 decode

For `PermitSingle`:
- [ ] `details.token` — the ERC-20 being approved
- [ ] `details.amount` — uint160 max allowance (often hardcoded to type(uint160).max)
- [ ] `details.expiration` — Unix timestamp when allowance dies (default 30 days)
- [ ] `details.nonce` — bitmap-style; check for reuse
- [ ] `spender` — **the address that will be able to pull tokens — this is the critical field**
- [ ] `sigDeadline` — when the signature itself expires

For `PermitBatch`:
- [ ] `details[]` array — N tokens approved at once
- [ ] **Audit each item** — phisher may sneak high-value token into a batch

## Spender verification (most important)

For the `spender` address:
- [ ] Is it the dApp's documented router/contract (cross-check against official docs)?
- [ ] Is it Uniswap's UniversalRouter (`0x6ff5693b99212da76ad316178a184ab56d299b43` on mainnet, varies by chain)?
- [ ] Is it a fresh deploy (verify on Etherscan — deployment date, verified source)?
- [ ] Does the spender appear in the dApp's documented contracts list?
- [ ] **If spender doesn't match → Critical phishing surface**

## Domain verification (clone defense)

- [ ] Is the current URL the canonical dApp domain (not a wildcard clone)?
- [ ] Composes with `auth_provider_wildcard` threat model: clones request permits too
- [ ] Cross-check origin against the dApp's verified frontend

## Amount + expiration UX audit

- [ ] What did user CLICK in the UI? (e.g., "swap $100 USDC for ETH")
- [ ] What's the signature amount? Match or unlimited?
- [ ] Mismatch ≥ 10x intended → Medium UX failure
- [ ] amount = type(uint160).max → High UX failure (unlimited allowance)
- [ ] Expiration > 7 days for a one-time intent → Medium

## EIP-2612 specifics

- [ ] `Permit(owner, spender, value, nonce, deadline)` — standard fields
- [ ] `nonce` matches `IERC20Permit(token).nonces(owner)` — sequential
- [ ] Some tokens (e.g., older DAI) use different field order — verify
- [ ] Permit signature replay across forks: token deployed on multiple chains with same nonces → cross-chain replay if chainId not in domain

## Backend / relayer surface

If dApp uses meta-transaction relayer:
- [ ] Where does the signature get sent?
- [ ] Does the backend just forward, or does it store the signature?
- [ ] If stored: how long? Where? Who has access?
- [ ] Can someone trick the backend into submitting the sig to a different chain?

## Wallet decoding quality

Track which wallets show clear info vs blind signing:
- [ ] MetaMask — shows Permit2 spender + amount?
- [ ] Rabby — shows Permit2 + simulates impact?
- [ ] Coinbase Wallet — shows readable summary?
- [ ] Wallet showing only "Signature request" with hex → blind signing = drainer enabler

## Severity rubric

- Permit2 spender ≠ official router (attacker-controlled or unknown) → **Critical**
- Permit2 from clone subdomain (Phase 5 chain) → **Critical** (compose phishing chain)
- amount = uint160.max + expiration > 7 days + UX doesn't disclose → **High**
- PermitBatch contains tokens unrelated to user's intent → **High**
- Backend stores signatures with weak access control → **High**
- Wallet doesn't decode = enabler-only → **Medium** (report to wallet vendor, not dApp)

## Reproducer

```javascript
// Intercept signTypedData in mock provider
const intercepted = [];
window.ethereum.request = async (params) => {
    if (params.method === 'eth_signTypedData_v4') {
        const payload = JSON.parse(params.params[1]);
        intercepted.push(payload);
        console.log('[PERMIT2-CAPTURE]', JSON.stringify(payload, null, 2));
    }
};
// Then trigger the dApp's swap/deposit/approve flow
```

## Tools

- `wallet_test/signature_inspector.py --eip712-stdin`
- `cast call $PERMIT2 "allowance(address,address,address)(uint160,uint48,uint48)" $OWNER $TOKEN $SPENDER` — verify existing allowance
- Etherscan address tag database for spender lookups
- DEX aggregator router lists: https://docs.uniswap.org / https://docs.1inch.io

---

## Allowance audit BEYOND Permit2 / EIP-2612 (post-Transit 2026)

Permit2 and EIP-2612 are not the only "approve-then-drain" vectors. **Standard ERC-20
approvals to deprecated router contracts** are equally dangerous and persist for years.
Transit Finance May 2026 ($1.88M) — re-exploit of 2022-deployed deprecated TRON
contract that still had user approvals from 4 years prior.

**Composes with [ghost_contract_legacy_approvals.yaml](../threat_models/ghost_contract_legacy_approvals.yaml) — see H11 in [HYPOTHESES.md](../hypothesis/HYPOTHESES.md).**

### Standard ERC-20 allowance audit

For any **router / aggregator / bridge** the dApp uses (active OR deprecated):

- [ ] Enumerate all historical contract addresses for this protocol (docs + GitHub commit history + Etherscan internal-tx history)
- [ ] For each old/abandoned contract: `cast call <token> "allowance(address,address)(uint256)" <user> <old_contract>` for sample of token holders
- [ ] Document: how many users still have approvals to abandoned contracts?
- [ ] What's the sum of approved-but-not-yet-drained surface?

### Multi-chain enumeration

Most DeFi protocols deploy to many chains. Transit was on 13+ chains. Each chain has its own deployment history.

- [ ] List ALL chains where protocol operates (docs + DefiLlama protocol page)
- [ ] For each chain: identify active vs deprecated contract addresses (Etherscan/BscScan/Tronscan/etc.)
- [ ] **Critical: smaller chains (TRON, fantom, scroll, sonic) often skip pause/kill migrations** when deprecating
- [ ] Run `hypothesis/ghost_contract_scanner.py --rpc <chain_rpc> --ghost <deprecated_addr>` per chain

### Ghost contract attack surface red flags

- [ ] Contract bytecode present (not selfdestructed) + `paused()` returns false
- [ ] Contract has arbitrary-call selector (`callBytes`, `multicall(bytes[])`, `execute(address, bytes)`)
- [ ] Live user approvals from multi-chain top holders
- [ ] Owner renounced (no path to pause post-incident — WORST case, since vulnerability is permanent)

### dApp UX gaps (Behavioral)

- [ ] Does the protocol's dApp UI warn users about approvals to deprecated contracts?
- [ ] Does the UI link to revoke.cash for cleanup?
- [ ] Does the team's docs / changelog say "revoke your approvals to V1" explicitly?
- [ ] If none → bug bounty submission: "users have unrevoked approval surface to deprecated V1 contract, no warning shown"

### Severity rubric — Ghost approval surface

- Sum of live approvals to ghost contract > $1M (sample-based estimate) + arbitrary-call bug → **Critical**
- Sum > $100K + any bug present → **High**
- Sum > $10K + cosmetic issue → **Medium** (centralization / abandoned surface)
- Sum < $10K → **Info** (still worth flagging)

---

## References

- Permit2 docs: https://docs.uniswap.org/contracts/permit2/overview
- EIP-2612: https://eips.ethereum.org/EIPS/eip-2612
- Inferno Drainer write-up: rekt.news / SlowMist quarterly reports
