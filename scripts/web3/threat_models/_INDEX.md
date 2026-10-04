# Threat Models — Index + Authoring Guide

This catalog is the toolkit's main hypothesis-generation layer. Each YAML is a **reusable adversarial-lens pattern** that apply.py matches against a target and emits instantiated hypotheses.

> **Profile layer (read BEFORE matcher).** [`_PROTOCOL_PROFILES.md`](_PROTOCOL_PROFILES.md) — per-protocol-type
> threat intelligence (8 types × ranked adversaries / critical invariants / read-first + temporal phases +
> composability layers). `_`/`.md` → apply.py does NOT load it (it's a reference, not a matcher). Flow: classify
> `protocol_class` → read the profile (why these threats) → then apply.py (which models fired). pashov x-ray
> threats.md, [[reference_pashov_skills]] block F. Does NOT duplicate the bug-taxonomy — it maps to Cat numbers.

## Catalog

| Model | When matches | Severity | Source case |
|---|---|---|---|
| `tss_validator_extraction.yaml` | Protocol uses TSS/MPC threshold sig (GG18/20, FROST, BLS threshold) | High-Critical | Thorchain 2026 ($10.8M) |
| `post_bounty_variant_drift.yaml` | Protocol has a past paid bounty with a potentially narrow fix | Medium-Critical | Thorchain α-shuffle 2022 → c-split 2026 |
| `cross_chain_source_destination_binding.yaml` | Bridge / cross-chain protocol with notary/guardian-attested payload + payout logic on destination | High-Critical | Verus 2026 ($11.58M), Wormhole 2022 ($325M), Nomad 2022 ($190M) |
| `attested_amount_trust_gap.yaml` | Broader sibling lens — any consumer of off-chain attestation (LRT operator reports, Pyth bundles, intent solver fills, restaking attestations) | Medium-Critical | Verus 2026 (canonical) + LRT/oracle siblings |
| `erc4337_signature_replay.yaml` | Account abstraction targets — smart accounts, paymasters, bundlers, factories (ERC-4337 / ERC-1271 / ERC-7579) | Medium-Critical | Cantina ERC-4337 advisory 2025 (4 patterns: cross-account replay, ERC-1271 reuse, paymaster drift, initCode frontrun) |
| `validator_set_quorum_integrity.yaml` | M-of-N bridges (Gravity/Cosmos, Ronin-style) — quorum verification LOGIC | Medium-Critical | Gravity 2026 ($5.4M, scope-boundary) + Code4rena Gravity 2021 (findable logic) |
| `liquidity_locker_privileged_unlock.yaml` | Liquidity locker / vesting / escrow holding pooled third-party custody with owner-mutable lock params | Medium-Critical | DxSale/DxLock 2026 ($7.3M); Decurity 2023 ($5.2M averted) |
| `fund_liveness_terminal_state.yaml` | Phased-lifecycle holding funds (ICO/crowdsale, vesting, escrow, auction, DAO-fund, locker) where the EXIT transition can never fire / be withheld | Medium-Critical | HONG ICO 2026 ($2M / 1003 ETH, 9y frozen → white-hat) |
| `governance_capture_mint_drain.yaml` | On-chain governance (Aragon/Governor) where majority is CHEAP to acquire (tiny supply) AND execution is atomic (no timelock), reaching uncapped mint/treasury with an AMM exit | High-Critical | Token of Power 2026 ($1.585M) + Beanstalk 2022 ($182M, flash-loan variant) |
| `agent_economy_escrow_identity.yaml` | Agent-economy infra — EIP-8004 (identity/reputation registries), EIP-8183/ACP escrow (Client/Provider/Evaluator), x402 payments | Medium-Critical | CertiK "Rise of the Agent Economy" 1+2 (EIP-8004/8183/x402 audit, Cat 23, 9 patterns) |
| `rwa_permissioned_token.yaml` | Tokenized RWA / security-token standards — ERC-1400 (partitions), ERC-3643/T-REX (compliance/identity), ERC-1404/6065/7943; KYC/whitelist/freeze/forcedTransfer/NAV/redeem-offchain | Medium-Critical | SlowMist RWA-Security-Practices (Cat 24; ERC-1400 21 VPs + ERC-3643 7 VPs; class-level) |

**Conceptual axes** (see [`_PATTERN_REGISTRY.md`](_PATTERN_REGISTRY.md)):
- Axis 1: **Cryptographic verification ≠ semantic verification** — tss_validator_extraction, cross_chain_source_destination_binding, attested_amount_trust_gap, **erc4337_signature_replay** (signature valid ≠ intent valid)
- Axis 2: **Asymmetric defense / post-bounty drift** — post_bounty_variant_drift
- Axis 4: **Custody exit-path / privileged extraction** — validator_set_quorum_integrity, liquidity_locker_privileged_unlock, **governance_capture_mint_drain** (a cheaply-acquired vote + atomic execution reaches an uncapped mint/treasury; AMM is the exit) (contract holds 3rd-party funds; an exit-path or quorum-logic flaw releases them)
- Axis 5: **Liveness / permanent freeze (mirror of extraction)** — fund_liveness_terminal_state, **agent_economy_escrow_identity** (escrow liveness-trap: funded job locked until expiredAt; settlement held hostage by a reverting afterAction hook) (funds CAN'T move because the legitimate exit transition is unreachable / activity-gated / adversary-blockable; no theft needed — still Critical/High)
- Axis 6: **Settlement authority ≠ verified outcome** — **agent_economy_escrow_identity** (the Evaluator settles a job, but the evidence it judges is unbound to the Provider's on-chain commitment, and if it's an AI agent it's prompt-injectable — settlement authority is trusted but the outcome it certifies is forgeable)
- Axis 7: **On-chain receipt ≠ off-chain truth / one guarded path ≠ all paths** — **rwa_permissioned_token** (the contract is a mapping layer over an SPV/custodian; a compliance check on `transfer` says nothing about `mint`/`forcedTransfer`/`redeem`, per-partition balances drift from the total, and a `redeem` flips state before the off-chain settlement confirms — "the code permits far more than users assume")

## How apply.py uses these

```bash
cd bug-bounty-toolkit
python3 scripts/web3/threat_models/apply.py \
    --target sessions/$TARGET \
    --output sessions/$TARGET/threat_model_hypotheses.md
```

apply.py:
1. Loads all `*.yaml` (skips `_*.yaml`)
2. Reads `sessions/$TARGET/chain.json` for the `chain` field
3. Reads optional `sessions/$TARGET/_tags.txt` (one tag per line) — set by Claude based on protocol class detection
4. Matches via `applies_when` AND not `negative_match`
5. For matched models — runs `executable_checks` if the target has source
6. Emits markdown with (model name + assumption + instantiated hypotheses + case studies + checklists + check hits)

In quick mode (`/hunt`) — only models with `severity_floor: medium+` shown.
In deep mode (`/deephunt`) — all matched models shown.

---

## How to AUTHOR a new threat_model from an exploit writeup

**Worked example: Thorchain TSSHOCK 2026 → `tss_validator_extraction.yaml`**

### Step 1 — Read the writeup + identify the root cause class

Don't capture "what exactly happened" — capture the **class of assumption violated**.

Wrong (too specific): "Validator extracted key via malformed α value in dlnproof"
Right (class-level): "Bonded validator can reconstruct vault key from N legitimate ceremonies if ZK proofs not strict"

### Step 2 — Identify actors

Who has a legitimate capability that gets weaponized? List them with their **legitimate** action. The attack comes later — first establish the trust structure.

```yaml
actors:
  - role: bonded_validator
    capability: Joins active signing set, participates in keygen + signing as legitimate member
```

### Step 3 — Write assumption_violated in plain prose

One paragraph. What does the protocol silently assume? This is the LENS — it must be sharp:

```yaml
assumption_violated: |
  Bonded validator participating in N legitimate signing ceremonies cannot
  reconstruct vault private key offline.
```

### Step 4 — Write attack_vector in plain prose

How the violation is weaponized. Short but specific enough that another engineer can reason about siblings.

### Step 5 — Write hypotheses_template — 3-5 specific testable claims

Each should be **observable in target** + a **specific code element to check**.

Wrong: "Check TSS is secure" — generic
Right: "If protocol uses GG18/GG20 tss-lib fork, verify Paillier biprime check + small-factor sieve in ALL paths"

These templates instantiate per-target when apply.py runs.

### Step 6 — Set applies_when

Be **inclusive on the first pass, narrow later**. Too narrow = miss valid matches. Too broad = noise.

`protocol_class` use the canonical set: bridge, amm, lending, restaking, vault, governance, mpc-custody, aggregator, yield, perps, oracle, dex.

`tags` semantic free-form snake_case. Tag conventions emerge over time.

`chain: [any]` is fine unless the model is truly chain-specific.

> **GOTCHA (matching is AND across declared fields).** `matches()` requires EVERY field you declare in `applies_when` to pass. If you set `protocol_class: [...]`, a target whose class is `None` or outside your list is **rejected even when the tags match perfectly** → the model silently never fires. If the class is fuzzy (e.g. an RWA token is variously `token`/`security_token`/`stablecoin`/`vault`/`other`), leave `protocol_class: []` and carry the match on specific tags alone — generic tags (`compliance`,`kyc`) cause false matches, so prefer narrow ones (`permissioned_token`,`real_world_asset`). Then make sure a T1 trigger tells Claude to set one of those tags in `_tags.txt`. (Found 2026-06-18 — `rwa_permissioned_token` matched 0 until the protocol_class gate was dropped.)

### Step 7 — Add executable_checks where they help

Only add if a concrete pattern (grep regex) maps to a surface that can be checked statically.

For TSS — `grep tss-lib | PaillierSK | dlnproof` clearly identifies the surface. For "post-bounty drift" — no static check makes sense, skip.

### Step 8 — Cite case_studies + related_checklists/_prompts

Cross-link with threat_intel.md (add the case study there too if not present) + relevant checklists and prompts.

### Step 9 — Set severity range

`severity_floor: high` for TSS (key extraction always Critical when confirmed).
`severity_floor: medium` for broader/composability models (depends on the instance).

### Step 10 — Validate

Manually run apply.py against a test target. Verify:
- The model loads without a YAML error
- `applies_when` matches expected targets and misses unrelated ones
- `executable_checks` fire correctly on the test corpus
- The output markdown reads sensibly to Claude in the next phase

After the first real use — fill `last_validated_against`.

---

## Anti-patterns

**Don't** copy-paste exploit specifics into hypotheses. If a pattern only catches Thorchain TSSHOCK c-split — the model is worthless for anything else.

**Don't** make hypotheses a list of known-class buzzwords. "Check reentrancy" — Claude knows. The model must add a **novel framing**.

**Don't** make `applies_when` so broad (`tags: [any]`) that it matches everything — produces noise.

**Don't** forget `severity_floor` — without it the model spams quick mode hunting.

---

## Backlog — models to write next

Good candidate sources for the next models (after Thorchain dust settles):
- `oracle_single_point_trust.yaml` — KelpDAO class (single DVN, single Pyth feed)
- `governance_compromised_signer.yaml` — Ronin/Drift class (multi-sig with low threshold)
- `frontend_signing_blast_radius.yaml` — Curve/Balancer frontend hijack class
- `keeper_inaction_cascade.yaml` — Compound v3 / GMX class
- ~~`flashloan_atomic_extraction.yaml`~~ — **DONE** (Cream/Beanstalk governance-drain class covered by `governance_capture_mint_drain.yaml`, post-TOP 2026 — handles both flash-loan and cheap-buy vote sources)
- ~~`cross_chain_message_replay.yaml`~~ — **DONE** (covered by `cross_chain_source_destination_binding.yaml` post-Verus 2026 — replay protection is Section 2 in [`checklists/specialized/bridge.md`](../checklists/specialized/bridge.md))

Each followed per Steps 1-10 above.
