# Reading Note: Verus-Ethereum Bridge Source-Amount Forge (May 2026)

**Source**: [Halborn explainer](https://www.halborn.com/blog/post/explained-the-verus-ethereum-bridge-hack-may-2026), [Phalcon trace](https://x.com/Phalcon_xyz/status/2056295257361572238), [PeckShield alert](https://x.com/PeckShieldAlert/status/2056194168385642881), [Blockaid analysis](https://x.com/blockaid_/status/2056176541785034803)
**Reading date**: 2026-05-19
**Class**: Cryptographic verification ≠ semantic verification — bridge attested-payload trust gap
**Loss**: $11.58M (103.6 tBTC + 1,625 ETH + 147K USDC, swapped to 5,402 ETH)
**Audit corpus ID**: `verus-2026-source-amount-forge`

Following protocol from [`adversarial_reading.md`](../../../../sessions/_methodology/adversarial_reading.md) — 7-field template.

---

## 1. Author entry point (как ресёрчер начал)

Public GitHub: `VerusCoin/Verus-Ethereum-Contracts`. Никакой private knowledge не требовался. Repo open, README + audit reports absent (red flag — мост на $11.58M TVL без публичного audit history).

## 2. Critical step I would skip

Прочитать **`SubmitImports.sol` целиком** — не только signature verification path, но и amount decoding и payout pipeline. Большинство hunters читают cryptographic verification (signatures, Merkle proof) и убеждаются что "верификация есть → safe". Skip = miss the gap.

**Lesson**: верификация ≠ semantic check. Каждая bridge entry function требует **отдельной** trace от decoded payload field к payout call.

## 3. Heuristic для toolkit

> "Если bridge entry function проходит cryptographic verification и затем вызывает `_mint/_release/_transfer` с `amount` из payload, искать **explicit `require/assert`** linking этот amount к verified source-chain field. Absence = candidate for Verus 2026 class."

Operationalized in [`bridge_tests/source_amount_grep.sh`](../../../bridge_tests/source_amount_grep.sh) + [`threat_models/cross_chain_source_destination_binding.yaml`](../../../threat_models/cross_chain_source_destination_binding.yaml).

## 4. Tool which would have caught it

После того как наш toolkit получил Verus update:
- `apply.py` с `cross_chain_source_destination_binding.yaml` matched бы на `protocol_class=bridge`
- `executable_checks` regex_count `require.*sum.*locked.*paid` вернул 0 → high severity flag
- `source_amount_grep.sh` отметил бы `submitImports` entry function без conservation assertion
- `bridge_message_forge.md` prompt emitted hypothesis "что если attacker forge'aет blob с tiny input + huge output?"
- Cross-link к Wormhole 2022 / Nomad 2022 case studies дал бы prior + Bayesian confidence

**Probability мы бы поймали Verus до exploit** при /deephunt cycle: ~70-80%.

**До этой работы (Phase 1 toolkit state)**: ~20-30% — checklists упоминали `locked ≡ issued - burned` но без executable detector и без threat_model lens.

## 5. Time (honest)

Reading + analysis: ~30 min для one hunter. Foundry PoC construction: ~1-2 hours. Total time-to-exploit для experienced bug hunter: **~3 hours after public repo clone**.

Attacker мог потратить значительно больше на Tornado Cash setup + opsec (funding wallet, prepping exit liquidity), но **technical depth** для bug discovery — несколько часов чтения.

## 6. Class-level lesson

Same conceptual class как:
- **Wormhole 2022** ($325M): trusted `signature_set` account без validating creation provenance
- **Nomad 2022** ($190M): trusted default `0x00` merkle root как confirmed state
- **Verus 2026** ($11.58M): trusted notary-signed CCE без validating amount conservation

**Все три** — bridge верит криптографической envelope (что-то-было-подписано), не верифицирует semantic claim payload contents (что было подписано — это правда о source state).

**Mitigation universally**: pair every attestation verification с downstream semantic invariant assertion. Two separate properties, two separate checks.

## 7. Sibling-variant questions (для hunting next)

1. **Wormhole post-2022 fix**: был узким (validate `signature_set` creator). Existing sibling в post-fix code? Other accounts trusted by mere existence?
2. **Stargate / LayerZero custom adapters**: если protocol uses default LayerZero verification но adds custom destination logic — может custom logic skip amount conservation?
3. **Polkadot parachain bridges**: same conceptual pattern (validator-signed XCM messages) — есть ли amount conservation на destination?
4. **Cosmos custom IBC apps** (не canonical IBC, а protocols building on top): IBC packet handlers — где amount validated?
5. **L1↔L2 native bridges** (Arbitrum/Optimism/Polygon zkBridge): finality assumption + amount conservation. L2 sequencer trusted to report correctly?
6. **Intent solvers** (UniswapX/CowSwap/Across): attested settlement price — same lens. Solver signed "filled at P" — settlement verifies P matches reality at execution block?
7. **LRT operators** (EigenLayer, Symbiotic): operator-signed slashing reports — restaking protocol verifies on-chain slashing events match report?
8. **Oracle bundles** (Pyth/RedStone): publisher-signed price update — consumer applies deviation bound check post-verification?

---

## Cross-link

- Threat model (bridge-specific): [`threat_models/cross_chain_source_destination_binding.yaml`](../../../threat_models/cross_chain_source_destination_binding.yaml)
- Threat model (broader sibling lens): [`threat_models/attested_amount_trust_gap.yaml`](../../../threat_models/attested_amount_trust_gap.yaml)
- Checklist: [`checklists/specialized/bridge.md`](../../../checklists/specialized/bridge.md) Sections 1-4
- Adversarial prompt: [`prompts/bridge_message_forge.md`](../../../prompts/bridge_message_forge.md)
- Operational detector: [`bridge_tests/source_amount_grep.sh`](../../../bridge_tests/source_amount_grep.sh)
- Threat intel: [`threat_intel.md`](../../../threat_intel.md) §8 Bridge Source-Amount Conservation Class
- Audit corpus: `_known_findings.jsonl` ID `verus-2026-source-amount-forge`
- Successful pattern: [`successful_patterns.md`](../../../../../sessions/_methodology/successful_patterns.md) entry #5
- Learning path: [`learning_paths/bridges.md`](../../../../../sessions/_methodology/learning_paths/bridges.md)
- Calibration class tag: `bridge-cross-chain` в [`calibration_log.jsonl`](../../../../../sessions/_methodology/calibration_log.jsonl)
- Gap review sibling list: [`gap_review.md`](../../../../../sessions/_methodology/gap_review.md)
