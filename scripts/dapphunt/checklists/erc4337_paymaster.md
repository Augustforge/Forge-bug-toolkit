# ERC-4337 paymaster / bundler — checklist

Use when target uses Account Abstraction (ERC-4337): smart accounts, paymasters,
bundlers, EntryPoint contract.

**Why this checklist exists:** AA stack has multi-layer surface — paymaster
sponsorship abuse, bundler censorship, validation phase storage rules. Growing
bounty surface 2025-2026.

**Canonical EntryPoints:**
- v0.6: `0x5FF137D4b0FDCD49DcA30c7CF57E578a026d2789`
- v0.7: `0x0000000071727De22E5E9d8BAf0edAc6f37da032`

## Identify the AA stack

- [ ] What's the smart account implementation? (Safe{Core}, Kernel, Biconomy, custom)
- [ ] What's the EntryPoint version? (v0.6 vs v0.7 — different rules)
- [ ] Who's the bundler? (Pimlico, StackUp, Alchemy, custom)
- [ ] Is there a paymaster? Single-sponsor or token-paymaster?

## Paymaster sponsorship signature

For verifying-paymaster pattern:
- [ ] What's hashed for the sponsorship sig?
  - Should include: chainId, paymaster address, validUntil, validAfter, UserOp hash
  - Missing chainId → cross-chain replay
  - Missing paymaster address → cross-paymaster replay (rare but real)
- [ ] What signs the sig? Single EOA / multisig / TSS?
- [ ] If single EOA: where is the key held? (centralization risk)
- [ ] Are signed sigs stored anywhere? Logged?

## Validation phase storage rules (EntryPoint enforcement)

ERC-4337 spec restricts validation-phase storage access:
- [ ] Read paymaster's `validatePaymasterUserOp` source
- [ ] Catalog SLOAD operations:
  - Access to self storage (paymaster's own slots) → OK
  - Access to sender's storage → restricted (sender's "associated storage" only)
  - Access to ANY other contract → forbidden
- [ ] Use `debug_traceCall` on a sample UserOp to enumerate SLOADs
- [ ] Bundler accepting non-compliant ops → exploitable inconsistency

## Sponsorship rate limiting

- [ ] Is there per-sender max ops?
- [ ] Is there per-app/dApp max ops?
- [ ] Is there global daily limit?
- [ ] What happens at limit — revert or queue?
- [ ] **No rate limit + open sponsorship = DoS drain primitive**

## postOp accounting

- [ ] Does paymaster recompute gasCost or use EntryPoint-provided value?
- [ ] If recomputed: source of gas price? mismatch surface?
- [ ] For token-paymasters: oracle source for token→ETH price?
- [ ] Oracle manipulation in postOp → silent fee extraction

## Signature flow audit

- [ ] Who validates the smart account's signature? account itself? or paymaster duplicating?
- [ ] If paymaster duplicates: send UserOp with valid paymaster sig + invalid sender sig
- [ ] EntryPoint reverts on sender validation failure — paymaster pre-charge consumed?
- [ ] **If yes → grief/drain on paymaster deposit**

## Bundler endpoint analysis

- [ ] List all bundler endpoints used by the dApp
- [ ] Check rate limits, CAPTCHA, geo restrictions on each
- [ ] Single bundler dependency → censorship risk
- [ ] Is there a fallback path? Direct EntryPoint? Multiple bundlers?

## EntryPoint deposit safety

- [ ] Where does paymaster keep its prefund deposit?
- [ ] Who can withdraw from EntryPoint.deposits[paymaster]?
- [ ] Is the withdrawer key the same as sponsorship signer?
- [ ] Single key compromise = drain paymaster + impersonate sponsorship

## Smart account specifics

- [ ] What signature scheme? ECDSA / WebAuthn / multi-key?
- [ ] Module/plugin system (Kernel, Safe{Core})?
  - Plugin install authority?
  - Plugin permission scoping?
- [ ] Recovery mechanism — social recovery? timelock?
- [ ] Nonce management — sequential vs key-grouped?

## Session keys (if implemented)

- [ ] Are there session keys with limited permissions?
- [ ] Scope: which functions/contracts can session key call?
- [ ] Expiration: time-limited? usage-count-limited?
- [ ] Revocation path?

## Bundler-side observations

- [ ] Is bundler open to public RPC?
- [ ] What chains does bundler support?
- [ ] Are bundler fees transparent?
- [ ] Mempool exposure — public or private?

## Severity rubric

- Paymaster sig missing chainId → **High** (cross-chain replay)
- Paymaster validation accesses non-self storage → **Medium-High** (bundler dependent)
- No rate limit + open sponsorship → **High** (DoS drain)
- postOp uses recomputed gas with manipulable source → **Medium-High**
- Single EOA controls EntryPoint deposit withdraw → **High** (centralization)
- Paymaster duplicates sender sig validation → **High** (grief primitive)
- Module install on smart account permissionless → **Critical** (account takeover)

## Tools

- `cast call <EntryPoint> "getDepositInfo(address)(uint112,bool,uint112,uint32,uint48)" <paymaster>` — paymaster deposit info
- `cast logs --from-block X --to-block Y --address <EntryPoint>` — UserOp event traces
- Pimlico UserOp tracer: https://www.userop.dev/
- Stackup paymaster docs: https://docs.stackup.sh/

## References

- ERC-4337: https://eips.ethereum.org/EIPS/eip-4337
- EntryPoint v0.7 changes: https://github.com/eth-infinitism/account-abstraction/releases
- Validation rules (ERC-7562): https://eips.ethereum.org/EIPS/eip-7562
- Safe{Core} AA stack: https://docs.safe.global/aa-sdk
