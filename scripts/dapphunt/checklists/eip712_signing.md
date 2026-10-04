# EIP-712 / EIP-1271 / SIWE / multi-chain signing — checklist

## EIP-712 typed data

- [ ] Capture a typed-data signing request from the dApp (use mock provider or burner)
- [ ] Decode `domain.{name, version, chainId, verifyingContract}`
- [ ] Is `chainId` dynamic (matches the wallet's current chain) or hardcoded?
- [ ] Is `verifyingContract` set to the actual on-chain target, or zero / placeholder?
- [ ] If chainId hardcoded to 1 (mainnet) but dApp deploys to L2 → cross-chain replay
- [ ] If verifyingContract is the wrong contract → signature may apply elsewhere

## EIP-1271 (smart wallet signatures)

- [ ] Does the protocol accept signatures from smart contract wallets (returns `0x1626ba7e`)?
- [ ] If yes: is there a way to make a smart wallet that returns `0x1626ba7e` for ANY hash?
- [ ] Race: signature accepted before the smart wallet's code is finalized

## EIP-3009 transferWithAuthorization

- [ ] If dApp uses transferWithAuthorization, are nonce + valid-after / valid-before fields enforced?
- [ ] Domain separator binding to chainId + verifyingContract?

## SIWE (EIP-4361)

- [ ] Message has `domain` line at top? Matches the actual URL the user is on?
- [ ] `nonce` field present? Per-session unique?
- [ ] `Issued At` field present? Server checks it's recent (< 5 minutes)?
- [ ] `Expiration Time` field present? Server enforces it?
- [ ] `Statement` field — user-readable? Could attacker control it to phish?

## SIWS (Solana sign-in)

- [ ] Same as SIWE but on Solana with `signIn()` method
- [ ] Domain binding via Solana wallet standard (some wallets don't enforce)

## Cosmos signing

- [ ] signAmino vs signDirect — Direct preferred (less ambiguity)
- [ ] ADR-36 `signArbitrary` — message format clear? No tx fields hidden in message?

## Sui / Aptos

- [ ] signTransactionBlock vs signPersonalMessage — distinct purposes; verify dApp uses correct method
- [ ] Transaction blocks include all gas / sender info?

## Cross-chain replay

- [ ] Does the dApp accept a signature on chain X for use on chain Y?
- [ ] Permit / Permit2 signatures with chainId in domain = bound; without = replayable
- [ ] Personal_sign with raw message (no domain binding) = always replayable across chains

## Tools

- `wallet_test/signature_inspector.py --eip712-stdin`
- `wallet_test/signature_inspector.py --siwe-stdin`
- `wallet_test/signature_inspector.py --personal-sign 0x...`
