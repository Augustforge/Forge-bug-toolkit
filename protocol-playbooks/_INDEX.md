# Protocol Playbooks — target-specific quick-start (J0 lookup)

Concrete per-protocol "where to look" guides with mainnet addresses, contract maps, and
known-pitfall code (source: ugwst-sec WEB3-AUDIT-SKILLS, integrated 2026-06-13). Use at the
START of /deephunt J0 when the target IS (or forks) one of these protocols — saves the cold-read
ramp. This is the **concrete-instance** layer; `scripts/web3/threat_models/_PROTOCOL_PROFILES.md`
is the **abstract protocol-type** layer (invariants, adversaries). Read the profile for the
type, the playbook for the specific protocol — don't duplicate, they compose.

| Playbook | Use when target is / forks | Sharpest leads |
|---|---|---|
| `balancer.md` | Balancer V2/V3, any Vault-singleton AMM | **free flash-loans** from Vault, WordCodec packed-slot (Cat 2.8), boosted/nested pool composability |
| `makerdao.md` | MakerDAO / Sky, CDP stablecoins | Vat ray/wad/rad precision seams (Cat 1), PSM manipulation, Jug/Dog liquidation |
| `curve.md` | Curve, StableSwap forks | A-ramp manipulation, `virtual_price` flash-loan read (Cat 5.2), oracle from LP |
| `morpho.md` | Morpho Blue/Aave-V3-wrapper, P2P matching | P2P delta blending, IRM whitelist, permissionless-market oracle trust, lazy-rate (Cat 5.9) — point after our Superform-Morpho finding |
| `uniswap-v4.md` | UniV4, hook-based AMMs | hook permission matrix, flash-accounting reentrancy surface, singleton delta-manip (Cat 12.7), one-sided slippage (Cat 3.7) |
| `aave-v3.md` | Aave V3 + forks | e-mode, isolation-mode, liquidation, L2-sequencer (Cat 5.10) |
| `gmx.md` | GMX / perp-DEXs | mark-vs-index, funding, ADL (Cat 21) |
| `eigenlayer.md` | EigenLayer / restaking / AVS | operator leverage, slashing, correlated withdrawal (Cat 5.11) |

Each playbook's "Attack Surface" header links to the matching `../attack-trees/` tree (resolves —
the trees were integrated alongside). Flow: playbook (where) → attack-tree (branches) →
taxonomy Cat (bug kind) → `hypotheses.md` (H-NN).
