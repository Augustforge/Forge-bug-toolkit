# Threat Actor Models — Feasibility Tiers

Used in J4 (Economic Model Analysis) to determine finding severity.

**Key question**: "Which actor tier can execute this attack?"

If only a nation-state can exploit → severity Low (theoretical). If a script kiddie can → Critical (immediate risk).

---

## Tier Definitions

### T1: Script Kiddie ($0-1k capital)
- **Skills**: Can run a ready-made exploit / replay a public attack
- **Tools**: Etherscan, MetaMask, basic Foundry knowledge
- **Capital**: Can spend $0-1000 on gas + small deposits
- **Time**: Hours

**What's accessible**:
- Public exploit replay
- Frontrunning known vulnerable patterns
- Basic phishing surfaces (Permit2 traps)
- Liquidity sandwich on mempool

**What's NOT accessible**:
- Custom contract exploits
- Flash loan complex chains
- Cross-chain coordination

**Severity weight**: bugs exploitable by T1 → **automatic Critical** unless economic profit < gas cost.

---

### T2: Solo Whitehat ($0 capital)
- **Skills**: Reads Solidity, builds Foundry PoCs
- **Tools**: Slither, Foundry, manual analysis
- **Capital**: $0 — only reports, doesn't exploit
- **Time**: Days-weeks per target

**What they find**:
- Same things we'd find via /deephunt
- Threat model: **competitor for our bounty**

**Defensive strategy**:
- Hunt fresh targets (first 7-30 days post-deploy)
- Build differentiated capabilities (no-source bytecode analysis)
- Optimize J9 submission speed (race window)

---

### T3: Solo Blackhat ($1k-100k capital)
- **Skills**: Solidity dev, MEV searcher skills, custom exploits
- **Tools**: Foundry, Anvil, mempool monitoring
- **Capital**: Up to $100k own capital
- **Time**: Weeks-months on single target

**What's accessible**:
- Custom contract exploits requiring capital deployment
- Multi-step exploits (deposit → manipulate → withdraw)
- Time-window attacks (oracle staleness, governance proposals)
- Targeted phishing

**Severity weight**: T3-accessible → **High at minimum**, Critical if profit > $1M.

---

### T4: MEV Searcher / Bot Operator ($10k-10M effective, flash loan unlimited)
- **Skills**: Solidity + bot infra + tx ordering + private mempool access
- **Tools**: MEV-Boost, Flashbots, private relays, custom searchers
- **Capital**: $10k operating + UNLIMITED via flash loans (Aave, Maker, Balancer, Uniswap V3)
- **Time**: Same-block to minutes

**What's accessible**:
- Frontrun / backrun / sandwich
- Flash-loan + atomic exploit (no capital risk)
- Oracle manipulation in same block
- Liquidation MEV
- Arbitrage extraction

**Severity weight**: T4-accessible single-tx exploits → **Critical**. Flash-loanable = severity ↑↑.

---

### T5: Sophisticated APT ($100k-100M, multi-step)
- **Skills**: Solidity + cryptography + cross-chain coordination + protocol economics
- **Tools**: Same as T4 + supply chain access + multisig social engineering
- **Capital**: $100k-$100M
- **Time**: Months of preparation

**What's accessible**:
- Multi-block exploits (governance proposals, time-locked actions)
- Cross-chain message manipulation
- Cryptographic edge cases (signature malleability, EIP-1271 abuse)
- Zero-day on novel mechanisms

**Examples**:
- Wormhole signature verification bug (2022)
- Ronin multisig social
- Curve read-only reentrancy

**Severity weight**: T5-only → High. T5-required complex setups can downgrade to Medium if no clear economic incentive.

---

### T6: Nation-State / Lazarus tier (unlimited)
- **Skills**: All of T5 + supply chain compromise + 0-day exploitation + social
- **Tools**: Compromised dev machines, npm package supply chain, signed malware
- **Capital**: Unlimited
- **Time**: Years

**What's accessible**:
- Anything if economically motivated AND government-cleared target
- Supply chain attacks (Solana wallet drainer via npm, etc.)
- Private key extraction via malware
- Frontend hijack via DNS/CDN compromise

**Severity weight**: T6-only → typically **Low for bug bounty purposes** because:
- They're going to find their own way regardless
- Mitigation is operational (not code fix)
- Smart-contract bug bounties don't cover supply chain

**Exception**: Code-level bug that T6 can use → still severity by code-level T-tier (whoever else CAN do it).

---

## Severity Mapping

For each finding, ask: **what is the lowest tier that can execute this attack?**

| Lowest tier | Default severity | Modifiers |
|-------------|------------------|-----------|
| T1 (Script kiddie) | **Critical** | Even if profit small |
| T3 (Solo blackhat) | **High** | Critical if profit > $1M |
| T4 (MEV searcher) | **High** | Critical if flash-loanable + profit > $100k |
| T5 (Sophisticated) | **Medium** | High if profit > $10M |
| T6 (Nation-state only) | **Low/Informational** | Code fix recommended but not bounty-tier |

---

## Capital Sources Reference

When computing `capital_required` in J4:

### Flash Loan Pools (unlimited capital, single-tx)
- **Aave V3**: ETH, USDC, USDT, DAI — ~$1B+ available on mainnet
- **Maker DSS Flash**: DAI only, no fee
- **Balancer V2**: many tokens, 0 fee
- **Uniswap V3 Flash**: any pool's liquidity
- **dYdX Solo**: legacy, still functional

If exploit is wrapped in flash-loan tx → `capital_required = 0` regardless of size needed.

### Owned Capital (multi-block required)
- Stablecoin pools
- ETH/WBTC reserves
- Governance token holdings (for vote attacks)

---

## Composability with Threat Actors

Some attacks chain multiple tiers:
- T1 social engineers victim → T3 picks up dust
- T4 frontruns oracle update → T5 triggers governance attack

For these, severity = **highest individual tier's accessible portion**.

---

## Examples — Threat Modeling Past Exploits

| Exploit | Lowest Tier | Why |
|---------|-------------|-----|
| Cream ERC-4626 inflation (2022) | T3 | Required ~$100k deposit, simple multi-tx |
| Wormhole signature bug (2022) | T5 | Custom crypto exploit, $325M |
| KelpDAO LayerZero DVN (2024) | T6 | Supply chain compromise of DVN operator |
| Curve read-only reentrancy (2023) | T4 | Flash-loanable, single-tx |
| Euler liquidation bug (2023) | T4 | Flash-loanable, $200M loss |
| Drift cosigner compromise (2025) | T6 | Key extraction, $285M loss |
| Resolv USR depeg (2024) | T6 | Compromised key minted, supply chain |
| Ronin multisig (2022) | T6 | Social + key compromise |

**Pattern**: Most $100M+ exploits = T6 (operational), not code-level. Code bounties primarily catch T1-T4 issues.

---

## Use in `/deephunt` Workflow

In J4 economic analysis output:
```json
{
  "finding_id": "F001",
  "lowest_threat_tier": "T4",
  "rationale": "Flash-loanable, single-tx, requires ordering control via private relay",
  "capital_required_usd": 0,
  "expected_profit_usd": 500000,
  "feasibility_score": 75,
  "default_severity": "High",
  "severity_modifier": "+Critical due to profit > $100k threshold"
}
```

This translates directly to the severity argument in the J9 report.
