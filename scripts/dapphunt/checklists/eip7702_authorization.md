# EIP-7702 (Pectra) authorization — checklist

EIP-7702 went live on Ethereum mainnet with Pectra (May 2025). EOAs can now delegate
temporary code via a signed authorization. One careless signature → attacker has
EOA-as-contract until next overwriting delegation.

**Why this checklist exists:** new attack surface, immature tooling, drainer kits
already adapted to abuse it (Q3 2025). dApps that request 7702 authorizations without
clear UI = first wave of phishing victims.

## Detection — is this dApp using 7702?

- [ ] Capture a signing request via mock provider (`wallet_test/eip1193_mock_provider.js`)
- [ ] Is request type `0x04` (or wallet method name like `wallet_signAuthorization` / `personal_signTransaction` with auth list)?
- [ ] Does the dApp call `eth_sendTransaction` with `authorizationList` field?
- [ ] Search bundle for `SignedAuthorization`, `AuthorizationList`, `authorizeDelegate`

## Authorization payload analysis

For each captured authorization, decode and verify:

- [ ] `chainId` — must equal current connected chain
  - chainId == 0 → **Critical** cross-chain replay
  - chainId != current chain → **Critical** misdirected delegation
- [ ] `address` — the delegate contract
  - Is it a published, audited template?
  - Is it an attacker-controlled / fresh deploy?
  - Is it the dApp's own contract or some third-party?
- [ ] `nonce` — must match EOA's current nonce
  - Reused nonce → replay vulnerable
- [ ] `(y_parity, r, s)` — signature over (chainId, address, nonce)

## Delegate contract analysis

Once you know the delegate, audit it:

- [ ] Read source code (Etherscan verified? GitHub?)
- [ ] Does it use `address(this)` in storage access?
  - When 7702 active, `address(this)` = EOA, not delegate
  - Different delegations across time can collide in slot mapping
- [ ] Does it have arbitrary call function? `function execute(address target, bytes calldata data)` callable by msg.sender = address(this)?
- [ ] Does it have privileged setters? (setOwner, setOperator, transferOwnership)
- [ ] Is there a revocation function?
- [ ] Constructor / initializer — is it relevant for EOA delegation?

## dApp UX surface

- [ ] Does the signing UI show:
  - Delegate contract name? (not just address)
  - Verified-template badge?
  - What functions become callable?
  - Clear "this delegates code to your wallet" warning?
- [ ] Is there a revocation path in the dApp UI?
- [ ] What does the dApp tell the user about persistence?

## Wallet provider behavior

For known providers (Privy, Magic, Web3Auth, Coinbase, MetaMask):

- [ ] Does provider have a "default 7702 delegate"?
- [ ] If yes, audit that delegate (next section)
- [ ] Does provider support `wallet_revokeDelegation` or equivalent?
- [ ] Does provider warn on chainId mismatch?
- [ ] Does provider enforce nonce > current?

## Off-chain replay analysis

Same authorization signature could be used elsewhere:

- [ ] If chainId == 0: signature valid on EVERY EVM chain (BSC, Polygon, Arbitrum, etc.)
  - Check victim's holdings across chains
- [ ] If chainId set but never invalidated: nonce reuse on same chain = re-delegation possible
- [ ] If signature broadcast publicly: monitor mempool / bundlers for replay

## Severity rubric

- dApp requests 7702 sig + delegate is unaudited + chainId=0 → **Critical**
- dApp requests 7702 sig + delegate has arbitrary `execute()` → **Critical**
- Wallet doesn't show delegate name, just address → **High** (phish enabler)
- Wallet has no revocation UI → **High**
- Delegate uses `address(this)` for storage → **High** (corruption)
- Default delegate from wallet provider with privileged setters → **Critical**

## Reproducer scaffolding

```javascript
// In wallet_test/eip1193_mock_provider.js, intercept eth_sendTransaction
// and authorizationList field. Log full auth payload.

window.ethereum.request = async (params) => {
    if (params.method === 'eth_sendTransaction' && params.params?.[0]?.authorizationList) {
        console.log('[7702-INTERCEPT]', JSON.stringify(params.params[0].authorizationList));
    }
    // ... continue mock flow
};
```

## Tools

- `wallet_test/signature_inspector.py --auth-stdin` (extend to decode auth list)
- Etherscan / Phalcon for delegate contract bytecode + ABI
- foundry's `cast tx --rpc-url ... <txhash>` to inspect on-chain 7702 txs

## References

- EIP-7702: https://eips.ethereum.org/EIPS/eip-7702
- Pectra activation: https://ethereum.org/en/roadmap/pectra/
- OpenZeppelin 7702 templates: https://github.com/OpenZeppelin/openzeppelin-community-contracts
- Cyfrin 7702 attack demo: cyfrin.io/blog (search "7702")
