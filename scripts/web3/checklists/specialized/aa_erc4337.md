# Specialized Checklist: ERC-4337 Account Abstraction

Scope: smart accounts (Safe, Kernel, ZeroDev, Biconomy, Coinbase Smart Wallet),
EntryPoint contracts, Bundlers (Pimlico, Stackup, Alchemy Rundler, Etherspot),
Paymasters (verifying, deposit-based, ERC20-fee), Account Factories (CREATE2).

Sources cross-referenced:
- [Cantina ERC-4337 security blog](https://cantina.xyz/blog/erc-4337-security-bundlers-paymasters-signatures)
- `_audit_corpus/_known_findings.jsonl` entries `erc4337-2025-*`
- [EIP-4337 spec](https://eips.ethereum.org/EIPS/eip-4337) + [ERC-7562 validation rules](https://eips.ethereum.org/EIPS/eip-7562)

---

## 1. Signature Validation (HIGH severity class)

### 1a. UserOp hash derivation
- [ ] UserOp hash includes the `entryPoint` address (cross-EntryPoint replay defence)
- [ ] UserOp hash includes `chainId` (cross-chain replay defence)
- [ ] UserOp hash includes the `account address` (cross-account replay for clone factories)
- [ ] Hash construction does NOT use packed encoding without a domain separator (see `erc4337-2025-calldata-hash-collision`)
- [ ] `validateUserOp` verifies the signature over the exact hash from the EntryPoint, doesn't reconstruct it

**Red flag pattern**:
```solidity
// BAD — packed without a domain → cross-account replay if codehash is identical
bytes32 hash = keccak256(abi.encodePacked(userOp.sender, userOp.nonce, ...));
```
```solidity
// GOOD — EIP-712 structured + entryPoint + chainId
bytes32 hash = keccak256(abi.encode(USEROP_TYPEHASH, ..., entryPoint, block.chainid));
```

### 1b. ERC-1271 for smart accounts
- [ ] `isValidSignature(hash, sig)` uses an EIP-712 domain separator
- [ ] Domain includes: name, version, chainId, verifyingContract
- [ ] Hash binding to intent context (e.g., Permit2 != Uniswap order)
- [ ] No signature reuse across (account, application context) pairs

**Cross-link**: [`_known_findings`](../../research/_audit_corpus/_known_findings.jsonl) → `erc4337-2025-erc1271-signature-reuse`

### 1c. Nonce handling
- [ ] Nonce strictly increments (or semaphore-based unordered nonces are correct)
- [ ] Cannot replay a UserOp with the same nonce
- [ ] Nonce key tied to the account, not global

---

## 2. Paymaster Griefing (HIGH severity class)

### 2a. Budget bounds
- [ ] `validatePaymasterUserOp` enforces a per-UserOp max cost
- [ ] Rate-limit per account / per time window (spam protection)
- [ ] Total paymaster deposit can cover a worst-case month's usage

### 2b. Validation/execution state consistency
- [ ] `postOp` does NOT use state that could have changed (gas price, oracle prices)
- [ ] Pricing snapshot taken in validation, frozen for postOp
- [ ] If an ERC20-fee paymaster — token price locked, not re-fetched after execution
- [ ] postOp callback handles `actualGasCost >> validationGasCost` gracefully

**Red flag pattern**:
```solidity
// BAD — gas price fresh in postOp → attacker timing flash-spike
function postOp(...) external {
    uint256 cost = userOp.gas * tx.gasprice;  // attacker controls this
}
```

### 2c. Paymaster authentication (private paymasters)
- [ ] If the paymaster sponsors only specific accounts — signature/allowlist check
- [ ] Signature is NOT replayed cross-paymaster
- [ ] If signed sponsorship — has an expiry timestamp

**Cross-link**: `_known_findings` → `erc4337-2025-paymaster-unbounded-sponsorship`

---

## 3. Bundler Griefing (MEDIUM-HIGH class)

### 3a. Validation simulation guarantees
- [ ] Validation simulation CANNOT diverge from on-chain execution (ERC-7562 banned opcodes respected)
- [ ] No `BLOCKHASH`, `BLOBHASH`, `TIMESTAMP`, `NUMBER`, `BALANCE` in validation paths
- [ ] No `SLOAD`/`SSTORE` outside the account's own storage in validation
- [ ] Storage access patterns satisfy ERC-7562 rules

### 3b. InitCode front-running (Account Factories)
- [ ] CREATE2 salt cryptographically bound to the owner (`salt = keccak256(owner || ...)`)
- [ ] Counterfactual address cannot be deployed by a 3rd party with a different init state
- [ ] If the user funded the counterfactual address before deployment — the bundler cannot swap the owner

**Red flag pattern**:
```solidity
// BAD — salt is only the nonce → a frontrunner can deploy with a different owner
function createAccount(address owner, uint256 nonce) external returns (Account) {
    return new Account{salt: bytes32(nonce)}(owner);
}
```
```solidity
// GOOD — salt commits to the owner
bytes32 salt = keccak256(abi.encode(owner, nonce));
```

**Cross-link**: `_known_findings` → `erc4337-2025-bundler-initcode-frontrun`

### 3c. Gas costs bounded
- [ ] verificationGasLimit, callGasLimit, preVerificationGas have caps in the factory/account
- [ ] No griefing where the attacker pays minimal but forces large execution

---

## 4. EntryPoint Authentication

- [ ] All execute paths use `require(msg.sender == entryPoint)` (or a modifier)
- [ ] EntryPoint address is immutable / set once / via authenticated upgrade
- [ ] EntryPoint address verified against canonical (0x0000000071727De22E5E9d8BAf0edAc6f37da032 for v0.7)
- [ ] Do not trust a user-supplied EntryPoint address in any call path

---

## 5. Aggregator Signatures

- [ ] Aggregator sig verification matches per-UserOp validation (no bypass when an aggregator is used)
- [ ] Aggregator can attest only to UserOps from accounts that opted in to it
- [ ] Aggregator compromise does not drain all accounts (limit blast radius)

---

## 6. Account Upgrade / Recovery

- [ ] Upgrade requires an owner signature (not paymaster, not bundler, not EntryPoint)
- [ ] Recovery flow is time-locked / multi-sig / hardware-key gated
- [ ] No upgrade path via paymaster privilege
- [ ] Module installation (ERC-7579) authenticated
- [ ] Removed/replaced modules cannot replay old signed UserOps

---

## 7. Composability Edge Cases

- [ ] Batch UserOp: failure handling — partial state if one op in the batch reverts?
- [ ] DelegateCall in account execution — which modules are trusted?
- [ ] Reentrancy: a UserOp executing an external call that calls EntryPoint again
- [ ] Session keys / sub-keys: scope limited (selector + target + value caps)

---

## 8. Deploy / fee-flow / staking hygiene (SlowMist AA checklist gaps)

Items the high-level checklists list that the sections above didn't yet cover (source:
`slowmist/Account-Abstraction-Security-Audit-Checklist`, deduped against §1–7).

### 8a. Cross-chain bytecode compatibility
- [ ] Account/factory deployed to multiple EVM chains compiles to bytecode that runs on ALL of them — no `PUSH0` (Solidity ≥0.8.20 / Shanghai) on a chain that hasn't enabled Shanghai → account bricks or address differs. Pin `evm_version`; verify the SAME deployed address across chains actually has identical, executable code.

### 8b. Account prefund (`missingAccountFunds`)
- [ ] `validateUserOp` transfers `missingAccountFunds` to the EntryPoint (pays its own prefund) — and does so via a call whose failure is handled per spec (return non-zero `validationData`, don't revert the whole bundle). A wallet that never pays prefund is unusable; one that reverts on the prefund transfer is a bundler-griefing vector.

### 8c. Staked-deposit permanent lock
- [ ] Entity stake to EntryPoint (`addStake`) respects `unstakeDelaySec >= MIN_UNSTAKE_DELAY` and the withdraw path (`unlockStake`→wait→`withdrawStake`) is reachable — a paymaster/factory whose stake can be locked with no valid unlock (or `unstakeDelaySec` set so high it's effectively permanent) loses the deposit forever. Check both the config value AND that the unlock function isn't access-gated to an address that can disappear.

---

## Cross-references
- Threat model auto-match: `protocol_class: account-abstraction` or tag `erc4337`
- Submission pre-flight: [`submission_checklist.yaml`](../../../../sessions/_methodology/submission_checklist.yaml)
- Pattern registry: [`_PATTERN_REGISTRY.md`](../../threat_models/_PATTERN_REGISTRY.md) → the Axis "Cryptographic verification ≠ semantic verification" applies to the signature replay class
