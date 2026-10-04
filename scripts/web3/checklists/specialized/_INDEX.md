# Specialized Class Checklists — Index

Per-protocol-class checklists. Apply when target matches the class.

Cross-reference: `DEFI_PRIMITIVES.md` (top-level) for primitive-specific bugs.

| File | Protocol class | Hunter script |
|------|----------------|----------------|
| `bridge.md` | LayerZero/Wormhole/Axelar/CCIP | `specialized/bridge_hunter.py` |
| `vault_erc4626.md` | ERC-4626 vaults | `specialized/vault_hunter.py` |
| `amm.md` | Uniswap V2/V3/V4, Curve, Balancer | `specialized/amm_hunter.py` |
| `lending.md` | Aave/Compound forks | `specialized/lending_hunter.py` |
| `restaking.md` | EigenLayer-likes | `specialized/restaking_hunter.py` |
| `governance.md` | Governor + Timelock | `specialized/governance_hunter.py` |
| `aa_erc4337.md` | Account Abstraction | `specialized/aa_erc4337_hunter.py` |
| `gravity_validator.md` | Gravity / M-of-N validator-set bridges (§8 = quorum degradation) | `specialized/gravity_validator_hunter.py` |
| `cross_layer_resource_limit.md` | CometBFT/Tendermint vote-based bridges/oracles/AVS (Cat 18.5 size-limit → liveness) | manual (read node config) |
| `intent_based.md` | CowSwap, UniX | manual |
| `mev_boost_pbs.md` | Relays, builders | manual |
| `dex_aggregator.md` | 1inch, Paraswap, Cowswap | manual |
| `yield_aggregator.md` | Yearn, Beefy | manual |
| `stablecoin.md` | DAI, FRAX, LUSD | manual |
| `synthetic_asset.md` | Synthetix, UMA | manual |
| `insurance_protocol.md` | Nexus, InsurAce | manual |
