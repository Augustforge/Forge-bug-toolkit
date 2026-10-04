# Token architecture — checklist

Use when target is a wrapped/synthetic/bridge/LST/LRT/mintable ERC-20 (or non-EVM equivalent).

**Why this checklist exists:** Echo Protocol Monad hack (19.05.2026, $76.7M nominal) — admin
key compromise + unconstrained mint + no timelock + no cap. Aanalogous patterns: Ronin ($625M),
Multichain ($130M), Harmony Horizon ($100M). All bypassed code audits because OPSEC and
centralization risk are outside smart-contract review scope.

## Role architecture

- [ ] Get list of all defined roles (DEFAULT_ADMIN_ROLE, MINTER_ROLE, PAUSER_ROLE, ...)
- [ ] For each role: query `getRoleMemberCount` + `getRoleMember(i)` for each index
- [ ] For each role member address: fetch on-chain bytecode (eth_getCode)
  - Empty (0x) → **EOA** → flag as centralization risk
  - Non-empty → identify contract type (heuristic: storage at known Gnosis Safe slots, name() check)
- [ ] Document threshold/signers if multisig (e.g., 3/5)
- [ ] **Critical flag:** DEFAULT_ADMIN_ROLE or MINTER_ROLE held by single EOA
- [ ] **High flag:** 2/2 or 2/3 multisig (low Byzantine fault tolerance)
- [ ] **Medium flag:** multisig with all signers in same physical jurisdiction / same organization

## Supply caps and rate limits

- [ ] Read `totalSupply()` and look for cap in contract:
  - `MAX_SUPPLY` / `cap()` / `maxTotalSupply()` constants
  - `mint()` modifier checking `totalSupply + amount ≤ cap`
- [ ] If no cap **AND** unrestricted MINTER_ROLE → **Critical** unbounded loss exposure
- [ ] Is there a per-tx mint cap or per-epoch rate limit?
- [ ] Is there a circuit breaker that pauses on supply growth anomaly?

## Timelock on admin operations

- [ ] Is DEFAULT_ADMIN_ROLE held by a TimelockController?
- [ ] If yes: read `minDelay()` — sufficient for incident response (≥24h)?
- [ ] Are `grantRole` / `revokeRole` operations subject to timelock?
- [ ] Are upgrade operations (if proxy) subject to timelock?

## Pause / emergency stop

- [ ] Does contract inherit from Pausable / PausableUpgradeable?
- [ ] Is PAUSER_ROLE separate from DEFAULT_ADMIN_ROLE?
- [ ] Is PAUSER held by an independent guardian (security council)?
- [ ] What does pause stop? mint? transfer? burn? all?

## Upgrade safety

- [ ] Is this a proxy contract (ERC-1967, UUPS, transparent)?
- [ ] If UUPS: who can call `upgradeTo`? Same single key as admin?
- [ ] Are storage slots `__gap` padded for future variables?
- [ ] Is `initialize()` protected (initializer modifier + check on implementation)?

## Cross-protocol impact

- [ ] Is this token accepted as collateral in any lending protocol on the same chain?
  - Defillama API by chain → list lending protocols → check supported collaterals
- [ ] Is this token in any AMM pool with significant liquidity?
- [ ] If admin compromise → estimate realized loss = min(mint capacity, available liquidity + lending depth)

## Off-chain attack surface (qualitative)

- [ ] Are key holders publicly known? (Doxxed founders, anonymous, foundation?)
- [ ] Are signing keys on hardware wallets / HSM (verifiable through public statements)?
- [ ] When was last key rotation?
- [ ] Has the team publicized OPSEC practices (e.g., bug bounty for OPSEC issues)?

## Severity rubric for findings

- DEFAULT_ADMIN_ROLE or MINTER_ROLE on single EOA + no timelock + no cap + integrated as collateral → **Critical** (Echo pattern)
- Single EOA admin + timelock OR cap → **High** (defense-in-depth missing)
- Multisig but threshold ≤ 2/3 OR same-org signers → **High**
- All defenses present but pauser = admin (no independent guardian) → **Medium**

## Tools

- `dapphunt/hypothesis/role_centralization_scanner.py` — automates role member classification
- Etherscan / explorer "Read Contract" tab for AccessControl roles
- `cast call <token> "getRoleMember(bytes32,uint256)(address)"` — query individual members
- Tenderly / Phalcon for simulating admin tx flows
