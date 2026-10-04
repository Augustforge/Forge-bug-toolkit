# Upgradeable proxy — checklist

Use when target uses upgradeable contracts (ERC-1967 proxy, UUPS, transparent,
beacon, or custom delegatecall pattern).

**Why this checklist exists:** Audius hijack ($1M, 2022) — initialize() callable
again. Wormhole near-miss ($300M) — implementation contract self-destructable.
OZ CVE-2023-26488 — reinit chain bug. This class is high-severity AND scanner-able.

**EIP-1967 storage slots to memorize:**
- Implementation: `0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc`
- Admin: `0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103`
- Beacon: `0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50`

## Identify proxy type

- [ ] Read EIP-1967 implementation slot via `eth_getStorageAt`
- [ ] Read EIP-1967 admin slot
  - Non-zero admin → likely TransparentUpgradeableProxy
  - Zero admin → likely UUPS (admin lives in implementation logic)
- [ ] Read EIP-1967 beacon slot
  - Non-zero → BeaconProxy
- [ ] Check bytecode for delegatecall pattern; if none of above slots → custom proxy (audit carefully)

## Implementation safety

- [ ] Fetch implementation address (from EIP-1967 slot)
- [ ] Call `owner()` / `getRoleMember(DEFAULT_ADMIN_ROLE, 0)` on implementation directly
  - If returns valid address (not zero) → implementation is initialized → Wormhole vector OPEN
  - If returns zero / reverts → implementation is "locked" via `_disableInitializers()`
- [ ] Try `initialize(...)` on implementation directly with attacker as owner (foundry fork)
  - Success → Critical, you can take over implementation
- [ ] If take-over succeeds, can attacker `selfdestruct` the implementation?
  - Look for SELFDESTRUCT opcode reachable from owner-only function
  - Cancun-era note: SELFDESTRUCT semantics changed, but legacy bytecode still callable

## Initializer chain audit

- [ ] Search source for `initializer`, `reinitializer(N)`, `onlyInitializing` modifiers
- [ ] List all reinitializer(N) usages — must be monotonically increasing N
- [ ] Read current `_initialized` storage value (OZ stores it in slot 0 of Initializable base)
- [ ] Any reinitializer(N) where N ≤ current `_initialized` → re-entry possible

## Storage layout safety

If the proxy has been upgraded historically:
- [ ] Find historical implementations:
  - Etherscan "Read as Proxy" history
  - OR query past `Upgraded(address)` events: `eth_getLogs` with topic0 = `bc7cd75a20ee27fd9adebab32041f755214dbc6bffa90cc0225b39da2e5c2d3b`
- [ ] For each version: extract storage layout (`forge inspect <Contract> storage-layout` from source if available)
- [ ] Diff layouts:
  - New variables added in middle → slot collision → state corruption
  - Variable type changed (uint128 → uint256) → consumes more slots → shift
  - Variable removed but slot not preserved → shift
  - __gap not properly consumed (added after gap) → shift

## Upgrade authority

- [ ] For UUPS: who can call `upgradeTo`? Read `_authorizeUpgrade` modifier
  - onlyOwner → who's owner? EOA / multisig / timelock?
  - onlyRole → which role? trace holders
- [ ] For transparent: read ProxyAdmin address
  - Call ProxyAdmin.owner()
  - Classify as EOA / multisig / timelock (use `role_centralization_scanner.py`)
- [ ] For beacon: read beacon owner
- [ ] **Critical:** single EOA upgrade authority without timelock = arbitrary state hijack on key compromise

## Initialization race (deployer phase)

If target is freshly deployed (last 30 days):
- [ ] Check tx history for proxy contract — was initialize() called by deployer?
- [ ] If initialize() not yet called → anyone can call → takeover race
- [ ] Watch for: factory contract that creates proxy but forgets to initialize in same tx

## Special patterns

### Diamond / EIP-2535
- [ ] Read facet cuts (`facets()`, `facetAddresses()`)
- [ ] Who can call `diamondCut`? (often most powerful function in protocol)
- [ ] Selectors clash detection across facets

### Beacon proxy
- [ ] Beacon owner = effective upgrader for ALL proxies pointing at it
- [ ] One key compromise = N proxies hijacked

### MinimalProxy (ERC-1167 clones)
- [ ] Clones are NOT upgradeable but inherit implementation forever
- [ ] If implementation has bug, every clone has bug
- [ ] Check if implementation is mutable (sometimes registry-backed)

## Common audit gaps

- [ ] Did the audit cover the LATEST implementation, or just an old one?
- [ ] Were upgrade scripts (deployer code) audited?
- [ ] Was the deployment of the proxy itself audited? (initialize race vulnerability)

## Severity rubric

- Implementation contract callable directly + has selfdestruct path → **Critical** (Wormhole pattern)
- initialize() callable with no protection → **Critical** (Audius pattern)
- Single EOA can call `upgradeTo` without timelock → **Critical**
- Storage layout drift confirmed across upgrades → **Critical** (state corruption)
- reinitializer(N) with N ≤ current → **High**
- __gap consumed incorrectly → **High** (latent corruption)
- ProxyAdmin owner is multisig but 2/3 → **High**

## Tools

- `dapphunt/hypothesis/proxy_reinit_scanner.py` — scanner for slot reads + impl probe
- `cast storage <PROXY> 0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc` — implementation slot
- `forge inspect <Contract> storage-layout` — when source available
- `slither <repo> --print upgradeability-checks`
- Etherscan "Read as Proxy" → implementation history

## References

- EIP-1967: https://eips.ethereum.org/EIPS/eip-1967
- EIP-1822 (UUPS): https://eips.ethereum.org/EIPS/eip-1822
- OZ Initializable v4.8.3+: https://github.com/OpenZeppelin/openzeppelin-contracts/security/advisories/GHSA-9c22-pwxw-p6hx
- Wormhole near-miss: https://blog.openzeppelin.com/wormhole-uninitialized-proxy-bugfix-review
- Audius post-mortem: https://blog.audius.co/article/audius-governance-takeover-post-mortem
