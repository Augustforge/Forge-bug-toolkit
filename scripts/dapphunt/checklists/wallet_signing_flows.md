# Wallet signing flows — multi-chain comparison checklist

## EVM (Ethereum / L2s)

- [ ] `eth_requestAccounts` — initial connect, returns address
- [ ] `wallet_switchEthereumChain` — chain switch; some dApps assume success
- [ ] `personal_sign` — UTF-8 message, prefixed with `\x19Ethereum Signed Message:\n`; no chain binding by default
- [ ] `eth_sign` — RAW message signing — **almost always a finding if present**, deprecated by MetaMask
- [ ] `eth_signTypedData_v4` — EIP-712; domain binding (chainId + verifyingContract)
- [ ] `eth_sendTransaction` — direct call
- [ ] Permit (EIP-2612) — gasless approve via signature
- [ ] Permit2 (Uniswap) — universal permit; allowance with expiry
- [ ] EIP-4361 SIWE — sign-in with Ethereum
- [ ] EIP-1271 — smart wallet signature validation
- [ ] EIP-3009 — USDC transferWithAuthorization
- [ ] **EIP-7702 (Pectra)** — `eth_signAuthorization` / tx type `0x04` (SET_CODE_TX_TYPE) / `authorizationList`
  - Authorization tuple: `(chain_id, address, nonce, y_parity, r, s)` — signs delegation of EOA code to a contract
  - If dApp asks for an authorization but UI shows "Connect" / "Sign in" → user grants code delegation unknowingly
  - **Verify in UI**: what contract address is the EOA delegating to? Is the delegation chain-bound? Is `chain_id=0` (cross-chain valid)?
  - Same threat-model as EIP-1271 lying but at the EOA level — **entire wallet becomes attacker-controlled smart contract** until revoked
  - Sign of bug: dApp constructs `authorization` payload silently / labels as "session permission"

## Solana

- [ ] `window.solana.connect()` — initial connect
- [ ] `signMessage(Uint8Array)` — arbitrary message
- [ ] `signTransaction(Transaction)` — single tx
- [ ] `signAllTransactions([Tx, Tx, ...])` — **bulk signing**; user may not inspect each
- [ ] `signIn({ ... })` — SIWS (sign-in with Solana) proposal
- [ ] No chain binding equivalent — Solana doesn't have chain IDs; transactions are network-bound via blockhash and account ownership

## Cosmos

- [ ] `window.keplr.experimentalSuggestChain` — chain config
- [ ] `signAmino(chainId, signer, signDoc)` — legacy Amino format
- [ ] `signDirect(chainId, signer, signDoc)` — Protobuf format (preferred)
- [ ] `signArbitrary(chainId, signer, data)` — ADR-36 raw message
- [ ] Cross-chain reuse — chainId binding is enforced if dApp passes it correctly

## Sui

- [ ] `signTransactionBlock({ transactionBlock })` — tx signing
- [ ] `signPersonalMessage({ message })` — UTF-8 message
- [ ] Sender / gas fields validated by wallet

## Aptos

- [ ] `aptos.signTransaction({ ... })`
- [ ] `aptos.signMessage({ message, ... })`
- [ ] No EIP-712-style domain; Aptos uses its own typed-data scheme via `MoveStructLayout`

## Cross-chain checks

- [ ] Same signature accepted across chains? (chainId binding)
- [ ] Same signature accepted across protocols? (verifyingContract binding)
- [ ] Wallet UI shows what's being signed clearly? Or only hash?

## Embedded wallet (Privy / Magic / Web3Auth) specifics

- [ ] Embedded wallet keys are held server-side (custody)
- [ ] Signing happens via TLS-encrypted RPC to provider
- [ ] If provider's signing endpoint is compromised → all users' keys at risk
- [ ] Outside-attacker can't directly drain (no key access) but can cause provider to sign attacker-favorable payloads if dApp is tricked
