# Composite Hypothesis Catalog

**Purpose:** threat_models/ describe *point* surfaces. This catalog describes *chains* —
2-to-N threat models composed into a complete attack. Hunters work top-down (which chain
am I testing?), not bottom-up (which surface might be present?).

**How to use:**
1. Pick a hypothesis that matches the target's profile (tags overlap).
2. Walk the **chain** — each link is a threat_model with its own verification.
3. If any link breaks (mitigation present), the chain doesn't compose → move on.
4. If all links hold, you have a high-confidence drain/abuse primitive — write reproducer.

**Reference findings** column shows real incidents that match each hypothesis. Use these
when writing reports — pattern recognition is half the submission battle.

---

## H1. Unconstrained Minter → Fake Collateral Drain

**Pattern**: Wrapped/synthetic/LST/bridge token with weak admin model deployed to a
chain with active lending integrations.

**Chain**:
1. [token_architecture] MINTER_ROLE / DEFAULT_ADMIN_ROLE on EOA (no multisig)
2. [token_architecture] No supply cap or per-epoch rate limit
3. [token_architecture] No TimelockController on role changes
4. [cross_protocol_collateral_trust] Lending protocol on same chain accepts this token as collateral
5. [cross_protocol_collateral_trust] Lending oracle is price-only (no PoR / backing verification)

**Threat models**: `compromised_admin_unconstrained_mint` + `cross_protocol_collateral_trust`

**Verification**:
- Run `role_centralization_scanner.py --token <wrapped_addr>`
- If admin/minter is EOA → continue
- Enumerate lending protocols on chain (defillama API)
- For each: check if wrapped token in collateral list + read oracle config

**Severity**: Critical if all 5 hold, ≥High at 3/5

**Reference findings**:
- Echo Protocol Monad (19.05.2026, $76.7M nominal / $816K realized)
- Ronin Bridge (2022, $625M)
- Multichain (2023, $130M)

**Pre-emptive bug bounty angle**: even if admin not yet compromised, the *architecture
itself* warrants a Critical centralization-risk submission to programs that accept that
class (Immunefi often, HackenProof per-program).

---

## H2. Frontend Clone → Permit2 Phish → Asynchronous Drain

**Pattern**: dApp with permissive auth provider wildcards spawns clone subdomain;
clone issues Permit2 signatures to attacker spender; victim loses tokens hours later
without correlating to the signing event.

**Chain**:
1. [auth_provider_wildcard] Wildcard `*.{domain}` in Privy/Magic/Web3Auth allowed_domains
2. [dapp_clone_detector] Clone subdomain accessible + matches Privy app ID
3. [iframe_trust_composition] Clone lacks X-Frame-Options (clickjacking enabler)
4. [permit2_blind_signature_phishing] Clone requests Permit2 with attacker-controlled spender
5. [permit2_blind_signature_phishing] Wallet UI doesn't decode spender → blind signing

**Threat models**: `auth_provider_wildcard` + `dapp_clone` + `iframe_trust_composition` + `permit2_blind_signature_phishing`

**Verification**:
- Run `auth_provider_probe.py` → wildcard found
- Run `dapp_clone_detector.py` → clones enumerated
- Test signing flow on a clone with mock provider
- Decode signature: spender is attacker?

**Severity**: Critical (drain primitive on real users)

**Reference findings**:
- SynFutures 2026-05-20 (clickjacking + Privy wildcard; HackenProof submission)
- Inferno Drainer, Angel Drainer industrialization

**This is THE chain the SynFutures finding actually proves out — codify and replay against every Privy-using dApp.**

---

## H3. Wormhole-Pattern Implementation Hijack

**Pattern**: UUPS proxy with uninitialized implementation. Implementation has
selfdestruct path. Anyone calls `initialize()` on impl → becomes owner → selfdestructs
implementation → proxy bricked (or worse, gets pointed at malicious impl via UUPS).

**Chain**:
1. [upgradeable_proxy_reinit_collision] Proxy is UUPS (admin slot empty, impl slot set)
2. [upgradeable_proxy_reinit_collision] Implementation contract directly callable; owner()==0
3. [upgradeable_proxy_reinit_collision] Implementation has `_authorizeUpgrade` callable by owner
4. [upgradeable_proxy_reinit_collision] Implementation reachable selfdestruct OR impl can swap proxy's logic

**Threat model**: `upgradeable_proxy_reinit_collision`

**Verification**:
- Run `proxy_reinit_scanner.py --proxy <addr>`
- Check `implementation_initialized: false`
- Foundry fork: simulate calling initialize() with attacker as owner
- If success → write reproducer

**Severity**: Critical

**Reference findings**:
- Wormhole 2023 ($300M near-miss, whitehat saved)
- OpenZeppelin Initializable v4.8.3 CVE

**Where to find**: any UUPS proxy where deployer never explicitly disabled initializers
on the implementation. Common in pre-OZ-v4.9 codebases.

---

## H4. Hundred-Pattern Vault Inflation

**Pattern**: ERC-4626 / Compound v2 cToken-fork vault with balanceOf-based totalAssets,
no virtual offset, no dead-share burn. Empty market (totalSupply==0) listed as collateral.
Attacker depositing 1 wei → donating 1e18 → second depositor receives 0 shares.

**Chain**:
1. [erc4626_vault_inflation] Vault accounting is balanceOf-based
2. [erc4626_vault_inflation] No initial dead shares burn / virtual offset
3. [erc4626_vault_inflation] totalSupply == 0 OR low enough for manipulation
4. [erc4626_vault_inflation] Vault accepts deposits openly (no allowlist)

**Threat model**: `erc4626_vault_inflation`

**Verification**:
- Run `erc4626_donation_scanner.py --vault <addr>`
- Check accounting_style == "balance_of"
- Foundry fork reproducer: deposit 1 wei, transfer 1e18, second depositor

**Severity**: Critical if pool active + empty

**Reference findings**:
- Hundred Finance (2023, $7M)
- Sherlock/Spearbit contest findings (20+ instances, 2023-2024)

**Where to find**: every protocol that forked Compound v2 OR pre-OZ-v4.9 ERC4626 OR
custom vaults built without inflation awareness.

---

## H5. EIP-7702 One-Signature EOA Takeover

**Pattern**: Pectra-era dApp requests `wallet_signAuthorization` (or wraps in
`eth_sendTransaction` type 0x04) with attacker-controlled delegate address. User signs
once → entire EOA delegates code to drain contract → permanent compromise until
revocation.

**Chain**:
1. [eip7702_authorization_abuse] dApp triggers EIP-7702 authorization request
2. [eip7702_authorization_abuse] Delegate address is unverified / attacker-controlled
3. [eip7702_authorization_abuse] chainId=0 OR not bound to current chain
4. [eip7702_authorization_abuse] Wallet UI doesn't decode delegate (blind sig)
5. [eip7702_authorization_abuse] Wallet has no revocation UI → permanent

**Threat model**: `eip7702_authorization_abuse`

**Verification**:
- Mock provider captures `eth_sendTransaction` with authorizationList
- Decode each auth entry
- Check delegate verification

**Severity**: Critical (one signature = full EOA control)

**Reference findings**:
- Q3 2025 drainer kit additions (research demos)
- Pectra mainnet activation 2025-05-07

**Where to find**: any dApp explicitly advertising "smart EOA" / "gasless" via 7702.

---

## H6. Bridge Validator Compromise Cascade

**Pattern**: Cross-chain bridge with N-of-M validator set where N is low (≤5),
signers are not diversified (same org / public attribution / OPSEC questionable).
Compromise of N signers → full bridge drain.

**Chain**:
1. [bridge_admin_compromise_chain] Validator set threshold ≤ 5
2. [bridge_admin_compromise_chain] Signers not diversified (same org / shared OPSEC)
3. [bridge_admin_compromise_chain] Mint authority not separated from message verification
4. [bridge_admin_compromise_chain] No independent pauser
5. [bridge_admin_compromise_chain] No on-chain supply parity check

**Threat model**: `bridge_admin_compromise_chain`

**Verification**:
- Read bridge contract validator set
- OSINT on signers (LinkedIn, Twitter, key rotation events)
- Check pauser role separation

**Severity**: Critical at scale (≥$10M TVL)

**Reference findings**:
- Ronin (2022, $625M, 5/9)
- Harmony Horizon (2022, $100M, 2/5)
- Multichain (2023, $130M, MPC compromise)

**Where to find**: long-tail bridges that aren't LayerZero/CCIP/Hyperlane. Custom mint+lock bridges
on smaller chains. Look for "we run the bridge ourselves" tone in docs.

---

## H7. Oracle Manipulation → Vault Liquidation / Lending Drain

**Pattern**: Lending/vault uses oracle that reads from a low-liquidity DEX pool.
Attacker swaps a large amount → moves TWAP/spot → triggers favorable liquidation OR
borrows against inflated collateral.

**Chain**:
1. [cross_protocol_collateral_trust] Oracle reads DEX TWAP or spot
2. [cross_protocol_collateral_trust] Pool liquidity < manipulation cost (≤$100K is danger zone)
3. [cross_protocol_collateral_trust] No per-collateral borrow cap (or cap too high vs pool)
4. [cross_protocol_collateral_trust] TWAP window too short (<30 blocks) on volatile asset

**Threat model**: `cross_protocol_collateral_trust`

**Verification**:
- Read oracle config; find DEX pool source
- Check pool TVL on DexScreener
- Calculate cost to move price by X%; compare to potential borrow gain
- Foundry fork: simulate manipulation

**Severity**: High-Critical depending on profitability

**Reference findings**:
- Multiple Compound v2 fork oracle manips (2021-2024)
- bZx (2020), Cream Finance (2021 — $130M), Mango Markets (2022, $114M)

**Where to find**: any lending protocol with small-cap collateral, especially on
new chains where DEX liquidity is low (Monad, Berachain, hyper-EVM L2s).

---

## H8. Audit Drift → Post-Deploy New Bug Introduced

**Pattern**: Protocol got audited 6+ months ago. Substantial commits to contracts
since audit. New surface introduced (oracle change, role addition, integration with
new lending). Audit doesn't cover the drift.

**Chain**:
1. [behavioral] Last public audit > 6 months ago
2. [behavioral] Recent on-chain upgrade(s) — find Upgraded events
3. [behavioral] Audit scope explicitly limited to pre-upgrade commits
4. [any] Drift introduces new bug in the new code

**Threat models**: meta-hypothesis — combine with technical models based on what changed

**Verification**:
- Find audit reports on protocol website / Cyfrin / OpenZeppelin / Spearbit
- Read scope section; note pinned commit hash
- Compare to current deployed bytecode (etherscan diff)
- Identify diff classes (new functions, modified math, new roles)
- Apply appropriate technical threat models to each diff class

**Severity**: variable (depends on what drift introduced)

**Reference findings**:
- Numerous; recurring pattern in DeFi rather than one canonical example

**Where to find**: protocols showcasing "audited by X" but with substantial post-audit dev.
Particularly common after token launches when team rushes features.

---

## H9. Paymaster Cross-Chain Sig Replay → Sponsorship Drain

**Pattern**: ERC-4337 paymaster signs UserOp sponsorship without chainId binding.
Same paymaster contract deployed to multiple chains. Attacker captures sig on chain X
(via legit interaction), replays on chain Y where paymaster has fresh deposit.

**Chain**:
1. [erc4337_paymaster_grief] Paymaster verifies sig in validatePaymasterUserOp
2. [erc4337_paymaster_grief] Sig hash missing chainId
3. [erc4337_paymaster_grief] Paymaster deployed to ≥2 chains with same signer
4. [erc4337_paymaster_grief] No per-sender rate limit on either chain

**Threat model**: `erc4337_paymaster_grief`

**Verification**:
- Capture sponsorship sig on chain X (normal flow)
- Inspect paymaster contract on chain Y (must have ETH deposit)
- Submit UserOp with same sig to bundler on chain Y
- Observe paymaster deposit decrease

**Severity**: High (drain rate = paymaster runway)

**Reference findings**:
- Pimlico paymaster advisories 2024-2025

**Where to find**: any verifying-paymaster used across chains. Common with multi-chain dApps.

---

## H11. Multi-Chain Ghost Surface Drain (Transit pattern)

**Pattern**: Protocol deployed across many chains with multi-version contracts.
Old versions deprecated but never killed/paused. User approvals from years ago
remain active. Attacker re-exploits old vulnerability on an abandoned contract
years after the team thought the issue was "fixed".

**Chain**:
1. [ghost_contract_legacy_approvals] Protocol has multi-version contract history (V1/V2/V3 or "old/new")
2. [ghost_contract_legacy_approvals] Deprecated contract still has bytecode (not selfdestructed)
3. [ghost_contract_legacy_approvals] paused() / killed() returns false OR doesn't exist
4. [ghost_contract_legacy_approvals] Live user approvals still present (allowance() > 0 across sample holders)
5. [dex_aggregator_arbitrary_call] Old contract has the arbitrary-call vulnerability that was the original exploit cause

**Threat models**: `ghost_contract_legacy_approvals` + `dex_aggregator_arbitrary_call`

**Verification**:
- Enumerate ALL deployed contracts across ALL chains the protocol operates on (docs + GitHub commit history + explorer deploy tx scanning)
- For each: `ghost_contract_scanner.py --rpc $RPC --ghost <addr> --sample-holder <whale1> ...`
- Score by `risk_score` field; anything ≥50 = active drain primitive

**Severity**: Critical if sum of allowances × probability_of_re-exploit > $100K

**Reference findings**:
- **Transit Finance 2022→2026**: same vulnerability re-exploited 4 years later on deprecated TRON contract → $1.88M (would have been more on bigger chain)
- **SwapNet (Jan 2026)**: $13.4M; live contract with arbitrary-call class
- **Aperture Finance (Jan 2026)**: $3.67M; same class
- **Dexible (2023)**: $2M; same class

**Pre-emptive bug bounty angle**: Even without live exploitation, this is a Centralization / Abandoned Surface finding. HackenProof and Immunefi often accept it as High when:
1. Approval surface > $100K
2. No publicly available revocation flow
3. Bug bounty program scope doesn't explicitly exclude legacy contracts

**Where to find**: ANY protocol with multi-version deploys. DEX aggregators are the canonical example (1inch, ParaSwap, OpenOcean, KyberSwap, Transit, Rango, Bungee, LiFi, Socket). Every one of them deployed many router versions across chains. **Also: legacy liquidity lockers** (DxSale/DxLock, PinkSale, Unicrypt, Team Finance) — abandoned locker contracts still holding pooled LP with a transferred/active owner are a soft target (DxSale 2026 $7.3M); pivot to H13 for the privileged-unlock mechanics.

**Speed**: scan 50 aggregators × 5 chains × 4 tokens × 10 holders = ~10,000 RPC calls = one evening with parallel batching. ROI per hour is among the highest in dapphunt toolkit.

---

## H12. DEX Aggregator Arbitrary-Call Drain (Live Contract)

**Pattern**: Active aggregator/router contract accepts `(address target, bytes data)` parameters without target/selector whitelist. User who pre-approved the router has tokens drainable via crafted call.

**Chain**:
1. [dex_aggregator_arbitrary_call] Router exposes function with `(address, bytes)` signature
2. [dex_aggregator_arbitrary_call] target argument is NOT whitelisted to approved DEX list
3. [dex_aggregator_arbitrary_call] data argument NOT restricted to swap selectors
4. [dex_aggregator_arbitrary_call] Router has live ERC-20 approvals from many users (which is its core function)

**Threat model**: `dex_aggregator_arbitrary_call`

**Verification**:
- Decompile router contract (or read verified source)
- grep for function signatures matching `\(.*address.*bytes.*\)`
- For each match: trace `target` — is there `require(approvedDex[target])` or equivalent?
- For each match: trace `data` — is selector validated?
- If neither check present → drain primitive
- Reproducer: foundry fork → spoof user approve(router, MAX) → craft calldata = `transferFrom(user, attacker, balance)` packed → call router with target=USDC, data=that calldata → observe drain

**Severity**: Critical (TVL-scale, since every router user is exposed)

**Reference findings**:
- Transit Swap 2022 ($23-29M)
- SwapNet 2026 ($13.4M) — BlockSec analysis explicitly called this class
- Aperture Finance 2026 ($3.67M)
- Dexible 2023 ($2M)

**Where to find**:
- DEX aggregators with `multicall(bytes[])` patterns are common surface
- Cross-DEX routers that proxy to underlying pools without selector restriction
- Bridge+swap combiners (Bungee, Rango, Socket) — composability hops increase surface
- Closed-source aggregator contracts (BlockSec called the SwapNet case "$17M closed-source smart contract exploit")

**Pre-flight check**:
```
1. Open contract on Etherscan; is source verified?
   - If no: decompile via dedaub.com / pannouilh.com → look for selector 0x87395540 (callBytes), 0xac9650d8 (multicall), 0x1cff79cd (execute)
   - If yes: grep for `(address, bytes)` signatures
2. Find user approvals: scan allowance(<top_holders>, <router>) for major tokens
3. If both findings hit → high-confidence H12 candidate
```

---

## H10. Fresh-Chain Surface Velocity

**Pattern**: Newly-launched chain (≤6 months on mainnet) has young protocols with
OPSEC-immature teams. Many protocols ship without multisigs / timelocks "to move fast."
First incidents come from centralization, not code bugs.

**Chain**: meta-hypothesis — apply other chains' threat models with elevated severity weighting

**Where to find** (2026):
- Monad mainnet (launched 24.11.2025) — first big incident: Echo, 19.05.2026
- Berachain (launched 02.2025) — many young protocols
- Hyperliquid L1 (mainnet 2024) — perp / vault primitives
- Each new L1/L2 with TVL inflow

**Verification**:
- Apply token_architecture + cross_protocol_collateral_trust checklists to top 10 TVL projects
- Look for EOA admins, no timelocks, no caps
- Score risk; submit pre-emptive centralization findings or wait for compromise

**Severity**: Critical at scale; even single architectural finding can be High on right program

**Reference**: Echo Protocol Monad (19.05.2026) is the canonical 2026 example

---

## H13. Liquidity Locker Privileged Unlock → Pooled LP Drain

**Pattern**: A pooled-custody liquidity/vesting/escrow locker holds many users' LP under
an "immutable lock" promise, but owner-controlled parameters (fee, unlock timestamp,
emergency withdraw) are mutable with no timelock. Owner — original, transferred, or
compromised — releases everyone's funds at once.

**Chain**:
1. [liquidity_locker_privileged_unlock] Custody is POOLED (one contract holds many projects' LP)
2. [liquidity_locker_privileged_unlock] Owner-only `setFee`/`setUnlockTime`/`extendLock` mutates EXISTING locks (not just new ones)
3. [liquidity_locker_privileged_unlock] `unlockTime` backdatable to past/epoch OR emergency-withdraw bypasses per-user records
4. [liquidity_locker_privileged_unlock] Owner is EOA / low-threshold Safe / transferred / abandoned (no timelock)
5. [ghost_contract_legacy_approvals] (legacy variant) contract abandoned but still holds TVL

**Threat models**: `liquidity_locker_privileged_unlock` (+ `ghost_contract_legacy_approvals` for the abandoned-legacy variant)

**Verification**:
- Run `liquidity_locker_privilege_scanner.py --source <repo>` → mutable-param + emergency-withdraw flags
- Run `liquidity_locker_privilege_scanner.py --rpc <rpc> --contract <addr>` → owner classification
- Read `OwnershipTransferred` history (leading indicator) — silent transfer + dead project + live TVL
- Foundry fork: deposit as victim → as owner `setUnlockTime(past)`/`setFee(1)` → withdraw victim LP

**Severity**: Critical if owner can release others' pooled LP; High for EOA-owner centralization (program-dependent — route via triage monetization)

**Reference findings**:
- **DxSale / DxLock 2026** ($7.3M, 1,400 LPs): `setFee(1 wei)` + lock expiration backdated to 68s-after-epoch → batch drain. Ownership silently transferred Aug 2025, hopped ~80 wallets.
- **DxLock / Decurity 2023** (~$5.2M averted, $500 bounty): `unlockToken` w/o timestamp check; "fix" = raise fee (configurational) → bypassed via setFee in 2026. **Proves the class is findable & reportable.**

**Pre-emptive bug bounty angle**: even without active exploitation, owner-mutable lock
params over pooled third-party custody is a centralization finding where the program
accepts that class (Immunefi/Cantina common; HackenProof per-program).

**Where to find**: launchpad / locker platforms (DxSale, PinkSale, Unicrypt, Team Finance)
and their LEGACY contracts still holding TVL. Tags: `locker`, `liquidity_lock`, `custody`.

---

## H14. Permissionless On-Chain Metadata → AI Feature Injection → Agentic Drain

**Pattern**: dApp embeds an LLM feature (tx-explainer / risk narrative / agentic wallet)
that ingests attacker-controllable on-chain strings. Attacker deploys a token whose
`name`/`symbol`/`tokenURI` carries a prompt-injection payload (smuggled in invisible
Unicode to beat any keyword filter). When a victim views/handles that token, the LLM
obeys the injected instruction — at best a false "safe/verified" verdict, at worst an
agentic assistant that auto-executes a transfer or pre-fills a poisoned signing payload.

**Chain**:
1. [ai_agent_prompt_injection] dApp has an LLM feature reading on-chain metadata (scanner: `has_ai_feature`)
2. [ai_agent_prompt_injection] Input sanitization is visible-keyword-only — no Unicode normalization (NFKC / Cf-strip)
3. [ai_agent_prompt_injection] (verdict tier) LLM output is presented as authoritative ("verified / safe") → user signs
4. [ai_agent_prompt_injection] (agentic tier) Assistant can build/sign/send AND execute lacks per-action confirm → attacker-chosen transfer
5. [permit2_blind_signature_phishing] (optional compose) poisoned signing payload routes an allowance/transfer to attacker spender

**Threat models**: `ai_agent_prompt_injection` (+ `permit2_blind_signature_phishing` for the signing-poison variant)

**Verification**:
- Run `core/ai_prompt_injection_probe.py --target <url>` → confirm AI feature + untrusted sources + agentic sinks
- (Public release: the sendable injection payload catalog is withheld — supply your own scoped, benign-canary payloads if authorized)
- Deploy a test ERC-20 with `.name()` = a benign canary payload on a cheap chain
- Trigger the dApp's AI feature; if canary echoes → injection lands; if agent stages/sends a transfer → drain tier
- **Benign canary only; in-scope target AI features only; never platform/triage AIs**

**Severity**: Critical if agentic auto-execute or signing-payload poison; High if LLM verdict drives a sign the user would otherwise reject; Medium if attacker content merely rendered as authoritative

**Reference findings**:
- **ShapeShift agenticChat (09.06.2026)** — auto-execute send/swap without per-action confirm + "scheduled/approved" framing bypass (our High/BAC)
- **SynFutures (2026)** — permissionless on-chain `symbol()` as the same attacker-controlled source-of-truth
- ASCII/tag-block Unicode smuggling + zero-width interleave (filter-bypass research)

**Where to find**: any dApp advertising "AI explains your transaction", "AI risk score",
or an agentic / chat-to-execute wallet. Tags: `ai_assistant`, `agentic_wallet`,
`tx_explainer`, `has_ai_feature`.

---

## How to add a new composite hypothesis

1. Identify 2+ threat models that compose
2. Find ≥1 real-world incident that matched the chain
3. Write the chain with explicit links to underlying threat models
4. Add verification steps that are *concrete* (scanner commands, not "audit X")
5. Include severity rubric
6. Slot into appropriate position in this file (H-numbers do NOT need to be ordered)

## Hypothesis quality criteria

A good composite hypothesis:
- Has 2-5 links (not 1, not 10)
- Each link is verifiable independently
- Composes to a *primitive* (drain, takeover, denial) not a "potential issue"
- Maps to a real incident (or has a clear pre-emptive justification)
- Tells the hunter HOW to test, not WHAT to think

A bad composite hypothesis:
- Vague ("might be issues with X")
- Untestable
- Requires assumption stacking ("if X and if Y and if Z and ...")
- No reference incident AND no concrete pre-emptive case
