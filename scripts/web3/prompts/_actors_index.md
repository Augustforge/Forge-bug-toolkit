# Adversarial Actor Prompts — Index

Each prompt = a different threat-model lens. Standard `read_as_attacker.md` covers the outside attacker. Here — adversarial-insider variants. Use the matched lens(es) in the J0 hypothesis phase.

## When to use which

| Prompt | Apply when protocol has |
|---|---|
| `bonded_actor_threat.md` | General — any bonded/whitelisted/privileged role |
| `oracle_lies.md` | Pyth / Chainlink / TWAP / custom oracle / DVN |
| `relayer_censors.md` | IBC relayer / LayerZero executor / Wormhole / Axelar relay |
| `sequencer_reorders.md` | L2 (Arbitrum/Optimism/Base/zkSync) — centralized sequencer |
| `validator_extracts.md` | TSS / MPC / GG18/20 / FROST / threshold BLS / multisig validator set |
| `keeper_skips.md` | Compound v3 / Aave liquidations / Yearn harvests / external bot triggers |
| `mev_searcher_inserts.md` | DEX / AMM / order books / batch auction solvers |
| `frontend_compromised.md` | DeFi UI on Vercel/Cloudflare/AWS S3 with EOA signing |
| `bridge_message_forge.md` | **Bridges + attested-payload systems** — destination-side verification (consumes signed payload). Use alongside `relayer_censors.md` (upstream) for full bridge actor coverage. Covers: Verus 2026, Wormhole 2022, Nomad 2022, Ronin 2022, Multichain 2023 classes. |

## Workflow

1. Identify which actor roles exist in the protocol (read whitepaper + access control map)
2. Run the matched prompt(s) on the relevant contracts
3. Each prompt emits actor-specific hypotheses → merge into `hypothesis_candidates.md`
4. After all matched lenses — run `hypothesis_triage.md` (F4) to filter noise

## Multiple actors

If the protocol has multiple actor classes (typical for bridges — relayer + oracle + validator) — apply each as a separate prompt. Don't merge into one — different lenses yield different hypotheses.

## Anti-pattern

Don't apply prompts mechanically ("every protocol gets all 7"). Each prompt is expensive (Claude reading + thinking). Apply only the matched ones. Better 2 deep adversarial-lens reads than 7 shallow.
