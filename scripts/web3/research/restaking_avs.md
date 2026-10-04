# Restaking + AVS (Actively Validated Services)

**Status**: studying
**Priority**: very-high
**Why hunter cares**: EigenLayer $15B+ TVL by 2026, ecosystem AVS programs each often $1M+ payout. AVS bug class — NEW, audit ecosystem still maturing. Bugs are not widely known.

## Core concept

ETH staked in EigenLayer = "restaked" — operator opts into validating additional services (AVS). Operator's bond can be slashed by AVS if misbehaves. Multi-AVS = single operator validates several services parallel.

Risk surface:
- EigenLayer core slashing logic
- Operator opt-in mechanics
- Withdrawal queue
- AVS-specific slashing condition encoding
- Cross-AVS double-slashing prevention

## Top bug classes

### 1. Slashing logic gaps
Slasher contract decides when to slash operator. Bugs:
- Slashing condition can be triggered FALSELY (forged evidence)
- Slashing condition cannot be triggered when SHOULD be (real misbehavior unpunished)
- Slashing amount over/under estimated
- Double-slashing across AVSes for same misbehavior (slashed twice)
- Slashing window too short — operator withdraws bond before slash propagates

> **THIS IS LITERALLY THORCHAIN-CLASS for restaking world**. Validator misbehaves, slashing exists on paper but fails in practice.

### 2. Operator opt-in mechanics
- Operator can opt into AVS retroactively (collect rewards without exposure)
- Operator opt-out instant vs delayed (race-to-withdraw before slash)
- Multiple opt-ins for same AVS = double rewards?

### 3. Withdrawal queue
EigenLayer queues withdrawals for delay period (7 days typical).
- Can operator skip queue?
- Can attacker manipulate queue priority?
- Cross-asset withdrawal — accounting drift?

### 4. AVS coordination
- Multi-AVS operator: AVS A signals slash, AVS B not aware
- Operator's stake counted twice across AVSes (over-leverage)
- Slashing waterfall (cascading impacts)

### 5. Reward distribution
- Reward calculation drift over time
- Operator can claim before earning
- Delegator-operator commission accounting

### 6. Restaking-of-restaking
Restaking another LRT? Cascading slashing exposure.
- Operator restakes from Lido stETH → eEthos → operates AVS
- Single misbehavior cascades through chain

## Notable disclosures (study)

- **EigenLayer audits** — Spearbit + ConsenSys + Sigma Prime reports public
- **Pendle EigenLayer interactions** — composability bugs
- **EtherFi LRT** — multiple disclosed issues during 2024
- **Renzo, Kelp DAO** — operator opt-in bugs
- **AltLayer MACH** — slashing logic gaps

## Architecture (EigenLayer specific)

Key contracts (Layr-Labs/eigenlayer-contracts):
- `DelegationManager.sol` — operator delegation
- `StrategyManager.sol` — staked asset accounting
- `Slasher.sol` (deprecated, replaced by AVSDirectory)
- `AVSDirectory.sol` — operator-AVS opt-in
- `EigenPodManager.sol` — beacon chain integration
- `RewardsCoordinator.sol` — reward distribution

Key flows:
1. Staker deposits ETH/LST → StrategyManager
2. Staker delegates to operator → DelegationManager
3. Operator opts into AVS → AVSDirectory
4. AVS service runs, operator may misbehave
5. Slasher (now AVS-specific contract) slashes
6. Staker queues withdrawal (7d delay)

## Symbiotic (alternative design)

Different from EigenLayer:
- Slashing contracts deployed per-vault
- Different opt-in semantics
- Different reward model

Compare codebases — bugs in one often don't appear in the other = potential alpha.

Repo: https://github.com/symbioticfi/core

## Hunting workflow once we reach `can-hunt`

1. Identify protocol uses EigenLayer / Symbiotic / Karak
2. Check operator opt-in mechanics:
   - Is signature replayable across AVSes?
   - Is opt-in retroactive vs forward-only?
3. Check slashing condition:
   - Can attacker prevent legitimate slash (DoS slasher)?
   - Can attacker trigger false slash (forged evidence)?
4. Withdrawal queue race:
   - Slash trigger followed by withdrawal — does withdrawal complete?
   - Operator's bond drained BEFORE slash propagates?
5. Cross-protocol composability — LRT restaked? Cascading exposure?

## Active programs

- **EigenLayer Immunefi** — up to $1M
- **EtherFi** — Immunefi
- **Renzo** — Immunefi
- **Symbiotic** — bug bounty live
- **Most AVSes** — separate programs (Brevis, Lagrange, AltLayer)

## To-author once can-hunt status is reached

- `scripts/web3/checklists/specialized/restaking_avs.md` (extend existing `restaking.md`)
- `scripts/web3/threat_models/slashing_logic_gaps.yaml`
- `scripts/web3/threat_models/operator_optin_race.yaml`
- `scripts/web3/threat_models/withdrawal_queue_race.yaml`

## Cross-link

- Existing `scripts/web3/specialized/restaking_hunter.py` — extend with EigenLayer-specific patterns
- Existing `scripts/web3/checklists/specialized/restaking.md` — augment
- Existing `scripts/sol/specialized/slashing_edge_case_analyzer.py` — Sol equivalent already done
