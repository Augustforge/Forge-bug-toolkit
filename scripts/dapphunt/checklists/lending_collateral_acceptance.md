# Lending / CDP collateral acceptance — checklist

Use when target is a lending protocol, money market, CDP, or any protocol that accepts
deposited tokens as backing for borrowed liabilities.

**Why this checklist exists:** Echo Protocol Monad chain (19.05.2026) — Curvance on Monad
accepted freshly-minted eBTC as collateral without verifying real BTC backing. $816K
realized from a $76.7M nominal mint. Lending side was the **drain amplifier**: without
collateral acceptance, fake mint = unrealized loss.

## Collateral whitelist process

- [ ] How does a new collateral asset get added? Manual DAO vote, automated, permissionless?
- [ ] If DAO-governed: is there a timelock + grace period between vote and activation?
- [ ] If automated (e.g., "any token with >$1M TVL"): what's the criteria and bypasses?
- [ ] Document last 5 added collaterals and the process used

## Oracle configuration per asset

For each accepted collateral, document:

- [ ] Oracle type (Chainlink direct feed, Pyth, internal TWAP, custom adapter, sequencer?)
- [ ] Update frequency / heartbeat
- [ ] Deviation threshold (when does oracle refresh?)
- [ ] Source of truth — what does the oracle actually measure?

## Backing verification for wrapped/synthetic collateral

This is the **Echo amplifier vector**. For any wrapped/bridged/synthetic asset accepted:

- [ ] Does the oracle verify `totalSupply ≤ backing_reserve` in any way?
- [ ] Is there a Chainlink Proof-of-Reserves feed for this asset?
- [ ] If wrapped from another chain: is there a parity audit mechanism?
- [ ] **Critical flag:** wrapped/synthetic collateral accepted with **price-only oracle** and admin of underlying is EOA

## Borrow / supply caps

- [ ] Per-collateral supply cap (max amount can be deposited as collateral)?
- [ ] Per-collateral borrow cap (max amount can be borrowed against this collateral type)?
- [ ] Global protocol cap?
- [ ] If 0 / uint256.max → no cap → max realized loss = full liquidity
- [ ] If finite → max realized loss = min(borrow cap, available liquidity)

## Oracle manipulation surface

- [ ] Does any oracle read from a DEX pool the attacker could be sole LP of?
- [ ] TWAP window — too short on low-liquidity assets allows manipulation
- [ ] Single oracle source vs aggregated? Median-of-3 vs naive?
- [ ] Sequencer uptime check (Chainlink L2 Sequencer feed) — stale price during outage?

## Liquidation safety

- [ ] What happens if oracle reports stale or zero price?
- [ ] Is there fallback to secondary oracle?
- [ ] Can liquidations be triggered with manipulated oracle?
- [ ] Is there liquidation pause if oracle out of bounds?

## Cross-protocol integration check

- [ ] What other protocols accept the same collateral?
- [ ] Are there yield strategies (e.g., Yearn-style vaults) that auto-deposit user funds here?
- [ ] If this protocol is compromised, what's the downstream blast radius?

## Severity rubric

- Lending accepts wrapped/synthetic collateral + price-only oracle + admin of underlying is EOA → **Critical** (Echo amplifier)
- No per-collateral borrow cap on wrapped asset → **Critical** (unbounded amplifier)
- Oracle reads from DEX pool with <$100K liquidity → **High** (manipulation surface)
- Liquidation doesn't pause on stale oracle → **High**
- Permissionless collateral listing without grace period → **High** (governance race)

## Tools

- `cast call <pool> "getReserveData(address)"` for Aave-style
- `cast call <comptroller> "markets(address)"` for Compound-style
- Defillama API: `/protocol/{slug}` to enumerate supported collaterals
- Chainlink PoR feeds: https://data.chain.link/feeds (filter by "Proof of Reserve")
- `dapphunt/hypothesis/role_centralization_scanner.py` — pair with token side check
