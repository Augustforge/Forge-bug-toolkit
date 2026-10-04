# Web3 Threat Intelligence — Recent Attack Patterns

A base of real attack patterns from 2024-2026. Used by the `/hunt` skill at the **AI synthesis** stage to:
- Compare findings against known exploits
- Hint at which configurations to check manually
- Identify attacks outside standard coverage (that Slither/Mythril don't catch)

Source: [blockaid.io/blog](https://www.blockaid.io/blog), Immunefi disclosure reports.

---

## 1. DVN Single-Point-of-Failure (LayerZero) — KelpDAO $292M

**Date:** 2025
**Type:** Configuration vulnerability of cross-chain bridges
**Impact:** $292M

### Pattern
LayerZero V2 uses Decentralized Verifier Networks (DVN) to verify cross-chain messages. A configuration of `requiredDVNCount=1` means a single compromised verifier is enough to forge any message.

### How to detect
On-chain query: `EndpointV2.getConfig(eid, oapp, configType=2)` returns UlnConfig. Flag if:
```
requiredDVNCount == 1 AND optionalDVNCount == 0
```

### What Slither/Mythril don't catch
This is **configuration**, not code. An on-chain check after deployment via `cast call` is required.

**Action for our toolkit:** add a LayerZero config check step to the `/hunt` Web3 flow if the contract imports `ILayerZeroEndpointV2`.

---

## 2. Frontend Hijacking (Web2 attack on Web3)

**Date:** March 2026 (5 protocols in a week)
**Type:** Web2 infrastructure → Web3 users
**Impact:** Variable, potentially the entire TVL

### Pattern
The attacker compromises the CDN / DNS / build pipeline (Vercel, Cloudflare, S3) of a DeFi protocol. Injects malicious JS into the frontend's bundle.js. When the user signs a transaction through the UI, it is routed to a drainer instead of the real operation.

### How to detect
- Subresource Integrity (SRI) for all external JS
- Strict CSP without `unsafe-eval`, `unsafe-inline`
- Monitoring of CSP header / JS hash changes

### Action for toolkit
**Already in the web2 scan:** `scan.sh` checks CSP. But for Web3 projects it needs to be **stricter**:
- If the protocol is DeFi → CSP must forbid external script sources
- Missing SRI on a critical bundle = high severity (not medium)

---

## 3. Stablecoin Impersonation

**Date:** March 2026
**Type:** Token impersonation + look-alike domains
**Impact:** Constantly growing

### Pattern
- Deploy a token with the ticker "USDC" or "USDT" on a non-standard network
- Register look-alike domains (us-dc-portal.com, tetherx.io)
- Advertise a "swap" on these domains
- The victim swaps real stablecoins for junk

### How to detect
- Cross-check the token contract address against the CoinGecko / CoinMarketCap registry
- Token age + liquidity check (new + low liquidity = suspicious)
- DNS WHOIS — domain age

### Action for toolkit
Add `scripts/web3/token_legitimacy.py` (TODO later) — check a new token against known registries.

---

## 4. Wallet Drainer via Fake Revoke Sites

**Date:** Continuous (accelerated 2024-2026)
**Type:** Phishing exploiting post-hack panic
**Impact:** Per-victim, aggregated $millions

### Pattern
1. A real hack of a large protocol → panic in the community
2. Within hours, domains are registered: `revoke-{protocol}.com`, `migrate-{protocol}.app`
3. Boosted on Twitter / fake X accounts with a blue checkmark
4. The victim goes to "revoke approvals" → signs a drainer transaction

### How to detect
- Real-time domain monitoring after large hacks (Whois of new registrations by keywords)
- Transaction simulation **before** signing (Tenderly / Blockaid API)
- Check the `to` address against drainer threat feeds

### Action for toolkit
This is user protection, not a contract audit. Relevant for **disclosure reports** — user protection recommendations.

---

## 5. Governance Attack + Durable Nonce (Drift) — $285M

**Date:** 2025
**Type:** Multi-step: social → keys → market manipulation
**Impact:** $285M
**Chain:** Solana (our scope is EVM, but the pattern is universal)

### Pattern (adapted to EVM)
1. Social engineering of multisig signers (2-of-5 or 3-of-7)
2. Obtain N keys where N = threshold
3. Pre-signed transactions with a large nonce (in EVM — a high nonce, wait until the nonce catches up)
4. Create a fraudulent pool / market via governance
5. Wash trading to pump a fake price
6. Burn the fake positions for real funds

### How to detect (EVM analogue)
- Multisig threshold check: ≥4-of-7 is needed for serious DeFi
- Timelock on governance proposals: <48h = critical
- Circuit breakers for price feeds in derivatives protocols

### Action for toolkit
Add a manual check to the `/hunt` Web3 flow for protocols with governance:
- Gnosis Safe owners count + threshold
- Timelock delay (via the `Timelock.delay()` view function)
- Circuit breaker presence

---

## 6. Compromised Key + USR Stablecoin Mint (Resolv) — $80M

**Date:** 2025
**Type:** Key compromise + permission abuse
**Impact:** $80M

### Pattern
- Compromise of the private key of an EOA with a minter role on a stablecoin
- Mass mint of USR without collateral
- Depeg + sale on a DEX

### How to detect
- **The minter must be a multisig, not an EOA** — this is a red flag in any audit
- The mint function must have a supply cap or a collateral check
- No direct mint() from an EOA owner

### Action for toolkit
Add to a Slither custom detector / Wake check:
- Find `mint()` functions
- Check who can call (`onlyOwner`, `onlyMinter`)
- If caller = single EOA → flag CRITICAL
- If no supply cap / collateral check → HIGH

---

## 7. Thorchain TSS validator key extraction — $10.8M

**Date:** 15 May 2026
**Type:** Cryptographic insider — malicious bonded validator
**Impact:** $10.8M across 4 chains (ETH 3,443 / BTC 36.85 / BNB 96.6 / Base remainder)
**Chain:** Multi-chain (Thorchain native + outbound to ETH/BTC/BNB/Base)

### Pattern (canonical bonded-actor exploit)

1. Attacker deposited funds via a privacy bridge (XMR → Hyperliquid → USDC → Arbitrum → ETH)
2. Use ETH to acquire RUNE, bonded a new validator node `thor16ucjv3v695mq283me7esh0wdhajjalengcn84q`
3. Wait for churn into the active signing set
4. Participate in legitimate signing ceremonies — sending malformed ZK proofs / bad Paillier params (TSSHOCK c-split/c-guess variant)
5. Honest nodes leak partial shares; attacker accumulates offline over N rounds
6. Reconstruct the vault private key offline
7. Sign unauthorized outbound transactions to 4 chains simultaneously
8. Detection ~8 minutes after the first drain, manual `make pause` invoked

### Root cause class

**GG20 TSS implementation gaps** — partial legacy fix. Verichains received a **$500K bounty in 2022** for the α-shuffle variant. The fix was narrow — sibling variants (c-split/c-guess) stayed alive. CVE-2023-33241 (Fireblocks BitForge) covered Paillier modulus validation. It is unclear whether the THORChain fork was fully protected against all vectors.

### Why missed despite multi-audit history

Halborn / Trail of Bits / Kudelski audited THORChain. **TSS attacks are especially subtle**:
- The adversarial-validator threat model is out of typical audit scope (audits are predominantly for an outside attacker)
- No protocol abort during the attack — honest nodes don't notice the ZK proof malformation
- Cryptographic primitives — a different skill set than a Solidity audit
- Post-2022-bounty drift — the `tss-lib` fork mutated, possibly re-introducing adjacent leakage paths

### How to detect

**Static (code review)**:
- See `checklists/specialized/tss_mpc.md` — the full checklist
- Verify Paillier biprime + small-factor sieve checks are present in all code paths
- Verify ZK iterations are hardcoded ≥128
- Verify churn-in latency exists

**Dynamic (on-chain)**:
- Vault balance invariant per block: `Σ(authorized_inflows) - Σ(authorized_outflows) == vault_balance`
- Outbound txs without a matched inbound swap memo = critical anomaly
- Per-node ceremony abort rate — `0%` over many rounds = suspicious

**Threat-model lens**: `prompts/bonded_actor_threat.md`. Threat-model YAML: `threat_models/tss_validator_extraction.yaml`.

### Action for toolkit

- `checklists/specialized/tss_mpc.md` — TSS-specific checklist
- `prompts/bonded_actor_threat.md` — adversarial actor lens
- `threat_models/tss_validator_extraction.yaml` — reusable hypothesis template
- Mandatory step in `/deephunt` J3 for protocols using TSS (Maya, Threshold Network, Swingby, io.Finnet, Axelar tofn)

---

## Meta-pattern: Post-bounty variant drift

**Rule**: When a protocol paid a bounty for variant X of class C, and the fix is narrow (only one specific code path) — class C still lives in the protocol. Sibling variants Y, Z require separate verification.

### Canonical examples

- **THORChain α-shuffle ($500K, 2022)** → **c-split/c-guess ($10.8M, 2026)** — 4 years between the paid fix and the sibling exploit
- **Multichain Anyswap signature replay (2021)** → multiple sibling variants until the final shutdown
- **Curve readonly-reentrancy ($70M, 2023)** — first instance, multiple forks exploited over 6+ months

### Detection workflow

1. For a target, check: are there past paid bounties? (Solodit, rekt.news, the project's own disclosures)
2. For each paid bounty: extract the root-cause class (not the specific exploit)
3. For each class — generate sibling variant hypotheses:
   - Same protocol module, different function?
   - Same library, different version?
   - Same primitive, different parameter?
4. Apply `scripts/web3/longtail/bounty_regression.py` + `threat_models/post_bounty_variant_drift.yaml`

### Why this works

Bug bounty fixes are often under time pressure. The auditor checks "does this specific exploit still work" — not "is the entire class addressed". The auditor's knowledge of a variant's existence often only emerges weeks/months later.

**Rule of 3**: if a paid bounty fix touched code N lines, and adjacent ≤3N lines are also part of the same class — sibling variants almost certainly exist.

---

## Adversarial-actor framework

The six exploit cases above cluster into an actor-class lens. This is the structure for the bonded_actor_threat.md prompt.

| Case | Actor class | Bond/role |
|---|---|---|
| Thorchain TSS | TSS validator | RUNE bonded |
| Drift governance | Multisig signer | Trusted role |
| Resolv USR | Mint authority | Single EOA (anti-pattern) |
| KelpDAO DVN | LayerZero verifier | DVN operator |
| Multichain (historical) | MPC node | Bonded validator |
| Ronin (historical) | Validator multisig | 5-of-9 trust |

**Common pattern**: the bonded actor has legitimate capability, behaves "legitimately" in one ceremony/tx — but cumulative behavior extracts value. A standard outside-attacker audit doesn't catch this.

---

## Summary: what to add to the `/hunt` skill

At the AI synthesis step for a Web3 contract, check manually:

| Pattern | Manual check |
|---------|--------------|
| LayerZero | `getConfig().requiredDVNCount` ≥ 2 |
| Frontend (DeFi) | CSP + SRI strict |
| Multisig governance | threshold ≥ 4-of-7, timelock ≥ 48h |
| Mint authority | multisig, not EOA, supply cap |
| Cross-chain bridge | DVN count, validator set diversity |
| Token legitimacy | registry cross-check, age, liquidity |

These patterns **complement** the automatic scan (slither/mythril/wake) and focus on **configuration** vulnerabilities that automatic detectors don't find.

---

## Sources for regular updates

- https://www.blockaid.io/blog — must monitor
- https://x.com/blockaid_ — Twitter account with breakdowns
- https://rekt.news — chronicle of DeFi hacks
- https://defiyield.app/rekt-database — structured database
- https://immunefi.com/explore/disclosed/ — public disclosures
- https://www.halborn.com/blog — postmortems for every major hack

---

# Recent Attack Patterns — December 2025 → May 2026

A fresh blob of patterns from Halborn case studies + Blockaid alerts. All added as Slither detectors (`scripts/web3/detectors/`) or standalone scripts.

## R1. CPIMP — Clandestine Proxy-In-the-Middle of Proxy

**Date:** December 2025 | **Victim:** USPD | **Amount:** $1M
**Source:** [Halborn USPD analysis](https://www.halborn.com/blog/post/explained-the-uspd-hack-december-2025), [CPIMP explainer](https://www.halborn.com/blog/post/what-is-a-cpimp-attack-in-defi-smart-contracts)

### Pattern
Proxy deployed without atomic init. Attacker frontrun init via Multicall3 → injected a malicious wrapper proxy between the legitimate proxy and the implementation. Etherscan showed the original code, but the proxy pointed to a backdoor. 78 days silent → minted 98M USPD.

### Detection
- Slither: `cpimp_proxy_init.py` — flag a proxy without `_disableInitializers()` in the constructor + initialize() without a deployer guard
- Manual: check that deploy and init happen in one transaction

---

## R2. Groth16 zkSNARK Misconfiguration

**Date:** February 2026 | **Victims:** VeilCash, FOOMCASH copycat | **Amount:** $2.26M (FOOMCASH)
**Source:** [zksecurity analysis](https://blog.zksecurity.xyz/posts/groth16-setup-exploit/), [CryptoTimes](https://www.cryptotimes.io/2026/02/26/foomcash-loses-2-26m-in-copycat-zksnark-exploit/)

### Pattern
A verifier with `delta2 == gamma2` allows forging any proof without knowing the witness. Trusted setup ceremony skipped or placeholder values. PoC public → 48h after VeilCash, FOOMCASH was hacked.

### Detection
- Slither: `groth16_setup_check.py` — flag verifier contracts, check delta2/gamma2 equality
- Manual: `snarkjs zkey verify` against the original phase-2 transcript

---

## R3. Axelar Message Spoofing (Origin Not Validated)

**Date:** February 2026 | **Victim:** CrossCurve | **Amount:** $3M
**Source:** [Halborn CrossCurve](https://www.halborn.com/blog/post/explained-the-crosscurve-hack-february-2026)

### Pattern
expressExecute-like functions did not validate the origin from Axelar. The attacker crafted messages that PortalV2 considered legitimate → unlocking tokens.

### Detection
- Bridge tests: `bridge_tests/check_bridges.sh` — extended with an Axelar origin validation check
- Pattern: contracts importing `IAxelarExecutable` without overriding `_execute` with `require(sourceAddress == trustedSource)`

---

## R4. ERC-3525 Double-Mint via Reentrancy

**Date:** March 2026 | **Victim:** Solv Protocol | **Amount:** $2.7M
**Source:** [Halborn Solv](https://www.halborn.com/blog/post/explained-the-solv-hack-march-2026)

### Pattern
ERC-3525 = ERC-721 + ERC-20 hybrid. `doSafeTransferIn` → mint → `onERC721Received` callback → re-enter mint before the first one completes. 22 iterations: 135 BRO → 567M BRO.

### Detection
- Slither: `erc3525_reentrancy.py` — flag ERC-3525 vault functions without a nonReentrant guard
- Manual: CEI pattern review for all vaults integrating ERC-3525

---

## R5. Slippage Check with Shared Intermediate Tokens

**Date:** April 2026 | **Victim:** Rhea Finance | **Amount:** $18.4M
**Source:** [MEXC News Rhea](https://www.mexc.com/news/1036012), [AMBCrypto](https://ambcrypto.com/rhea-finance-revises-exploit-losses-to-18-4m-confirms-slippage-flaw-as-funds-partially-recovered/)

### Pattern
A multi-step swap aggregator summed the expected outputs of each step. It did not account for reuse of intermediate tokens between steps → double-counting the same liquidity. 2 days of prep: 423 wallets, fake pools.

### Detection
- Slither: `slippage_shared_intermediates.py` — flag multi-step swaps with aggregated slippage without uniqueness tracking
- Manual: test circular paths, multi-hop with shared intermediates

---

## R6. Partial Signature Scope (Backend Underspecified Digest)

**Date:** April 2026 | **Victim:** GiddyDeFi | **Amount:** $1.3M
**Source:** [Halborn April 2026 review](https://www.halborn.com/blog/post/month-in-review-top-defi-hacks-of-april-2026)

### Pattern
The backend signed only `swap.data`. The contract accepted unsigned wrapper fields: target, token, amount, approval target. The attacker reused the signature with modified unsigned fields → drained users with allowance.

### Detection
- Slither: `signature_scope_coverage.py` — flag signature recovery where sensitive params (to/amount/token) are not in the digest
- Manual: review all EIP-712 structs vs actual function execution params

---

## R7. LayerZero v2 Insufficient DVN Diversity (KelpDAO Re-affirmed)

**Date:** April 2026 (escalated) | **Victim:** KelpDAO | **Amount:** $292M
**Source:** [Halborn KelpDAO](https://www.halborn.com/blog/post/explained-the-kelp-dao-hack-april-2026), [CoinDesk](https://www.coindesk.com/business/2026/04/19/the-usd292-million-kelp-exploit-how-it-happened-and-what-it-means-for-defi)

### Pattern (detailed update based on the Halborn breakdown)
KelpDAO used "1 verifier, 1 RPC". Lazarus: compromised 2 RPCs, DDoSed the rest → echo chamber → injected a fraudulent message. 116,500 rsETH stolen, $13B TVL exodus.

### Detection
- Slither: `layerzero_verifier_count.py` — flag setConfig calls with `requiredDVNCount < 2`
- Onchain: `layerzero_dvn_audit.py` — read UlnConfig via RPC, flag insufficient DVN setup
- Manual: check that there are at least 2 independent DVNs (LayerZero Labs + Polyhedra/Nethermind/Google Cloud)

---

## R8. Hook/Callback Without Caller Validation (Ekubo + Cork)

**Date:** May 2025 (Cork $11M), May 2026 (Ekubo $1.4M) | **Amount:** $12.4M total
**Source:** [Dedaub Cork analysis](https://dedaub.com/blog/the-11m-cork-protocol-hack-a-critical-lesson-in-uniswap-v4-hook-security/), [Phemex Ekubo](https://phemex.com/news/article/ekubo-protocol-exploit-on-ethereum-causes-14-million-loss-78961)

### Pattern
Singleton AMM architecture (Uniswap v4 / Ekubo) uses hooks/callbacks for extension. If a callback lacks an `onlyPoolManager` / `onlyCore` modifier — anyone can invoke it directly:
- Ekubo: payment callback → `transferFrom(victim, attacker, amount)` where the victim has an allowance
- Cork: hook function → manipulate pool state without authorization

### Detection
- Slither: `hook_callback_unauthorized.py` — flag external callback/hook functions with transferFrom without a caller check
- Pattern: names `paymentCallback`, `unlockCallback`, `beforeSwap`, `afterSwap`, `onERC721Received` + transferFrom + no authorization

### Almost universal pattern
One detector covers all singleton-AMM hook architectures: Uniswap v4, Ekubo, Balancer v3, any forks.

---

## R9. Unprotected Role Granting (TrustedVolumes / 1inch)

**Date:** May 7, 2026 | **Victim:** TrustedVolumes (1inch resolver) | **Amount:** $5.87M
**Contract:** `0x8CCB1ffD5C2aa6Bd926473425Dea4c8c15DE60fd`
**Exploit tx:** `0x770bc9a1f7c32cb63a5002b9ceb5c7994cd3af0fc6b2309cb32d3c46f629daa0`
**Source:** Blockaid alert, EdaFace/CryptoRank

### Pattern
A public function `addAllowedOrderSigner(address)` without access control. The attacker called it to add themselves as a trusted order signer. Then used the token approvals already granted by users to the contract to withdraw WETH/USDT/WBTC/USDC.

**The same attacker wallet as in March 2025** (Yul calldata corruption). A deliberate second attempt on TrustedVolumes via a different vector.

### How it differs from March 2025
- March 2025: Yul assembly `calldataload` pointer underflow → overwriting the resolver address
- May 2026: Missing access control on a setter → attacker added themselves to the trusted list

### Detection
- Slither: `unprotected_role_granting.py` — flag public/external functions writing to privileged mappings (allowed/signer/whitelist/trusted/operator) without access control
- Manual: review all functions that modify allowlists, check for `onlyOwner`/`onlyRole`

### Red flags during an audit
1. A public function named `add*Signer`, `set*Allowed`, `grant*`, `whitelist*`
2. A mapping whose name contains `allowed`/`signer`/`trusted`/`operator` is modified from outside
3. No modifier on a function that raises privileges

---

## R10. Fake Jetton Deposit — TON Bridge Origin Not Validated

**Date:** May 13, 2026 | **Victim:** TAC Build (TON↔EVM bridge) | **Amount:** under investigation
**Source:** @TacBuild/status/2054264393895235933 (bridge paused, investigation ongoing)

### Pattern
The TON Jetton standard (TEP-74) uses an **asynchronous message** to transfer tokens:
1. `transfer()` → the Jetton contract sends `transfer_notification` to the recipient (bridge)
2. If the bridge validates ONLY the contents of `transfer_notification` (amount, sender) without checking that the source = a legitimate Jetton contract → attack:
   - Attacker deploys a **fake Jetton** that sends an arbitrary `transfer_notification`
   - The bridge mints wrapped tokens on the EVM side
   - Real tokens are not locked → attacker creates money out of thin air

### Why only Jettons are affected (not $TON)
- **Native $TON** is transferred via the `value` field in the message — the bridge sees the real balance
- **ETH-native assets** go through different logic (EVM → TAC) — not affected
- **TON Jettons** — exactly async TEP-74 transfers, the bridge must whitelist Jetton contracts

### Detection
- Manual: check whether a whitelist/allowlist of Jetton contracts exists in the bridge
- Manual: the bridge must compare the `sender` of `transfer_notification` with the Jetton master contract address
- Code: flag any TON bridge contract where `transfer_notification` is handled without `require(sender == expectedJettonMaster)`

### Red flags when auditing a TON bridge
1. No whitelist of Jetton addresses (accepts transfer_notification from any contract)
2. The bridge doesn't store Jetton master addresses per token
3. The `transfer_notification` handler doesn't validate the caller via a `get_jetton_data()` check

### EVM analogue
The same pattern as ERC-20 with a fake `Transfer` event — if the bridge listens to an event without checking the emitter address. On TON it is sharper because of the async nature of messages.

### Relevance for HackenProof/Immunefi
All TON bridge projects (TON Bridge official, OpenTons Bridge, Orbit Bridge TON, etc.) → check the Jetton whitelist. This is **High/Critical** if the whitelist is absent.

---

## Statistics from Halborn Top 100 DeFi Hacks Report 2025

- **80.5%** of stolen funds = off-chain attacks (compromised keys, social engineering, phishing)
- Only **19%** of protocols use multisig
- **34.6%** of smart contract exploits = input validation failures
- **83.3%** of eligible exploits in 2024 = flash loan attacks

Source: [Halborn Top 100 DeFi Hacks 2025](https://www.halborn.com/reports/top-100-defi-hacks-2025)

**Implication for our workflow:** even on onchain code-only audits, always monitor the off-chain surface (admin keys, multisig threshold, frontend integrity). Without this we will miss 80% of real threats.

---

## 8. Bridge Source-Amount Conservation Class

**Dates:** Feb 2022 (Wormhole $325M), Aug 2022 (Nomad $190M), May 2026 (Verus $11.58M)
**Type:** Cryptographic verification ≠ semantic verification — attested-payload trust gap
**Cumulative loss (3 cases):** ~$521M+ across 4 years
**Cumulative bridge losses 2026 (per PeckShield, first 2 weeks May):** $328.6M across 8 bridges

### Common root cause

Bridges and attested-payload systems **verify the cryptographic integrity** of the payload (signatures, Merkle proofs, hash bindings) but **do not verify the semantic invariants** of the payload contents:

- **Wormhole 2022**: believed that a `signature_set` account existing ≡ legitimately verified
- **Nomad 2022**: believed that the default merkle root `0x00` ≡ confirmed message state
- **Verus 2026**: believed that 8/15 notary signatures over a CCE ≡ source amount validated

All three = the same conceptual gap. Different surface form, identical underlying trust mistake.

### Attack flow (Verus 2026 — canonical worked example)

1. Attacker funds wallet with 1 ETH via Tornado Cash (hours before)
2. On the Verus chain: creates a Cross-Chain Export with input=$0.01 VRSC + output instruction=$11.58M (ETH+tBTC+USDC)
3. 8/15 notaries sign a state root containing this CCE — they verify cryptographic integrity, not semantic conservation
4. On Ethereum: calls `submitImports()` (selector 0x8c49b257)
5. Bridge verifies: ✓ notary signatures (8/15), ✓ Merkle proof of CCE inclusion, ✓ hash binding to the payload, ✗ source amount conservation (NOT CHECKED)
6. `_createImports()` decodes the blob and executes payouts from reserves
7. Attacker swaps drained assets into 5,402 ETH, prepares a Tornado Cash exit

### Fix

Per Blockaid: ~10 lines of Solidity in the missing `checkCCEValues` function:
```solidity
require(sum(payouts) <= sum(verifiedSourceTotals), "amount conservation violated");
```

This is a narrow fix. Sibling targets (Wormhole post-2022 patches, Stargate custom adapters, Polkadot parachain bridges, etc.) may have the same class of bug under a different surface form.

### Action for toolkit

Good news — we already have:
- 🎭 Threat model: [`threat_models/cross_chain_source_destination_binding.yaml`](threat_models/cross_chain_source_destination_binding.yaml) — auto-applies to bridge targets
- 🎭 Sibling lens: [`threat_models/attested_amount_trust_gap.yaml`](threat_models/attested_amount_trust_gap.yaml) — broader (LRT/oracle/intent-solver)
- 🔧 Operational detector: [`bridge_tests/source_amount_grep.sh`](bridge_tests/source_amount_grep.sh) — flags entry functions without a conservation assert
- 📋 Checklist Section 1-4: [`checklists/specialized/bridge.md`](checklists/specialized/bridge.md) — manual deep review
- 🧠 Adversarial prompt: [`prompts/bridge_message_forge.md`](prompts/bridge_message_forge.md) — lone-forge + N-of-M collusion
- 📜 Audit corpus: `_known_findings.jsonl` IDs `wormhole-2022-signature-bypass`, `nomad-2022-merkle-root-init`, `verus-2026-source-amount-forge`
- 📚 Reading note: [`research/_audit_corpus/notes/verus_2026_source_amount.md`](research/_audit_corpus/notes/verus_2026_source_amount.md)
- 🎓 Learning path: [`sessions/_methodology/learning_paths/bridges.md`](../../sessions/_methodology/learning_paths/bridges.md)

### Sibling watch list (cross-link to `gap_review.md` "Open")

1. **Wormhole post-2022 patches** — the fix was narrow (only signatureSet validation); check class siblings
2. Stargate / LayerZero apps with custom adapters
3. Polkadot parachain bridges
4. Cosmos custom IBC apps (non-canonical)
5. L1↔L2 native bridges (Arbitrum, Optimism, Polygon zkBridge)
6. Intent solvers (UniswapX/CowSwap/Across) — attested execution sibling

### Sources

- Verus: [Halborn explainer](https://www.halborn.com/blog/post/explained-the-verus-ethereum-bridge-hack-may-2026), [CoinDesk](https://www.coindesk.com/markets/2026/05/18/yet-another-crypto-bridge-falls-victim-to-an-usd11-million-hack)
- Wormhole: [rekt.news](https://rekt.news/wormhole-rekt/)
- Nomad: [rekt.news](https://rekt.news/nomad-rekt/)
- 2026 bridge tally: [Protos $329M](https://protos.com/bridge-hacks-back-in-vogue-as-verus-exploit-brings-2026-total-to-329m/)

---

## R11. Validator Set Quorum Compromise (Gravity Bridge $5.4M)

**Date:** 30 May 2026 | **Amount:** ~$5.4M ($4.3M USDC, 274 ETH, $434K USDT, 14.164 PAYG)
**Chain:** Cosmos SDK chain + immutable `Gravity.sol` (`0xa4108aA1Ec4967F8b52220a4f7e94A8201F2D906`)
**Attacker:** `0x7B582033061b96cC3F9421e73a749ED7C62da1F9`, `0x4d3ca32e687e871a58b78AcAc73bE59AC37C7A47`
**Source:** [The Block](https://www.theblock.co/post/403108/cosmos-based-gravity-bridge-drained-of-5-4-million-in-suspected-key-compromise-researchers-say), [Gravity security.md](https://github.com/Gravity-Bridge/Gravity-Docs/blob/main/docs/security.md), [Code4rena 2021](https://code4rena.com/reports/2021-08-gravitybridge)

### Pattern (and the scope boundary)
M-of-N bridge: `submitBatch`/`updateValset` require validator signatures with cumulative voting
power ≥ 2/3. The root cause of the hack = **compromise of ≥2/3 of validators' ETH signing keys** →
the attacker assembled a valid quorum for `submitBatch` with their own addresses. `Gravity.sol`
worked CORRECTLY.

**Critical for bug bounty:** key theft is the DECLARED threat model (security.md states outright
"the only path = keys of >2/3"). This is **NOT a findable bug** (like Ronin 2022). Do not submit,
unless the program explicitly pays for centralization/key-custody (see `feedback_ton_self_destructive_severity`).

### What IS findable HERE (Code4rena Gravity 2021 — the real class)
- `updateValset` without re-checking the cumulative power of the new set → swap to a sub-quorum set
- no signer dedup → one validator satisfies N-of-M
- checkpoint/nonce replay; power overflow
- EVM-hardened vs Cosmos-side malleability asymmetry → freeze
- fee-on-transfer in submitBatch → accounting drift

### Detection (our toolkit)
- 🎭 `threat_models/validator_set_quorum_integrity.yaml` (auto-applies on `bridge`/`gravity`/`validator-set`/`custody`)
- 🤖 `specialized/gravity_validator_hunter.py` — Nakamoto coefficient (min keys for 2/3) + source logic
- 🔧 `hypothesis/bridge_detector.py` — recognizes Gravity (submitBatch/updateValset) + the `custody` tag
- 📋 `checklists/specialized/gravity_validator.md`

---

## R12. Liquidity Locker Privileged Backdoor (DxSale $7.3M)

**Date:** 28-29 May 2026 | **Amount:** ~$7.3M, 1,400 BNB-chain LP | **Chain:** BSC
**Attacker:** `0xC4574DDEF299e7E563971e200433e592EeaaFA69` (funded Bybit); drainer `0xc2efbd94…01e4718` (unverified, solc 0.8.33)
**Source:** [crypto.news](https://crypto.news/dxsale-exploit-drains-7-3m-in-bnb-through-hidden-contract-backdoor/), [Cointelegraph](https://cointelegraph.com/news/memecoin-platform-dxsale-drained-73m-1400-lps), [Decurity 2023](https://blog.decurity.io/dx-protocol-vulnerability-disclosure-mitigation-of-a-critical-smart-contract-exploit-bddff88aeb1d)

### Pattern
Legacy **DxLock** — a pooled liquidity locker holding the LP of thousands of projects in one contract
(unverified). A privileged owner backdoor (NOT an approval-drain, NOT reentrancy, NOT a classic key-leak):
1. Ownership quietly transferred in Aug 2025, run through ~80-89 wallets (obfuscation)
2. `setFee(1 wei)` — zeroing the cost of modifying locks
3. lock expiration set to **68 sec from the Unix epoch** → all positions are "already unlocked"
4. batch withdrawal of 1,400 LP via a drainer contract

### Findable AND reportable (proven)
Decurity reported THIS class in 2023 (`unlockToken` without a timestamp check, ~$5.2M potential).
DxSale paid **$500** and "fixed" it by raising the fee — **a configuration fix, not a structural one**
→ bypassed via the same `setFee` in 2026. (Link: `post_bounty_variant_drift.yaml` — configurational
fix = sibling alive.)

### Detection (our toolkit)
- 🎭 `threat_models/liquidity_locker_privileged_unlock.yaml` (auto on `locker`/`vesting`/`escrow`/`custody`)
- 🤖 `hypothesis/liquidity_locker_privilege_scanner.py` — mutable lock-params + owner classification
- 📋 `checklists/hypothesis/liquidity_locker_privilege.md`
- 🧠 composite `HYPOTHESES.md` H13 (+ H11 for the abandoned-legacy variant)
- 📡 `monitors/ownership_transfer_monitor.py` — ownership-transfer as a leading indicator

---

## R13. Permanent Fund Freeze via Activity-Gated Exit (HONG ICO $2M, white-hat)

**Date:** 31 May 2026 (white-hat) | **Amount:** ~$2M / 1003.62 ETH, trapped **9 years** | **Chain:** Ethereum
**Contract:** `0x9Fa8fA61A10Ff892E4EBCeB7f4e0FC684C2ce0a9` (HONG, verified, solc v0.3.5, 2016 ether.camp TheDAO-clone)
**White-hat:** [@0xFlorent_](https://x.com/0xFlorent_/status/2061070356564091258) — "first white-hat exploit on Ethereum"
**Source:** on-chain (Etherscan: successful `refundMyIcoInvestment`/`collectMyReturn` from ~48 holders; balance 1003→828 ETH)

### Pattern (a MIRROR of drain classes — not theft, but a freeze)
HONG — a DAO fund with a state machine (ICO → lock → governance → distribution → exit).
1. The ICO **did not reach `minTokensToCreate`** → the fund never locked (`isFundLocked=false`).
2. Refund `refundMyIcoInvestment()` is gated by the `notLocked` modifier (passes) + `onlyTokenHolders`.
3. **The trap:** `tryToLockFund()` is `internal`, triggered **only from `createTokenProxy()`** (token purchase).
   The terminal release branch (Case D) requires `now >= deadline` AND a fresh call of the driver.
4. The ICO died in 2016 → no purchases → the state machine is parked in a non-terminal state,
   the exit path **was orphaned and forgotten for 9 years**, until the white-hat re-activated it.
5. NB: `mgmtDistribute` (admin path) **reverts** — the unlock went through a legitimate per-investor exit, NOT through privilege.

### Findable (a structural reachability bug, not designed-trust)
This is a **liveness bug**: a legitimate exit exists in the code, but its enabling transition is unreachable
without activity that has ceased. On Immunefi/Cantina "permanent freezing of funds" = its own
Critical/High class. Distinguish from a DOCUMENTED pause/guardian (designed-trust, OOS).
Sub-distinction: *forgotten/activity-gated* (HONG) vs *privileged-unlock-only* (DxSale R12) vs
*adversary-blockable DoS-to-freeze*.

### Detection (our toolkit)
- 🎭 `threat_models/fund_liveness_terminal_state.yaml` (auto on `ico`/`vesting`/`escrow`/`auction`/`dao`/`lifecycle`/`liveness`/`custody`)
- 🤖 `advanced/state_machine_analyzer.py` — exit-gate → writers heuristic; flagged HONG `refundMyIcoInvestment <- tryToLockFund(internal)` automatically
- 📋 `checklists/hypothesis/fund_liveness_reachability.md`
- 🔭 generation Lens 10 (Liveness / activity-gated exit) + taxonomy Cat 13.6

---

## R14. Per-Block Checkpoint Staleness (Tranchess ~$95M-risk, $200K bounty)

**Date:** Jun 2026 | **Reporter:** @chainsiren | **Report:** `github.com/floranguyen0/tranchess` | **Chain:** EVM
**Class:** taxonomy Cat 9.6 — per-block idempotency-guard staleness.

### Pattern
`_checkpoint()` synchronizes `recordedSupply` with `actualBalance`, but contains a gas optimization:
if it already ran in this block (`if (lastCheckpoint >= block.timestamp) return`) — a repeated
call is silently skipped. Tranchess splits value into tranches (Queen/Bishop/Rook); rebalance
**mints extra Queen directly to the staking contract**. The attack in one block: call a function that triggers
`_checkpoint()` (snapshotting the old `recordedSupply`) → trigger rebalance (`actualBalance` grew) →
`deposit()` (the second `_checkpoint()` is skipped) → `spareAmount = actualBalance - recordedSupply`
is inflated → the attacker receives staking-shares without depositing tokens.

### Researcher approach (line of thought — reusable)
**Idempotency-guard staleness lens:** for each once-per-block optimization ask "what takes the
snapshot and can I change the real value AFTER the snapshot, but in the same block?" → find the downstream
`(real − recorded)` delta → order the operations so the snapshot is stale when the delta is read.

### Detection (our toolkit)
- 🤖 `scripts/web3/detectors/checkpoint_staleness.py` — flags a per-block skip-guard + downstream delta sink
- 📋 taxonomy Cat 9.6 (+ composite affinity 3.x accounting, 2.4 cache staleness)

---

## R15. Cross-Layer Size-Limit → Chain Halt (Axelar $1B-chain, $5k cost, $50K bounty)

**Date:** Jun 2026 | **Reporter:** @marcohextor | **Report:** `marcohextor.com/axelar-network` | **Chain:** Axelar (CometBFT/Cosmos)
**Class:** composite — taxonomy Cat 18.5 (size-limit) × Cat 18.6 (punishment without quorum guard).

### Pattern (a composite of two root causes)
1. **18.5:** validators run `vald`, vote via RPC; Tendermint default `max_body_bytes =
   1_000_000`. The attacker generates txs with thousands of events → vote payload > 1 MB → submit fails,
   the validator doesn't vote. The limit sits in the **node config, not in the contract** — invisible to a contract-only review.
2. **18.6:** Axelar **did not check the minimum quorum / systemic nature of the failure** before punishing for a missed
   vote → an infra-wide miss is still punished → maintainers are removed → the network falls below quorum → **halt**.

### Researcher approach (line of thought — reusable, this is what's valuable)
**Cross-layer limit lens:** descend BELOW the contract into node infra → read the real defaults
(CometBFT `config.toml`) → find a liveness-critical op whose serialized payload the attacker can
inflate beyond the transport limit → chain it with the punishment side: is there a guard before punishment?
Two individually weak pieces of evidence (RPC-cap + missing quorum-guard) woven together → halt on a $1B chain. A reference
cross-thread synthesis.

### Detection (our toolkit)
- 📋 `scripts/web3/checklists/specialized/cross_layer_resource_limit.md` (18.5)
- 📋 `scripts/web3/checklists/specialized/gravity_validator.md` §8 + `threat_models/validator_set_quorum_integrity.yaml` vector 6 (18.6)
- 🎯 `sessions/_methodology/live_targets_consensus.md` #9 (CometBFT vote-based siblings)
