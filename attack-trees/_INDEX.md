# Attack-Trees — per-protocol hypothesis lookup (T1 artifact)

Per-protocol-type attack decision trees (source: ugwst-sec WEB3-AUDIT-SKILLS, integrated
2026-06-13). Use as a **T1 lookup**: once you've classified the target's protocol type,
walk the matching tree top-down and turn each leaf you can't immediately refute into an
H-{NN} candidate in `hypotheses.md` (T7). Complements `methodology/hypothesis_taxonomy.md`
(generic bug classes) — the trees are the protocol-specific *where to look*, the taxonomy is
the *what kind of bug*.

**Note on source links:** the original trees reference `patterns/X.md#anchor` (the source
repo's pattern files, which are mostly empty stubs). IGNORE those links — map each leaf to
OUR taxonomy category via the table below. The tree *structure* (the attack branches) is the
value, not the dead links.

## How to use (in /deephunt T1, after file prioritization)
1. Classify protocol type (also via `scripts/web3/threat_models/_PROTOCOL_PROFILES.md`).
2. Open the matching tree below; for each branch, mark `APPLIES` / `N/A` / `MAYBE`.
3. Each `APPLIES` leaf → H-{NN} hypothesis (cross-ref the taxonomy Cat in the table).
4. Each `MAYBE` → T6 composite building block.

## Tree → our taxonomy Cat mapping
| Tree | Primary taxonomy Cat | Profile (`_PROTOCOL_PROFILES.md`) |
|---|---|---|
| `lending-attack-tree.md` | 5 (oracle), 8 (liquidation), 5.10 (L2-seq) | lending |
| `dex-attack-tree.md` | 3.7 (slippage guard), 5.2 (spot manip), 12.7 (hook) | dex_amm |
| `bridge-attack-tree.md` | 5.5 (replay), 18.x (consensus), 5.11 ref | bridge |
| `vault-attack-tree.md` | 1.2/1.6 (rounding/donation), 8.3 (inflation), 9.6 | vault_4626 |
| `liquid-staking-attack-tree.md` | 5.11 (restaking), 8 (share), 3.3 (cost basis) | liquid_staking |
| `stablecoin-attack-tree.md` | 5 (oracle peg), 4.7 (mint), 1 (math) | stablecoin |
| `governance-attack-tree.md` | 4.7 (mint via proposal), 3.5 (snapshot) | governance |
| `nft-lending-attack-tree.md` | 5.2 (floor-price oracle), 8 (liquidation) | nft_lending |
| `perpetuals-attack-tree.md` | **21** (funding/ADL/mark), 5, 8 | perps_deriv |
| `options-attack-tree.md` | **19** (greeks/settlement/DOV), 5, 9 | options |
| `insurance-attack-tree.md` | **20** (cover/claim/pool-drain), 5, 13 | insurance |
| `intent-based-attack-tree.md` | **16.9/16.10** (UI/bitmap/partial), **5.8** (route-unbound) | intent_dex |

The three trees in **bold** (perp/options/insurance) and the intent tree back our newest
taxonomy classes (Cat 19/20/21 + 16.10) — they were the gap this integration filled.
